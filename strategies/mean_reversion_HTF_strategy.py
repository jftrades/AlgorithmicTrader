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
    hourly_bar_type: str 
    daily_bar_type: str
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    close_positions_on_stop: bool = True 

class MeanReversionHTFStrategy(Strategy):
    def __init__(self, config:MeanReversionHTFStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.hourly_bar_type = BarType.from_str(config.hourly_bar_type)
        self.daily_bar_type = BarType.from_str(config.daily_bar_type)
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
        self.breakout_analyser = TTTBreakout_Analyser(lookback=15, atr_mult=1.25, max_counter=6)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.hourly_bar_type)
        self.subscribe_bars(self.daily_bar_type) 
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
        bar_type_str = str(bar.bar_type)
        if "1-DAY-LAST-INTERNAL" in bar_type_str:
            self._handle_daily_bar(bar) 
            self._update_visualizer(bar)
        
        elif "1-HOUR-LAST-EXTERNAL" in bar_type_str:
            self._handle_hourly_bar(bar)
    
    def _handle_hourly_bar(self, bar: Bar) -> None:
        self.breakout_analyser.update_bars(bar)

        is_breakout, breakout_dir = self.breakout_analyser.is_tttbreakout() # TTT Breakout prüfen

        open_orders = self.cache.orders_open(instrument_id=self.instrument_id) # Prüfe offene Orders
        if open_orders:
            return

        if not self.rsi.initialized:
                self.log.warning("RSI not initialized yet - skipping trading logic")
                return

        if is_breakout:
            current_rsi = self.rsi.value
            if breakout_dir == "long" and current_rsi is not None and 0.65 <= current_rsi <= 0.9:
                self.execute_long_trade(bar)
            elif breakout_dir == "short" and current_rsi is not None and 0.65 <= current_rsi <= 0.9:
                self.execute_short_trade(bar)
        
        self._update_visualizer(bar)

    def _handle_daily_bar(self, bar: Bar) -> None:
        self.rsi.handle_bar(bar)  # RSI mit dem neuen Daily-Bar updaten
        self._update_visualizer(bar)

    def execute_long_trade(self, bar: Bar):
        self.log.info("Executing LONG trade: RSI oversold + TTT breakout")
        entry_price = bar.close
        atr = self.breakout_analyser._calc_atr()
        stop_loss = entry_price - 2 * atr
        take_profit = entry_price + 4 * atr

        position_size, _ = self.risk_manager.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )

        self.order_types.submit_long_bracket_order(
            position_size, entry_price, stop_loss, take_profit
        )

    def execute_short_trade(self, bar: Bar):
        self.log.info("Executing SHORT trade: RSI overbought + TTT breakout")
        entry_price = bar.close
        atr = self.breakout_analyser._calc_atr()
        stop_loss = entry_price + 2 * atr
        take_profit = entry_price - 4 * atr

        position_size, _ = self.risk_manager.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )

        self.order_types.submit_short_bracket_order(
            position_size, entry_price, stop_loss, take_profit
        )

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
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")
        self.stopped = True  

        # VISUALIZER UPDATEN
        try:
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        except Exception as e:
            self.log.warning(f"Could not calculate unrealized PnL: {e}")
            unrealized_pnl = None
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()

        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="balance", value=usd_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="RSI", value=float(self.rsi.value) if self.rsi.value is not None else None)
        
        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)


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
    
    def _update_visualizer(self, bar: Bar) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        try:
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        except Exception as e:
            unrealized_pnl = None

        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()

        rsi_value = float(self.rsi.value) if self.rsi.value is not None else None

        if self.rsi.initialized and "1-DAY-LAST-INTERNAL" in str(bar.bar_type):
            self.log.info(f"Saving RSI to collector: {rsi_value} at {bar.ts_event}")
            self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=usd_balance)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)