# Standard Library Importe
from decimal import Decimal
from typing import Any

# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType, TradeTick, QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder, StopMarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderEvent, PositionEvent
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.currencies import USDT, BTC

# Weitere/Strategiespezifische Importe
# from nautilus_trader...

class NameDerStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    #...
    close_positions_on_stop: bool = True 
    
class NameDerStrategy(Strategy):
    def __init__(self, config: NameDerStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        if isinstance(config.bar_type, str):
            self.bar_type = BarType.from_str(config.bar_type)
        else:
            self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        #...
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.subscribe_trade_ticks(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)
        self.log.info("Strategy started!")

    def get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None

    def on_bar (self, bar: Bar) -> None: 
        # in on_bar kommt die Handelslogik der Strategie + meistens Positionsmanagement wenn nicht in on_order_event / on_position_event
        pass

    # die weiteren on_Methoden...
    def on_trade_tick(self, tick: TradeTick) -> None:
        pass
    
    def on_quote_tick(self, tick: QuoteTick) -> None:
        pass

    def on_order_book(self, order_book: OrderBook) -> None:
        pass

    def on_order_event(self, event: OrderEvent) -> None:
        pass

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    
    def close_position(self) -> None:
        position = self.get_position()
        if position is not None and position.is_open:
            super().close_position(position)
        
    def on_stop(self) -> None:
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()