# eine unproitable und unangepasste Strategie die mit RSI und dem TTTBreakout simpel long term nach trades sucht.

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
from tools.help_funcs.base_strategy import BaseStrategy
from nautilus_trader.common.enums import LogColor


# Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex


class MeanRSITTTStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: str 
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    ttt_lookback: int
    ttt_atr_mult: float
    ttt_max_counter: int 
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    risk_reward_ratio: float
    close_positions_on_stop: bool = True

class MeanRSITTTStrategy(BaseStrategy, Strategy):
    def __init__(self, config:MeanRSITTTStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.bar_type = BarType.from_str(config.bar_type)
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.last_rsi_cross = None
        self.stopped = False
        self.realized_pnl = 0
        self.bar_counter = 0
        self.breakout_analyser = TTTBreakout_Analyser(
            lookback=config.ttt_lookback,
            atr_mult=config.ttt_atr_mult,
            max_counter=config.ttt_max_counter
        )
        

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.log.info("Strategy started!")

        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
            Decimal(str(self.config.risk_reward_ratio))
        )
        self.order_types = OrderTypes(self)
        self.collector = BacktestDataCollector()
 
        self.collector.initialise_logging_indicator("RSI", 1)
        self.collector.initialise_logging_indicator("position", 2)
        self.collector.initialise_logging_indicator("realized_pnl", 3)
        self.collector.initialise_logging_indicator("unrealized_pnl", 4)
        self.collector.initialise_logging_indicator("balance", 5)

    def get_position(self):
        return self.base_get_position()
    
    def on_bar(self, bar: Bar) -> None:
        self.breakout_analyser.update_bars(bar)

        self.rsi.handle_bar(bar) 
        self.update_visualizer_data(bar)

        is_breakout, breakout_dir = self.breakout_analyser.is_tttbreakout() # TTT Breakout prüfen

        open_orders = self.cache.orders_open(instrument_id=self.instrument_id) # Prüfe offene Orders
        if open_orders:
            return

        if not self.rsi.initialized:
                self.log.warning("RSI not initialized yet - skipping trading logic")
                return

        if is_breakout:
            current_rsi = self.rsi.value
            if breakout_dir == "long" and current_rsi is not None and 0.6 <= current_rsi <= 0.9:
                self.execute_long_trade(bar)
            elif breakout_dir == "short" and current_rsi is not None and 0. <= current_rsi <= 0.9:
                self.execute_short_trade(bar)
        
        self.update_visualizer_data(bar)

    def execute_long_trade(self, bar: Bar):
        self.log.info("Executing LONG trade: RSI oversold + TTT breakout")
        entry_price = bar.close
        atr = self.breakout_analyser._calc_atr()
        stop_loss = entry_price - 3 * atr
        take_profit = entry_price + 25 * atr

        position_size, _ = self.risk_manager.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )

        self.order_types.submit_long_bracket_order(position_size, entry_price, stop_loss, take_profit)

    def execute_short_trade(self, bar: Bar):
        self.log.info("Executing SHORT trade: RSI overbought + TTT breakout")
        entry_price = bar.close
        atr = self.breakout_analyser._calc_atr()
        stop_loss = entry_price + 3 * atr
        take_profit = entry_price - 5 * atr

        position_size, _ = self.risk_manager.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )

        self.order_types.submit_short_bracket_order(position_size, entry_price, stop_loss, take_profit)

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        return self.base_close_position()
    
    def on_stop(self) -> None:
        self.base_on_stop()
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
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def update_visualizer_data(self, bar: Bar) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()

        rsi_value = float(self.rsi.value) if self.rsi.value is not None else None

    
        self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=usd_balance)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)