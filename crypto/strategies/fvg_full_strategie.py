# fvg_full_strategie.py

from decimal import Decimal
from collections import deque
from typing import Deque, Optional, Tuple

from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, ClientId
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import Order
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, OrderStatus
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.events import OrderEvent
from nautilus_trader.config import PositiveInt, PositiveFloat


class FVGStrategyConfig(StrategyConfig):
    instrument_id: str
    bar_type: str
    trade_size_base: Decimal
    fvg_min_size_pips: PositiveInt
    entry_offset_pips: int
    stop_loss_pips: PositiveInt
    take_profit_ratio: PositiveFloat


class FVGStrategy(Strategy):
    def __init__(self, config: FVGStrategyConfig):
        super().__init__(config)
        # self.config ist bereits durch super() gesetzt und korrekt typisiert

        self._instrument_id_obj: InstrumentId = InstrumentId.from_str(self.config.instrument_id)
        self._bar_type_obj: BarType = BarType.from_str(self.config.bar_type)
        self._trade_size_base_qty: Quantity = Quantity(self.config.trade_size_base, precision=8)
        self._fvg_min_size_pips: int = self.config.fvg_min_size_pips
        self._entry_offset_pips: int = self.config.entry_offset_pips
        self._stop_loss_pips: int = self.config.stop_loss_pips
        self._take_profit_ratio_decimal: Decimal = Decimal(str(self.config.take_profit_ratio))

        self._instrument: Optional[Instrument] = None
        self._pip_value: Optional[Price] = None
        self._price_precision: Optional[int] = None
        self._bar_buffer: Deque[Bar] = deque(maxlen=3)
        self._active_entry_order: Optional[Order] = None
        self._active_stop_loss_order: Optional[Order] = None
        self._active_take_profit_order: Optional[Order] = None

        self.log.info(f"Initialized FVGStrategy ({self.id}) with config: {self.config.dict()}")

    def on_start(self) -> None:
        self.log.info(f"FVGStrategy ({self.id}) starting...")
        self._instrument = self.cache.instrument(self._instrument_id_obj)
        if self._instrument is None:
            self.log.error(f"Instrument {self._instrument_id_obj} not found. Strategy stopping.")
            self.stop()
            return

        self._pip_value = self._instrument.price_increment
        self._price_precision = self._instrument.price_precision

        if self._pip_value is None or self._pip_value == Decimal("0"):
            self.log.error(f"Pip value for {self._instrument.id} is invalid. Strategy stopping.")
            self.stop()
            return

        if self._instrument.size_increment and self._instrument.size_increment.precision is not None:
            instrument_size_precision = self._instrument.size_increment.precision
            self._trade_size_base_qty = Quantity(self.config.trade_size_base, precision=instrument_size_precision)
            self.log.info(f"Refined trade size: {self._trade_size_base_qty} (Precision: {instrument_size_precision})")
        else:
            self.log.warning(f"Instrument {self._instrument.id} has no size_increment or precision. Using default: {self._trade_size_base_qty.precision}")

        self.log.info(f"Instrument: {self._instrument.id}, PipVal: {self._pip_value}, PxPrec: {self._price_precision}, TradeQty: {self._trade_size_base_qty}")

        # Verwende einen konsistenten Namen für das ClientId-Objekt
        current_client_id = ClientId(str(self.id)) 

        self.subscribe_instrument(
            instrument_id=self._instrument_id_obj,
            client_id=current_client_id 
        )
        self.log.info(f"Subscribed to instrument {self._instrument_id_obj} with client_id {current_client_id}")

        # Wir versuchen es mit subscribe_bars, um die DataEngine-Warnung zu umgehen
        self.subscribe_bars(
            bar_type=self._bar_type_obj,
            client_id=current_client_id
        )
        self.log.info(f"Subscribed to bars for {self._bar_type_obj} with client_id {current_client_id}")
        
        # request_bars ist vorerst auskommentiert, da es die Warnung verursachte
        # self.request_bars(
        #     bar_type=self._bar_type_obj,
        #     client_id=current_client_id
        # )
        # self.log.info(f"Requested bars for {self._bar_type_obj} with client_id {current_client_id}")

    def on_bar(self, bar: Bar) -> None:
        self.log.info(f"on_bar: New Bar: ts_event={bar.ts_event}, Close={bar.close}")
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < 3:
            return

        fvg_details = self._check_for_fvg()
        if fvg_details:
            side, low_b, high_b = fvg_details
            self.log.info(f"FVG at {bar.ts_event}: Side={side.name}, Low={low_b}, High={high_b}")
            self._handle_fvg_entry(direction=side, fvg_low_boundary=low_b, fvg_high_boundary=high_b)
        else:
            self.log.info(f"on_bar: No FVG detected by _check_for_fvg() for pattern ending at {bar.close_time}")
    
    def _check_for_fvg(self) -> Optional[Tuple[OrderSide, Price, Price]]:
        c1: Bar = self._bar_buffer[0]
        c3: Bar = self._bar_buffer[2]
        self.log.info(f"_check_for_fvg: c1(H={c1.high}, L={c1.low}), c3(H={c3.high}, L={c3.low})")

        direction: Optional[OrderSide] = None
        fvg_low_boundary: Optional[Price] = None
        fvg_high_boundary: Optional[Price] = None

        if c3.low > c1.high:
            self.log.info(f"_check_for_fvg: Potential Bullish: c3.L({c3.low}) > c1.H({c1.high})")
            direction = OrderSide.BUY
            fvg_low_boundary = c1.high
            fvg_high_boundary = c3.low
        elif c3.high < c1.low:
            self.log.info(f"_check_for_fvg: Potential Bearish: c3.H({c3.high}) < c1.L({c1.low})")
            direction = OrderSide.SELL
            fvg_low_boundary = c3.high
            fvg_high_boundary = c1.low

        if direction:
            fvg_size_price_units = fvg_high_boundary - fvg_low_boundary
            fvg_size_pips: Optional[Decimal] = None
            if self._pip_value and not self._pip_value == Decimal("0"):
                try:
                    fvg_size_pips = Decimal(str(float(fvg_size_price_units) / float(self._pip_value)))
                except Exception as e:
                    self.log.error(f"_check_for_fvg: Error calculating fvg_size_pips - {e}")
                    return None
            else:
                self.log.warning("_check_for_fvg: Pip value invalid for FVG size calc.")
                return None
            
            self.log.info(f"_check_for_fvg: Potential {direction.name} FVG. Size PxUnits: {fvg_size_price_units}, Pips: {fvg_size_pips}")
            if fvg_size_pips >= self.config.fvg_min_size_pips:
                self.log.info(f"_check_for_fvg: FVG VALID. Size: {fvg_size_pips:.2f} pips.")
                return direction, fvg_low_boundary, fvg_high_boundary
            else:
                self.log.info(f"_check_for_fvg: FVG too small: {fvg_size_pips:.2f} < {self.config.fvg_min_size_pips} pips.")
        return None

    def _handle_fvg_entry(self, direction: OrderSide, fvg_low_boundary: Price, fvg_high_boundary: Price) -> None:

        if self._active_entry_order and self._active_entry_order.is_active:
            self.log.debug(f"Active entry order {self._active_entry_order.id} exists. Skipping.")
            return
        current_pos = self.portfolio.get_position(self._instrument_id_obj)
        if current_pos and not current_pos.is_flat:
            self.log.debug(f"Position for {self._instrument_id_obj} exists: {current_pos.quantity}. Skipping.")
            return

        offset_val = self._pip_value * self.config.entry_offset_pips # Price-Objekt
        entry_px: Price
        if direction == OrderSide.BUY:
            entry_px = fvg_high_boundary - offset_val
        elif direction == OrderSide.SELL:
            entry_px = fvg_low_boundary + offset_val
        else:
            self.log.error(f"Invalid direction: {direction} for FVG entry.")
            return

        entry_px = entry_px.round(self._price_precision)
        if entry_px <= Price(Decimal("0"), entry_px.precision): # Sicherer Vergleich mit Price(0)
            self.log.warning(f"Calculated entry price {entry_px} is zero or negative. Skipping.")
            return

        self.log.info(f"Attempting {direction.name} LIMIT: Qty={self._trade_size_base_qty}, Px={entry_px}")
        try:
            order = self.submit_order(
                instrument_id=self._instrument_id_obj, order_type=OrderType.LIMIT,
                order_side=direction, quantity=self._trade_size_base_qty,
                price=entry_px, time_in_force=TimeInForce.GTC,
            )
            self._active_entry_order = order
            self.log.info(f"Submitted entry order: {order.id} ({order.status.name})")
        except Exception as e:
            self.log.error(f"Error submitting entry order: {e}")

    def _place_stop_loss_and_take_profit(self, filled_entry_order: Order) -> None:
        entry_px_filled = filled_entry_order.avg_px_filled()
        entry_side = filled_entry_order.side
        trade_qty = filled_entry_order.quantity_filled()

        if trade_qty == Quantity(Decimal("0"), trade_qty.precision): # Sicherer Vergleich mit Quantity(0)
            self.log.error(f"Cannot place SL/TP, filled quantity is zero for order {filled_entry_order.id}.")
            return

        sl_offset_px = self._pip_value * self.config.stop_loss_pips # Price-Objekt
        sl_px: Price
        tp_px: Price

        if entry_side == OrderSide.BUY:
            sl_px = entry_px_filled - sl_offset_px
            tp_dist_px = sl_offset_px * self._take_profit_ratio_decimal # Price * Decimal -> Price
            tp_px = entry_px_filled + tp_dist_px
        elif entry_side == OrderSide.SELL:
            sl_px = entry_px_filled + sl_offset_px
            tp_dist_px = sl_offset_px * self._take_profit_ratio_decimal
            tp_px = entry_px_filled - tp_dist_px
        else:
            self.log.error(f"Invalid side for filled order {filled_entry_order.id}. Cannot place SL/TP.")
            return

        sl_px = sl_px.round(self._price_precision)
        tp_px = tp_px.round(self._price_precision)

        if sl_px <= Price(Decimal("0"), sl_px.precision) or tp_px <= Price(Decimal("0"), tp_px.precision):
            self.log.error(f"SL ({sl_px}) or TP ({tp_px}) is zero/negative. Not placing.")
            return

        opposite_side = OrderSide.opposite(entry_side)
        self.log.info(f"Placing SL/TP for entry {filled_entry_order.id}: SL@{sl_px}, TP@{tp_px}, Qty={trade_qty}")

        try:
            sl_order = self.submit_order(
                instrument_id=self._instrument_id_obj, order_type=OrderType.STOP_MARKET,
                order_side=opposite_side, quantity=trade_qty,
                stop_price=sl_px, time_in_force=TimeInForce.GTC,
            )
            self._active_stop_loss_order = sl_order
            self.log.info(f"Submitted SL: {sl_order.id} ({sl_order.status.name})")
        except Exception as e:
            self.log.error(f"Error submitting SL order: {e}")

        try:
            tp_order = self.submit_order(
                instrument_id=self._instrument_id_obj, order_type=OrderType.LIMIT,
                order_side=opposite_side, quantity=trade_qty,
                price=tp_px, time_in_force=TimeInForce.GTC,
            )
            self._active_take_profit_order = tp_order
            self.log.info(f"Submitted TP: {tp_order.id} ({tp_order.status.name})")
        except Exception as e:
            self.log.error(f"Error submitting TP order: {e}")

    def on_order_event(self, event: OrderEvent) -> None:
        order = event.order
        self.log.info(f"OrderEvent: ID={order.id}, Status={order.status.name}, AvgPx={order.avg_px_filled()}, FilledQty={order.quantity_filled()}")

        if self._active_entry_order and order.id == self._active_entry_order.id:
            if order.status == OrderStatus.FILLED:
                self.log.info(f"Entry order {order.id} FILLED.")
                entry_order_filled = self._active_entry_order
                self._active_entry_order = None
                self._place_stop_loss_and_take_profit(entry_order_filled)
            elif order.status == OrderStatus.CANCELED or order.status == OrderStatus.REJECTED:
                self.log.warning(f"Entry order {order.id} {order.status.name}. Reason: {order.reject_reason}")
                self._active_entry_order = None
            return

        if self._active_stop_loss_order and order.id == self._active_stop_loss_order.id:
            if order.status == OrderStatus.FILLED:
                self.log.info(f"Stop-Loss order {order.id} FILLED.")
                if self._active_take_profit_order and self._active_take_profit_order.is_active:
                    self.cancel_order(self._active_take_profit_order.id)
                    self.log.info(f"Canceled TP order {self._active_take_profit_order.id} (SL filled).")
                self._active_stop_loss_order = None
                self._active_take_profit_order = None
            elif order.status == OrderStatus.CANCELED or order.status == OrderStatus.REJECTED:
                self.log.warning(f"Stop-Loss order {order.id} {order.status.name}.")
                self._active_stop_loss_order = None
            return

        if self._active_take_profit_order and order.id == self._active_take_profit_order.id:
            if order.status == OrderStatus.FILLED:
                self.log.info(f"Take-Profit order {order.id} FILLED.")
                if self._active_stop_loss_order and self._active_stop_loss_order.is_active:
                    self.cancel_order(self._active_stop_loss_order.id)
                    self.log.info(f"Canceled SL order {self._active_stop_loss_order.id} (TP filled).")
                self._active_take_profit_order = None
                self._active_stop_loss_order = None
            elif order.status == OrderStatus.CANCELED or order.status == OrderStatus.REJECTED:
                self.log.warning(f"Take-Profit order {order.id} {order.status.name}.")
                self._active_take_profit_order = None
            return

    def on_stop(self) -> None:
        self.log.info(f"FVGStrategy ({self.id}) stopping...")
        if self._active_entry_order and self._active_entry_order.is_active:
            self.cancel_order(self._active_entry_order.id)
            self.log.info(f"Requested cancel for active entry order: {self._active_entry_order.id}")
        if self._active_stop_loss_order and self._active_stop_loss_order.is_active:
            self.cancel_order(self._active_stop_loss_order.id)
            self.log.info(f"Requested cancel for active SL order: {self._active_stop_loss_order.id}")
        if self._active_take_profit_order and self._active_take_profit_order.is_active:
            self.cancel_order(self._active_take_profit_order.id)
            self.log.info(f"Requested cancel for active TP order: {self._active_take_profit_order.id}")
        self.log.info("Finished requesting cancels for any active orders.")

    def on_shutdown(self) -> None:
        self.log.info(f"FVGStrategy ({self.id}) shutting down...")