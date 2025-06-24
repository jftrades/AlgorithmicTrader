#hier werde ich den Code kommplett selber schreiben und nicht mehr Gemini sondern wenn Copilot benutzen

from decimal import Decimal
from typing import Any

from nautilus_trader.trading import Strategy
from nautilus_trader.model.data import Bar, TradeTick, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity, PositiveInt, PositiveFloat
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.indicators.rsi import RelativeStrengthIndex

class RSISimpleStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    rsi_period:PositiveInt
    rsi_overbought:PositiveFloat
    rsi_oversold:PositiveFloat
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
    
    def on_start(self) -> None:
        self.log.info("Strategy started!")
        self.subscribe_bars(self.instrument_id, self.bar_type)
        self.subscribe_trade_ticks(self.instrument_id)

    def on_bar(self, bar: Bar) -> None:
        self.rsi.handle_bar(bar)
        if not self.rsi.is_initialized:
            return
        
        rsi_value = self.rsi.value # RSI Value muss nicht in __init__ sein, da es eine Eigenschaft des RSI Indikators ist
        
        if self.has_open_orders:
            self.log.debug("Open order exists, skipping new signal.")
            return
    
        if rsi_value > self.rsi_overbought:
            if self.position.is_open:
                self.close_position()
            else:
                self.sell(
                    instrument_id=self.instrument_id,
                    quantity=Quantity(self.trade_size),
                    price=Price(bar.close_price)
                )
        if rsi_value < self.rsi_oversold:
            if self.position.is_open:
                self.close_position()
            else:
                self.buy(
                    instrument_id=self.instrument_id,
                    quantity=Quantity(self.trade_size),
                    price=Price(bar.close_price)
                )
    def on_order_event(self, event: Any)-> None:
        if event.is_filled:
            self.log.info(f"Order filled: {event.order_id} for {event.instrument_id} at {event.price}")
        elif event.is_canceled:
            self.log.info(f"Order canceled: {event.order_id} for {event.instrument_id}")
        elif event.is_rejected:
            self.log.error(f"Order rejected: {event.order_id} for {event.instrument_id}")
            
    def on_trade_tick(self, trade_tick: TradeTick) -> None:
        self.log.debug(f"Trade tick received: {trade_tick.instrument_id} at {trade_tick.price}")
        self.rsi.handle_trade_tick(trade_tick)

    def on_stop(self) -> None:
        if self.close_positions_on_stop and self.position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")
    
    def close_position(self) -> None:
        if self.position.is_open:
            self.log.info(f"Closing position for {self.instrument_id} at market price.")
            self.market_order(
                instrument_id=self.instrument_id,
                quantity=self.position.quantity
            )
        else:
            self.log.info(f"No open position to close for {self.instrument_id}.")

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        if self.close_positions_on_stop and self.position.is_open:
            self.close_position()
        self.stop()

        # Notiz von Ferdi: sowohl def on_trade_tick als auch def on_close_position als auch def on_error
        # sind hier theoreitisch nicht notwendig, da sie nur für die Fehlerbehandlung und das Logging
        # genutzt werden. Ausser natürlich unser Code wird komplexer und wir brauchen sie
        # trotzdem für Praxis genau wie on_start einfach in die Projekt mit einfügen ig

            
