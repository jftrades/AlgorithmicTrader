# wichtig für diese FVG Strategie, wir testen NICHT, ob FVGS allgemein halten
# sondern wir testen, ob, wenn eine FVG respektiert/angetestet wurde, wie gut die continuation dafür ist
# wir kaufen sozusagen nachdem die FVG gehalten hat
# wir können auch in anderen Skripten einen Inverse, den direkten Kauf einer FVG etc testen.

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

# Weitere/Strategiespezifische Importe
# from nautilus_trader...

class FVGSimpleStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    #...
    close_positions_on_stop: bool = True 
    
class FVGSimpleStrategy(Strategy):
    def __init__(self, config: FVGSimpleStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        if isinstance(config.bar_type, str):
            self.bar_type = BarType.from_str(config.bar_type)
        else:
            self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        self.bullish_fvgs = []  # Liste für bullische FVGs (jeweils (high, low))
        self.bearish_fvgs = []  # Liste für bearishe FVGs (jeweils (low, high))
        self.bar_buffer = [] #einfach eine Liste, die die letzten Bars speichert (wird in on_bar genauer definiert und drauf zugegriffen)
        self.close_positions_on_stop = config.close_positions_on_stop

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
        self.bar_buffer.append(bar)
        if len(self.bar_buffer) < 3:
            return
        
        bar_2 = self.bar_buffer[-3]
        bar_1 = self.bar_buffer[-2]
        bar_0 = self.bar_buffer[-1]

        # Bullische FVG
        if bar_0.low > bar_2.high:
            self.log.info(f"Bullische FVG erkannt: Gap von {bar_2.high} bis {bar_0.low}")
            self.bullish_fvgs.append((bar_2.high, bar_0.low))

        # Bearishe FVG
        if bar_0.high < bar_2.low:
            self.log.info(f"Bearishe FVG erkannt: Gap von {bar_2.low} bis {bar_0.high}") 
            self.bearish_fvgs.append((bar_2.high, bar_0.low))
        
        # Buffer auf die letzten 3 Bars begrenzen (pop löscht das letzte Element aus der Liste)
        if len(self.bar_buffer) > 3:
            self.bar_buffer.pop(0)

        position = self.get_position()
        # Bullishe FVG erkennen und Kaufmethode
        for gap in self.bullish_fvgs[:]:
            gap_high, gap_low = gap
            if gap_high <= bar.low <= gap_low:
                self.log.info(f"Retest bullische FVG: {gap}")
                if position is not None and position.is_open:
                    self.close_position()
                else:
                    order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)

                    entry_price = bar.close
                    stop_loss = bar.low  # SL unter das aktuelle Low
                    risk = entry_price - stop_loss
                    take_profit = entry_price + 2 * risk  # TP im 1:2-Ratio

                    # Stop-Loss-Order
                    sl_order = self.order_factory.stop_market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        trigger_price=Price(stop_loss, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sl_order)

                    # Take-Profit-Order
                    tp_order = self.order_factory.limit(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        price=Price(take_profit, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(tp_order)

                self.bullish_fvgs.remove(gap) # FVG nach Retest entfernen
                
            elif bar.low < gap_low:
                self.log.info(f"Bullische FVG durchtraded: {gap}")
                self.bullish_fvgs.remove(gap)  # FVG nach Durchbruch entfernen

        # Bearishe FVG erkennen und Kaufmethode
        for gap in self.bearish_fvgs[:]:
            gap_high, gap_low = gap
            if gap_low <= bar.high <= gap_high:
                self.log.info(f"Retest bearishe FVG: {gap}")
                if position is not None and position.is_open:
                    self.close_position()
                else:
                    order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)

                    entry_price = bar.close
                    stop_loss = bar.high  # SL über das aktuelle high
                    risk = stop_loss - entry_price
                    take_profit = entry_price + 2 * risk  # TP im 1:2-Ratio

                    # Stop-Loss-Order
                    sl_order = self.order_factory.stop_market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        trigger_price=Price(stop_loss, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sl_order)

                    # Take-Profit-Order
                    tp_order = self.order_factory.limit(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        price=Price(take_profit, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(tp_order)

                self.bearish_fvgs.remove(gap) # FVG nach Retest entfernen
                
            elif bar.low < gap_low:
                self.log.info(f"Bearishe FVG durchtraded: {gap}")
                self.bearish_fvgs.remove(gap)  # FVG nach Durchbruch entfernen
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
