# hier rein kommt dann die HTF mean reversion strategy basierend auf:
# RSI, vllt VWAP und breakout oder so in der richtigen Zone - rumprobieren
# diese strat wird dann gehedged mit einer nur trendfollowing strategie

# Standard Library Importe
from decimal import Decimal
from typing import Any
import sys
from pathlib import Path

# Nautilus Kern offizielle Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder, StopMarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderEvent, PositionEvent
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.currencies import USDT, BTC

# Nautilus Kern eigene Importe !!! immer
from tools.structure.TTTbreakout import TTTBreakout_Analyser
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags
from nautilus_trader.common.enums import LogColor

# Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex


class MeanReversionHTFStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    bar_type_1h: str  
    bar_type_1d: str
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    close_positions_on_stop: bool = True 

class MeanReversionHTFStrategy(Strategy):
    def __init__(self, config:MeanReversionHTFStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        if isinstance(config.bar_type, str):
            self.bar_type = BarType.from_str(config.bar_type)
        else:
            self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.last_rsi_cross = None
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.realized_pnl = 0
        self.bar_counter = 0
        self.stopped = False
        self.breakout_analyser = TTTBreakout_Analyser(lookback=20, atr_mult=1.5, max_counter=6)
        

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.log.info("Strategy started!")
        risk_percent = Decimal("0.005")  # 0.5%
        max_leverage = Decimal("2")
        min_account_balance = Decimal("1000") 
        risk_reward_ratio = Decimal("2")  # 2:1 Risk-Reward Ratio
        self.risk_manager = RiskManager(self, risk_percent, max_leverage, min_account_balance, risk_reward_ratio)
        self.order_types = OrderTypes(self)

        self.collector = BacktestDataCollector()
        self.collector.initialise_logging_indicator("RSI", 1)
        self.collector.initialise_logging_indicator("position", 2)
        self.collector.initialise_logging_indicator("realized_pnl", 3)
        self.collector.initialise_logging_indicator("unrealized_pnl", 4)
        self.collector.initialise_logging_indicator("balance", 5)

    def get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None

    def on_bar(self, bar: Bar) -> None:
        rsi_value = self.rsi.value
        self.rsi.update_raw(bar.close)
        self.breakout_analyser.update_bars(bar)
        is_breakout, breakout_dir = self.breakout_analyser.is_tttbreakout()
        
        # Prüfe, ob bereits eine Order offen ist (pending), um Endlos-Orders zu vermeiden
        open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        if open_orders:
            return  
        
        # Kennzeichnen, ob Schwellen schon überschritten wurden:
        if not hasattr(self, "rsi_overbought_triggered"):
            self.rsi_overbought_triggered = False
        if not hasattr(self, "rsi_oversold_triggered"):
            self.rsi_oversold_triggered = False

        # LONG und SHORT Setup wird ausgeführt:
        self.long_setup(rsi_value, is_breakout, breakout_dir)
        self.short_setup(rsi_value, is_breakout, breakout_dir)

        # VISUALIZER UPDATEN
        net_position = self.portfolio.net_position(self.instrument_id) # das hier danach weg war für debugging
        try:
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        except Exception as e:
            self.log.warning(f"Could not calculate unrealized PnL: {e}")
            unrealized_pnl = None
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()
        #self.log.info(f"acc balances: {usd_balance}", LogColor.RED)
        
        self.collector.add_indicator(timestamp=bar.ts_event, name="account_balance", value=usd_balance)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=float(rsi_value) if rsi_value is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)

    def long_setup(self, rsi_value, is_breakout, breakout_dir):
        if rsi_value < self.rsi_oversold:
            self.rsi_oversold_triggered = True

        if self.rsi_oversold_triggered and rsi_value <= 0.45:
            if is_breakout and breakout_dir == "long":
                self.log.info("TTT Breakout LONG erkannt")

                entry_price = self.portfolio.last_price(self.instrument_id)
                atr = self.breakout_analyser._calc_atr()
                stop_loss = entry_price - 2 * atr
                take_profit = entry_price + 4 * atr

                position_size = self.risk_manager.calculate_position_size(entry_price=entry_price, stop_loss_price=stop_loss, risk_per_trade=0.01)
                self.submit_long_bracket_order(self, position_size, entry_price, stop_loss, take_profit)

    def short_setup(self, rsi_value, is_breakout, breakout_dir):
        if rsi_value > self.rsi_oversold:
            self.rsi_overbought_triggered = True

        if self.rsi_overbought_triggered and rsi_value <= 0.55:
            if is_breakout and breakout_dir == "short":
                self.log.info("TTT Breakout SHORT erkannt")
                
                entry_price = self.portfolio.last_price(self.instrument_id)
                atr = self.breakout_analyser._calc_atr()
                stop_loss = entry_price + 2 * atr
                take_profit = entry_price - 4 * atr

                position_size = self.risk_manager.calculate_position_size(entry_price=entry_price, stop_loss_price=stop_loss, risk_per_trade=0.01)
                self.submit_short_bracket_order(self, position_size, entry_price, stop_loss, take_profit)
        

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        if net_position is not None and net_position != 0:
            self.log.info(f"Closing position for {self.instrument_id} at market price.")
            #self.log.info(f"position.quantity: {net_position}", LogColor.RED)
            # Always submit the opposite side to close
            if net_position > 0:
                order_side = OrderSide.SELL
                action = "SHORT"
            elif net_position < 0:
                order_side = OrderSide.BUY
                action = "BUY"
            else:
                self.log.info("Position quantity is zero, nothing to close.")
                return
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=order_side,
                quantity=Quantity(abs(net_position), self.instrument.size_precision),
                time_in_force=TimeInForce.GTC,
                tags=create_tags(action=action, type="CLOSE")
            )
            #unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
            #self.realized_pnl += float(unrealized_pnl) if unrealized_pnl else 0
            self.submit_order(order)
            self.collector.add_trade(order)
        else:
            self.log.info(f"No open position to close for {self.instrument_id}.")
            
        if self.stopped:
            logging_message = self.collector.save_data()
            self.log.info(logging_message, color=LogColor.GREEN)
    
    def on_stop(self) -> None:
        position = self.get_position()
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")
        self.stopped = True  

        # VISUALIZER UPDATEN - der try execpt block ist nur zum debuggen - eigentlich kommt da nur  unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id) hin
        
        try:
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        except Exception as e:
            self.log.warning(f"Could not calculate unrealized PnL: {e}")
            unrealized_pnl = None
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()
        #self.log.info(f"acc balances: {usd_balance}", LogColor.RED)

        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="balance", value=usd_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="RSI", value=float(self.rsi.value) if self.rsi.value is not None else None)
        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)
        #self.collector.visualize()  # Visualize the data if enabled


    def on_order_filled(self, order_filled) -> None:
        ret = self.collector.add_trade_details(order_filled)
        self.log.info(f"Order filled: {order_filled.commission}", color=LogColor.GREEN)

    def on_position_closed(self, position_closed) -> None:

        realized_pnl = position_closed.realized_pnl  # Realized PnL
        self.realized_pnl += float(realized_pnl) if realized_pnl else 0
        self.collector.add_closed_trade(position_closed)

    def on_position_opened(self, position_opened) -> None:
        realized_pnl = position_opened.realized_pnl
        #self.realized_pnl += float(realized_pnl) if realized_pnl else 0

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()


