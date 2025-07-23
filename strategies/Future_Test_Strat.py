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
from tools.help_funcs.base_strategy import BaseStrategy
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
    
    
class RSISimpleStrategy(BaseStrategy, Strategy):
    def __init__(self, config: RSISimpleStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.bar_type = config.bar_type
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        
        # Multi-Instrument Setup
        self.rsi_indicators = {}  # Pro Instrument ein RSI
        self.last_rsi_cross = {}  # Pro Instrument letzten Cross merken
        
        self.stopped = False 
        self.realized_pnl = 0 

    def on_start(self) -> None:
        # Hole alle verfügbaren Instrument-IDs für die Venue
        self.instrument_ids = self.cache.instrument_ids(self.venue)
        self.log.info(f"Gefundene Instrumente: {len(self.instrument_ids)}")
        
        # Subscribe zu allen Instrumenten und erstelle RSI-Indikatoren
        for instrument_id in self.instrument_ids:
            self.log.info(f"Setup für Instrument: {instrument_id}")
            
            # BarType für jedes Instrument erstellen
            from nautilus_trader.model.data import BarType
            bar_type_str = f"{instrument_id}-5-MINUTE-LAST-EXTERNAL"
            bar_type_obj = BarType.from_str(bar_type_str)
            
            # Subscribe zu Bars
            self.subscribe_bars(bar_type_obj)
            
            # RSI-Indikator pro Instrument
            self.rsi_indicators[instrument_id] = RelativeStrengthIndex(period=self.rsi_period)
            self.last_rsi_cross[instrument_id] = None
            
        self.log.info("Multi-Instrument Strategy started!")
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
        return self.base_get_position()

    def on_bar(self, bar: Bar) -> None:
        # Finde das Instrument für diesen Bar
        bar_instrument_id = bar.bar_type.instrument_id
        self.instrument = self.cache.instrument(bar_instrument_id)
        
        # Update RSI für dieses spezifische Instrument
        rsi = self.rsi_indicators[bar_instrument_id]
        rsi.handle_bar(bar)
        
        if not rsi.initialized:
            return

        # Check für offene Orders für dieses spezifische Instrument
        open_orders = self.cache.orders_open(instrument_id=bar_instrument_id)
        if open_orders:
            return 
        
        # Entry Logic für dieses spezifische Instrument
        self.entry_logic(bar, bar_instrument_id)
        
        # Nur für das erste Instrument (main instrument) Visualizer updaten
        if bar_instrument_id == self.instrument_id:
            self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
            self.update_visualizer_data(bar)

    def entry_logic(self, bar: Bar, instrument_id: InstrumentId):
        rsi = self.rsi_indicators[instrument_id]
        rsi_value = rsi.value
        
        if rsi_value > self.rsi_overbought:
            if self.last_rsi_cross[instrument_id] != "rsi_overbought":
                self.close_position_for_instrument(instrument_id)
                self.submit_short_order(instrument_id)
                self.log.info(f"SHORT Signal für {instrument_id} bei RSI {rsi_value:.2f}")
            self.last_rsi_cross[instrument_id] = "rsi_overbought"
            
        if rsi_value < self.rsi_oversold:
            if self.last_rsi_cross[instrument_id] != "rsi_oversold":
                self.close_position_for_instrument(instrument_id)
                self.submit_long_order(instrument_id)
                self.log.info(f"LONG Signal für {instrument_id} bei RSI {rsi_value:.2f}")
            self.last_rsi_cross[instrument_id] = "rsi_oversold"

    def submit_short_order(self, instrument_id: InstrumentId):
        # Nutze den OrderTypes aber für spezifisches Instrument
        # Temporär setze das aktuelle instrument_id
        original_instrument_id = self.order_types.strategy.instrument_id
        self.order_types.strategy.instrument_id = instrument_id
        self.order_types.submit_short_market_order(self.trade_size)
        self.order_types.strategy.instrument_id = original_instrument_id

    def submit_long_order(self, instrument_id: InstrumentId):
        # Nutze den OrderTypes aber für spezifisches Instrument
        original_instrument_id = self.order_types.strategy.instrument_id
        self.order_types.strategy.instrument_id = instrument_id
        self.order_types.submit_long_market_order(self.trade_size)
        self.order_types.strategy.instrument_id = original_instrument_id

    def close_position_for_instrument(self, instrument_id: InstrumentId):
        # Verwende portfolio.position() statt cache.positions_open()
        position_list = self.cache.positions(instrument_id=instrument_id)
        if not position_list:
            return
        position = position_list[0]
        self.log.info(f"Position für {instrument_id}: {position}")
        
        if position.is_open:
            self.close_position()
            self.log.info(f"Position geschlossen für {instrument_id}")
        else:
            self.log.info(f"Keine offene Position für {instrument_id}")

    def update_visualizer_data(self, bar: Bar) -> None:
        # Verwende die korrekte net_position() Methode mit instrument_id Parameter
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()

        rsi_value = float(self.rsi_indicators[self.instrument_id].value) if self.rsi_indicators[self.instrument_id].value is not None else None

        self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=float(net_position))  # Convert Decimal to float
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=usd_balance)


    def close_position(self) -> None:
        return self.base_close_position()
    
    def on_stop(self) -> None:
        self.base_on_stop()

        self.stopped = True  
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
        realized_pnl = float(self.portfolio.realized_pnl(self.instrument_id))  # Unrealized PnL
        self.realized_pnl += unrealized_pnl+realized_pnl if unrealized_pnl is not None else 0
        unrealized_pnl = 0
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double() 


        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="account_balance", value=usdt_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

        #self.collector.visualize()  # Visualize the data if enabled
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)
        logging_message = self.collector.save_data()

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)


        self.log.info(logging_message, color=LogColor.GREEN)

        #self.collector.visualize()  # Visualize the data if enabled
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

        #return self.base_on_error(error)

