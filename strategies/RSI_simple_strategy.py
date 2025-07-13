# Standard Library Importe
from decimal import Decimal
import time
from typing import Any

# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, TradeTick, BarType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.common.enums import LogColor

# Nautilus Strategie spezifische Importe
from tools.structure.TTTbreakout import TTTBreakout_Analyser
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags
from nautilus_trader.common.enums import LogColor

# Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex

# ab hier der Code für die Strategie
class RSISimpleStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    close_positions_on_stop: bool = True
    
    
class RSISimpleStrategy(Strategy):
    def __init__(self, config: RSISimpleStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.close_positions_on_stop = config.close_positions_on_stop
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.last_rsi_cross = None
        self.realized_pnl = 0
        self.stopped = False  # Flag to indicate if the strategy has been stopped

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.subscribe_trade_ticks(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)
        self.log.info("Strategy started!")
        self.collector = BacktestDataCollector()
        self.collector.initialise_logging_indicator("RSI", 1)
        self.collector.initialise_logging_indicator("position", 2)
        self.collector.initialise_logging_indicator("realized_pnl", 3)
        self.collector.initialise_logging_indicator("unrealized_pnl", 4)
        self.collector.initialise_logging_indicator("account_balance", 5)
        self.collector.initialise_logging_indicator("balance", 5)

        self.risk_manager = RiskManager(self, 0.01)
        self.order_types = OrderTypes(self)

        
    def get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None

    def on_bar(self, bar: Bar) -> None:
        self.rsi.handle_bar(bar)
        if not self.rsi.initialized:
            return

        usdt_balance = self.get_account_balance()
        self.risk_manager.update_account_balance(usdt_balance)

        open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        if open_orders:
            return 
        
        self.entry_logic()
        self.update_visualizer_data(Bar, usdt_balance)

    def entry_logic(self, bar: Bar):
        rsi_value = self.rsi.value
        position = self.get_position()
        if rsi_value > self.rsi_overbought:
            if self.last_rsi_cross is not "rsi_overbought":
                self.close_position()
                self.order_types.submit_short_market_order(self.config.trade_size)
            self.last_rsi_cross = "rsi_overbought"
        if rsi_value < self.rsi_oversold:
            if self.last_rsi_cross is not "rsi_oversold":
                self.close_position()
                self.order_types.submit_long_market_order(self.config.trade_size)
            self.last_rsi_cross = "rsi_oversold"

    def update_visualizer_data(self,bar: Bar, sudt_balance: Decimal) -> None:
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
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open)

    def close_position(self) -> None:
        self.order_types.close_position_by_market_order()
        if self.stopped:
            logging_message = self.collector.save_data()
            self.log.info(logging_message, color=LogColor.GREEN)
        

    def on_stop(self) -> None:
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")
        self.stopped = True  
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
        realized_pnl = float(self.portfolio.realized_pnl(self.instrument_id))  # Unrealized PnL
        #self.log.info(f"position.quantity: {net_position}", LogColor.RED)
        self.realized_pnl += unrealized_pnl+realized_pnl if unrealized_pnl is not None else 0
        unrealized_pnl = 0
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double() 
        self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)


        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="account_balance", value=usdt_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

        #self.collector.visualize()  # Visualize the data if enabled

    def on_order_filled(self, order_filled) -> None:
        ret = self.collector.add_trade_details(order_filled)
        self.log.info(
            f"Order filled: {order_filled.commission}", color=LogColor.GREEN)
        

    def on_position_closed(self, position_closed) -> None:
        realized_pnl = position_closed.realized_pnl  # Realized PnL
        self.realized_pnl += float(realized_pnl) if realized_pnl else 0
    

    def on_position_opened(self, position_opened) -> None:
        realized_pnl = position_opened.realized_pnl  # Realized PnL
        #self.realized_pnl += float(realized_pnl) if realized_pnl else 0

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()

