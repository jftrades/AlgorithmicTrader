# Standard Library Importe
from decimal import Decimal
from typing import Any
import pandas as pd

# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, TradeTick, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce

# Nautilus Strategie spezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from nautilus_trader.core.datetime import unix_nanos_to_dt


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
        if isinstance(config.bar_type, str):
            self.bar_type = BarType.from_str(config.bar_type)
        else:
            self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.close_positions_on_stop = config.close_positions_on_stop
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.prev_rsi = None
        self.just_closed = False
    
        # Debug: Welche Attribute/Möglichkeiten gibt es?
        print("STRATEGY DIR:", dir(self))
        if hasattr(self, "portfolio"):
            print("PORTFOLIO DIR:", dir(self.portfolio))

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        #self.subscribe_trade_ticks(self.instrument_id)
        #self.subscribe_quote_ticks(self.instrument_id)
        self.log.info("Strategy started!")

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

        rsi_value = self.rsi.value
        position = self.get_position()

        if self.prev_rsi is not None:
            # LONG ENTRY
            if self.prev_rsi >= self.rsi_oversold and rsi_value < self.rsi_oversold:
                if self.just_closed:
                    self.just_closed = False  # Reset, aber NICHT sofort wieder handeln!
                    return
                if position is not None and position.is_open:
                    if position.quantity < 0:
                        self.close_position()
                        self.just_closed = True  # <--- Flag setzen
                        return
                elif position is None or not position.is_open:
                    self.submit_order(self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    ))
                    return

            # SHORT ENTRY
            elif self.prev_rsi <= self.rsi_overbought and rsi_value > self.rsi_overbought:
                if self.just_closed:
                    self.just_closed = False
                    return
                if position is not None and position.is_open:
                    if position.quantity > 0:
                        self.close_position()
                        self.just_closed = True
                        return
                elif position is None or not position.is_open:
                    self.submit_order(self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    ))
                    return

        self.prev_rsi = rsi_value
    def close_position(self) -> None:
        position = self.get_position()
        if position is not None and position.is_open:
            self.log.info(f"Closing position for {self.instrument_id} at market price.")
            order_side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=order_side,
                quantity=Quantity(abs(position.quantity), self.instrument.size_precision),
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)
        else:
            self.log.info(f"No open position to close for {self.instrument_id}.")

    def on_stop(self) -> None:
        position = self.get_position()
        if position is not None and position.is_open:
            self.log.info(f"Force closing open position at strategy stop for {self.instrument_id}")
            self.close_position()
        self.log.info("Strategy stopped!")

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()

        # Notiz von Ferdi: sowohl def on_trade_tick als auch def on_close_position als auch def on_error
        # sind hier theoreitisch nicht notwendig, da sie nur für die Fehlerbehandlung und das Logging
        # genutzt werden. Ausser natürlich unser Code wird komplexer und wir brauchen sie
        # trotzdem für Praxis genau wie on_start einfach in die Projekt mit einfügen ig

            
