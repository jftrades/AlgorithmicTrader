# eine simple mean-reversion strategie, 
# die gleichzeitig eine trend following strategie ist durch systematischen Einsatz von Emas und closes

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
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags
from tools.help_funcs.base_strategy import BaseStrategy
from nautilus_trader.common.enums import LogColor


# Strategiespezifische Importe
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from collections import deque

class MeanemaStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: str 
    trade_size_usd: Decimal
    fast_ema_period: int
    slow_ema_period: int
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    min_bars_under_fast_ema: int
    min_bars_over_fast_ema: int
    close_positions_on_stop: bool = True

class MeanemaStrategy(BaseStrategy, Strategy):
    def __init__(self, config:MeanemaStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.trade_size_usd = config.trade_size_usd
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.bar_type = BarType.from_str(config.bar_type)
        self.stopped = False
        self.realized_pnl = 0
        self.bar_counter = 0
        self.fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(config.slow_ema_period)
        self.min_bars_under_fast_ema = config.min_bars_under_fast_ema
        self.last_under_fast_ema = deque(maxlen=self.min_bars_under_fast_ema)
        self.min_bars_over_fast_ema = config.min_bars_over_fast_ema
        self.last_over_fast_ema = deque(maxlen=self.min_bars_over_fast_ema)
        self.prev_close = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.log.info("Strategy started!")

        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)
        self.collector = BacktestDataCollector()

        self.collector.initialise_logging_indicator("fast_ema", 0)
        self.collector.initialise_logging_indicator("slow_ema", 0)
        self.collector.initialise_logging_indicator("position", 1)
        self.collector.initialise_logging_indicator("realized_pnl", 2)
        self.collector.initialise_logging_indicator("unrealized_pnl", 3)
        self.collector.initialise_logging_indicator("balance", 4)

    def get_position(self):
        return self.base_get_position()
    
    def on_bar(self, bar: Bar) -> None:
        if self.fast_ema is not None:
            self.fast_ema.handle_bar(bar)
        if self.slow_ema is not None:
            self.slow_ema.handle_bar(bar)

        open_orders = self.cache.orders_open(instrument_id=self.instrument_id) # Prüfe offene Orders
        if open_orders:
            return
        
        # Bedingung 1: wir müssen unter/über dem slow ema sein
        if bar.close < (self.slow_ema.value if self.slow_ema.value is not None else float('inf')):
            self.long_logic(bar)
            self.check_for_long_exit(bar)

        if bar.close > (self.slow_ema.value if self.slow_ema.value is not None else float('inf')):
            self.short_logic(bar)
            self.check_for_short_exit(bar)

        if bar.close == (self.slow_ema.value if self.slow_ema.value is not None else float('inf')):
            pass
        
        self.update_visualizer_data(bar)

    def long_logic (self, bar):
        trade_size_usd = float(self.config.trade_size_usd)
        qty = max(1, int(float(trade_size_usd) // float(bar.close)))
        if len(self.last_under_fast_ema) == self.min_bars_under_fast_ema:
            if (
                self.prev_close is not None
                and self.fast_ema.value is not None
                and self.prev_close < self.fast_ema.value
                and bar.close >= self.fast_ema.value
                and all(self.last_under_fast_ema)
            ):
                self.order_types.submit_long_market_order(qty)
                self.log.info("Long-Order submitted!")

        if self.fast_ema.value is not None and self.prev_close is not None:
            self.last_under_fast_ema.append(self.prev_close < self.fast_ema.value)
        self.prev_close = bar.close
        
    def short_logic (self, bar):
        trade_size_usd = float(self.config.trade_size_usd)
        qty = max(1, int(float(trade_size_usd) // float(bar.close)))
        if len(self.last_over_fast_ema) == self.min_bars_over_fast_ema:
            if (
                self.prev_close is not None
                and self.fast_ema.value is not None
                and self.prev_close > self.fast_ema.value
                and bar.close <= self.fast_ema.value
                and all(self.last_over_fast_ema)
            ):
                self.order_types.submit_short_market_order(qty)
                self.log.info("Short-Order submitted!")

        if self.fast_ema.value is not None and self.prev_close is not None:
            self.last_over_fast_ema.append(self.prev_close > self.fast_ema.value)
        self.prev_close = bar.close

    def check_for_long_exit (self, bar):
        position = self.get_position()
        if position is None or position.quantity <= 0:
            return
        
        if (
            self.slow_ema.value is not None
            and self.fast_ema.value is not None
            and bar.close > self.slow_ema.value
            and bar.close < self.fast_ema.value
        ): 
            self.order_types.close_position_by_market_order()


    def check_for_short_exit (self,bar):
        position = self.get_position()
        if position is None or position.quantity <= 0:
            return
        
        if (
            self.slow_ema.value is not None
            and self.fast_ema.value is not None
            and bar.close < self.slow_ema.value
            and bar.close > self.fast_ema.value
        ): 
            self.order_types.close_position_by_market_order()

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        return self.base_close_position()
    
    def on_stop(self) -> None:
        self.base_on_stop()
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
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="fast_ema", value=float(self.fast_ema.value) if self.fast_ema.value is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="slow_ema", value=float(self.slow_ema.value) if self.slow_ema.value is not None else None)
        
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
    
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="fast_ema", value=float(self.fast_ema.value) if self.fast_ema.value is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="slow_ema", value=float(self.slow_ema.value) if self.slow_ema.value is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=usd_balance)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)

    def on_reset(self) -> None:
        self.fast_ema.reset()
        self.slow_ema.reset()