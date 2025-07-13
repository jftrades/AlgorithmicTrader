# ================================================================================
# BAR STRATEGY TEMPLATE - Nautilus Trader
# Minimales Template für Bar-basierte Strategien mit Nautilus Trader
# ================================================================================
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
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags
from nautilus_trader.common.enums import LogColor

# Weitere/Strategiespezifische Importe
# from nautilus_trader...

class NameDerStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    #...
    close_positions_on_stop: bool = True 
    
class NameDerStrategy(BaseStrategy, Strategy):
    def __init__(self, config: NameDerStrategyConfig):
        super().__init__(config)
        self.base_strategy = BaseStrategy(config)
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.bar_type = config.bar_type
        self.bar_counter = 0

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.log.info("Strategy started!")
        self.risk_manager = RiskManager(self)
        self.order_types = OrderTypes(self)
        self.collector = BacktestDataCollector()
        self.collector.initialise_logging_indicator("position", 1)
        self.collector.initialise_logging_indicator("realized_pnl", 2)
        self.collector.initialise_logging_indicator("unrealized_pnl", 3)
        self.collector.initialise_logging_indicator("balance", 4)

    def get_position(self):
        self.base_strategy.base_get_position()

    def on_bar(self, bar: Bar) -> None:
        # Get account balance and update risk manager
        usdt_balance = self.get_account_balance()
        self.risk_manager.update_account_balance(usdt_balance)
        # Strategie Logik aufteilen un z.B. def long_trade, def short_trade
        # diese Hilfsmethoden in on_bar aufrufen
        # und auf die order_types und risk_manager Hilfsmethoden zugreifen
        self.update_visualizer_data(bar, usdt_balance)

    def on_order_event(self, event: OrderEvent) -> None:
        pass

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        return self.base_strategy.base_close_position()
    
    def on_stop(self) -> None:
        self.base_strategy.base_on_stop()

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
        return self.base_strategy.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_strategy.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_strategy.base_on_error(error)
    
    def update_visualizer_data(self, bar: Bar) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id )
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()

        #self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=usd_balance)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)