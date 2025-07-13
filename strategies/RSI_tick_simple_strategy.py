# hier rein kommt die normale simple RSI strategy, nur mit Tick Daten
# das wird die erste implementuerung von tick Daten

# Standard Library Importe
from decimal import Decimal
from typing import Any
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta, timezone
 
# Nautilus Kern offizielle Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType, TradeTick, QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder, StopMarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderEvent, PositionEvent
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.model.enums import AggressorSide  # für BUY/SELL

# Nautilus Kern eigene Importe !!! immer
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector  # Optional visualization
from tools.help_funcs.help_funcs_strategy import create_tags
from nautilus_trader.common.enums import LogColor

# Weitere/Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from nautilus_trader.model.objects import Currency

class RSITickSimpleStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    tick_buffer_size: int = 1000
    close_positions_on_stop: bool = True 
    
class RSITickSimpleStrategy(Strategy):
    def __init__(self, config: RSITickSimpleStrategyConfig):
        self.base_strategy.base__init__(config)
        self.tick_buffer_size = config.tick_buffer_size 
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.last_rsi_cross = None 
        self.stopped = False  # Flag to indicate if the strategy has been stopped
        self.tick_counter = 0
        self.trade_ticks = []
        self.last_logged_balance = None  # Track last logged balance


    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_trade_ticks(self.instrument_id)
        bar_type = BarType.from_str(f"{self.instrument_id}-5-MINUTE-LAST-INTERNAL")
        self.subscribe_bars(bar_type)
        self.subscribe_trade_ticks(self.instrument_id)
        self.log.info("Tick Strategy started!")

        self.collector = BacktestDataCollector()  # Optional visualization
        self.collector.initialise_logging_indicator("RSI", 1)
        self.collector.initialise_logging_indicator("position", 2)
        self.collector.initialise_logging_indicator("realized_pnl", 3)
        self.collector.initialise_logging_indicator("unrealized_pnl", 4)
        self.collector.initialise_logging_indicator("balance", 5)

        self.base_strategy = BaseStrategy(self)
        self.risk_manager = RiskManager(self, 0.01)
        self.order_types = OrderTypes(self)

        # Get the account using the venue instead of account_id
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        if account:
            usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double()
            self.last_logged_balance = usdt_balance
            self.log.info(f"USDT balance: {usdt_balance}")
        else:
            self.log.warning(f"No account found for venue: {venue}")

    def get_position(self):
        self.base_strategy.base_get_position()

    def on_bar(self, bar: Bar):
        self.rsi.handle_bar(bar)
        self.last_rsi = self.rsi.value if self.rsi.initialized else None
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
        

    def on_trade_tick(self, tick: TradeTick) -> None:  
        rsi_value = self.rsi.value if self.rsi.initialized else None
        if rsi_value is None:
            return  # RSI noch nicht initialisiert, daher keine Logik ausführen
        self.tick_counter += 1
        self.trade_ticks.append(tick)
        if len(self.trade_ticks) > self.tick_buffer_size:
            self.trade_ticks.pop(0)
        
        # Prüfe, ob bereits eine Order offen ist (pending), um Endlos-Orders zu vermeiden
        open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        if open_orders:
            return  # Warten, bis Order ausgeführt ist

        # Entry/Exit-Logik - tick-genau
        if rsi_value > self.rsi_overbought:
            if self.last_rsi_cross != "rsi_overbought":
                self.close_position()
                self.order_types.submit_short_market_order(self.config.trade_size)
            self.last_rsi_cross = "rsi_overbought"
        elif rsi_value < self.rsi_oversold:
            if self.last_rsi_cross != "rsi_oversold":
                self.close_position()
                self.order_types.submit_long_market_order(self.config.trade_size)
            self.last_rsi_cross = "rsi_oversold"

        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double() if account else 0

        self.update_visualizer_data(tick, usdt_balance, rsi_value)
  

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        self.base_strategy.base_close_position()
    
    def on_stop(self) -> None:
        self.base_strategy.base_on_stop()

        self.stopped = True  
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
        realized_pnl = float(self.portfolio.realized_pnl(self.instrument_id))  # Unrealized PnL
        self.realized_pnl += unrealized_pnl+realized_pnl if unrealized_pnl is not None else 0
        unrealized_pnl = 0
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double() 
        
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="balance", value=usdt_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="RSI", value=float(self.last_rsi) if self.last_rsi is not None else None)
        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)
        #self.collector.visualize()  # Visualize the data if enabled

    def on_order_filled(self, order_filled) -> None:
        self.base_strategy.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        self.base_strategy.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        self.base_strategy.base_on_error(error)

    def update_visualizer_data(self, tick: TradeTick, usdt_balance: Decimal, rsi_value: float) -> None:
        # VISUALIZER UPDATE - Jeden Tick für vollständige Tick-Daten
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balances_total()
        #self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)
        
        self.tick_counter += 1
        if self.tick_counter % 1000 == 0:
            self.collector.add_indicator(timestamp=tick.ts_event, name="position", value=net_position)
            self.collector.add_indicator(timestamp=tick.ts_event, name="RSI", value=float(rsi_value))
            self.collector.add_indicator(timestamp=tick.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
            self.collector.add_indicator(timestamp=tick.ts_event, name="realized_pnl", value=float(self.realized_pnl))
            self.collector.add_indicator(timestamp=tick.ts_event, name="balance", value=usdt_balance)