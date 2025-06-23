# fvg_full_strategie.py
#funktioniert btw nach wie vor noch nicht wie es soll aber ich werde es nutzen um die anderen Codes zu schreiben 
# so bisschen als Orientierung

from decimal import Decimal
from collections import deque
from typing import Deque, Optional, Tuple

from nautilus_trader.model.identifiers import InstrumentId, ClientId, ClientOrderId, StrategyId
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
    # Stelle sicher, dass strategy_id hier nicht benötigt wird,
    # da es normalerweise von der Engine zugewiesen wird.
    # Wenn du es im Backtest-Skript übergibst, kannst du es hier definieren:
    # strategy_id: Optional[str] = None # Wird dann in __init__ für self.id verwendet


class FVGStrategy(Strategy):
    def __init__(self, config: FVGStrategyConfig):
        super().__init__(config) # Ruft Strategy.__init__ auf, die self.id (eine StrategyId) setzt

        self._instrument_id_obj: InstrumentId = InstrumentId.from_str(self.config.instrument_id)
        self._bar_type_obj: BarType = BarType.from_str(self.config.bar_type)
        self._trade_size_base_qty: Quantity = Quantity(self.config.trade_size_base, precision=8) # Präzision wird in on_start verfeinert
        self._fvg_min_size_pips: int = self.config.fvg_min_size_pips
        self._entry_offset_pips: int = self.config.entry_offset_pips
        self._stop_loss_pips: int = self.config.stop_loss_pips
        self._take_profit_ratio_decimal: Decimal = Decimal(str(self.config.take_profit_ratio))

        self._instrument: Optional[Instrument] = None
        self._pip_value: Optional[Price] = None
        self._price_precision: Optional[int] = None
        self._bar_buffer: Deque[Bar] = deque(maxlen=3)

        self._active_entry_cid: Optional[ClientOrderId] = None
        self._active_entry_order: Optional[Order] = None
        self._active_stop_loss_cid: Optional[ClientOrderId] = None
        self._active_stop_loss_order: Optional[Order] = None
        self._active_take_profit_cid: Optional[ClientOrderId] = None
        self._active_take_profit_order: Optional[Order] = None
        self._waiting_for_entry_fill_to_place_sl_tp: bool = False

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

        # Korrigierte Prüfung für self._pip_value == 0
        if self._pip_value is None or self._pip_value == Price(Decimal("0"), self._pip_value.precision):
            self.log.error(f"Pip value for {self._instrument.id} is invalid or zero. Strategy stopping.")
            self.stop()
            return

        if self._instrument.size_increment and self._instrument.size_increment.precision is not None:
            instrument_size_precision = self._instrument.size_increment.precision
            self._trade_size_base_qty = Quantity(self.config.trade_size_base, precision=instrument_size_precision)
        self.log.info(f"Instrument: {self._instrument.id}, PipVal: {self._pip_value}, PxPrec: {self._price_precision}, TradeQty: {self._trade_size_base_qty}")

        # Korrigierte ClientId für Subscriptions
        # self.id ist eine StrategyId. Wir brauchen eine ClientId.
        # Wenn die StrategyId im Backtest-Setup (STRATEGY_INSTANCE_ID_STR) mit der
        # client_id in BacktestDataConfig übereinstimmt, ist das der richtige Weg.
        try:
            # Versuche, eine ClientId direkt aus der StrategyId-Zeichenkette zu erstellen.
            # Dies funktioniert, wenn die Zeichenkettendarstellung von StrategyId für ClientId gültig ist.
            current_client_id_for_subscription = ClientId(str(self.id))
        except Exception as e:
            self.log.error(f"Konnte ClientId nicht aus StrategyId '{self.id}' erstellen: {e}. Strategy stopping.", exc_info=True)
            self.stop()
            return

        self.log.info(f"Using ClientID '{current_client_id_for_subscription}' for data subscriptions (derived from StrategyID '{self.id}').")

        self.subscribe_instrument(instrument_id=self._instrument_id_obj, client_id=current_client_id_for_subscription)
        self.log.info(f"Subscribed to instrument {self._instrument_id_obj} with client_id {current_client_id_for_subscription}")

        self.subscribe_bars(bar_type=self._bar_type_obj, client_id=current_client_id_for_subscription)
        self.log.info(f"Subscribed to bars for {self._bar_type_obj} with client_id {current_client_id_for_subscription}")

    # In deiner FVGStrategy Klasse (fvg_full_strategie.py)

    def on_bar(self, bar: Bar) -> None:
        self.log.info(f"DEBUG: dir(bar) = {dir(bar)}")

        current_bar_display_timestamp = bar.ts_event

        self.log.info(f"on_bar: New Bar received. ts_event={bar.ts_event}, Close={bar.close}. (Using ts_event as placeholder for bar time: {current_bar_display_timestamp})")
        
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < 3:
            self.log.debug(f"Bar buffer size {len(self._bar_buffer)}/3. Waiting for more bars. Current bar (event time): {current_bar_display_timestamp}")
            return

        fvg_details = self._check_for_fvg()
        if fvg_details:
            side, low_b, high_b = fvg_details
            self.log.info(f"FVG detected for bar ending around {current_bar_display_timestamp}: Side={side.name}, FVG_LowBoundary={low_b}, FVG_HighBoundary={high_b}")
            self._handle_fvg_entry(direction=side, fvg_low_boundary=low_b, fvg_high_boundary=high_b)
        else:
            self.log.info(f"No FVG detected for 3-bar pattern ending around {current_bar_display_timestamp}")
            
    def _check_for_fvg(self) -> Optional[Tuple[OrderSide, Price, Price]]:
        c1: Bar = self._bar_buffer[0]
        c3: Bar = self._bar_buffer[2]

        direction: Optional[OrderSide] = None
        fvg_low_boundary: Optional[Price] = None
        fvg_high_boundary: Optional[Price] = None

        if c3.low > c1.high: # Bullish FVG
            direction = OrderSide.BUY
            fvg_low_boundary = c1.high
            fvg_high_boundary = c3.low
        elif c3.high < c1.low: # Bearish FVG
            direction = OrderSide.SELL
            fvg_low_boundary = c3.high
            fvg_high_boundary = c1.low

        if direction:
            fvg_size_price_units = fvg_high_boundary - fvg_low_boundary # Ergibt Decimal
            
            # Korrigierte Prüfung für self._pip_value == 0
            if not self._pip_value or self._pip_value == Price(Decimal("0"), self._pip_value.precision):
                self.log.warning("_check_for_fvg: Pip value invalid or zero for FVG size calc.")
                return None
            
            try:
                val_fvg_size = Decimal(str(fvg_size_price_units)) if not isinstance(fvg_size_price_units, Decimal) else fvg_size_price_units
                val_pip = Decimal(str(self._pip_value)) if not isinstance(self._pip_value, Decimal) else self._pip_value
                if val_pip == Decimal("0"): # Zusätzliche Sicherheit
                    self.log.warning("_check_for_fvg: Converted pip value is zero.")
                    return None
                fvg_size_pips = (val_fvg_size / val_pip).normalize()
            except Exception as e:
                self.log.error(f"_check_for_fvg: Error calculating fvg_size_pips - {e}", exc_info=True)
                return None
            
            if fvg_size_pips >= self.config.fvg_min_size_pips:
                self.log.info(f"_check_for_fvg: {direction.name} FVG VALID. Size: {fvg_size_pips:.2f} pips.")
                return direction, fvg_low_boundary, fvg_high_boundary
            else:
                self.log.debug(f"_check_for_fvg: FVG too small: {fvg_size_pips:.2f} < {self.config.fvg_min_size_pips} pips.")
        return None

    def _handle_fvg_entry(self, direction: OrderSide, fvg_low_boundary: Price, fvg_high_boundary: Price) -> None:
        if self._active_entry_cid or self._waiting_for_entry_fill_to_place_sl_tp:
            self.log.debug(f"Active entry order CID {self._active_entry_cid} or waiting for fill. Skipping new entry.")
            return

        if not self.portfolio.is_flat(self._instrument_id_obj):
            self.log.debug(f"Position for {self._instrument_id_obj} exists (not flat). Skipping entry.")
            return

        offset_val_calculated = self._pip_value * self.config.entry_offset_pips # Price * int -> Decimal
        offset_val = Price(offset_val_calculated, self._price_precision) # Zu Price konvertieren

        entry_px_calculated: object
        if direction == OrderSide.BUY:
            entry_px_calculated = fvg_high_boundary - offset_val # Price - Price -> Decimal
        elif direction == OrderSide.SELL:
            entry_px_calculated = fvg_low_boundary + offset_val # Price + Price -> Decimal
        else:
            self.log.error(f"Invalid direction: {direction} for FVG entry.")
            return
        
        # Zu Price mit korrekter Präzision konvertieren (Rundung erfolgt implizit)
        entry_px = Price(Decimal(str(entry_px_calculated)), self._price_precision)
        
        if entry_px <= Price(Decimal("0"), entry_px.precision):
            self.log.warning(f"Calculated entry price {entry_px} is zero or negative. Skipping.")
            return

        self.log.info(f"Attempting {direction.name} LIMIT: Qty={self._trade_size_base_qty}, Px={entry_px}")
        try:
            entry_order_to_submit = self.order_factory.limit(
                instrument_id=self._instrument_id_obj,
                order_side=direction,
                quantity=self._trade_size_base_qty,
                price=entry_px,
                time_in_force=TimeInForce.GTC
            )
            self.submit_order(order=entry_order_to_submit) # submit_order() erwartet 'order='
            self._active_entry_cid = entry_order_to_submit.client_order_id
            self._waiting_for_entry_fill_to_place_sl_tp = True
            self.log.info(f"Submitted entry order with ClientOrderID: {self._active_entry_cid}")
        except Exception as e:
            self.log.error(f"Error submitting entry order: {e}", exc_info=True)

    def _place_stop_loss_and_take_profit(self, filled_entry_order: Order) -> None:
        entry_px_filled = filled_entry_order.avg_px_filled()
        entry_side = filled_entry_order.side
        trade_qty = filled_entry_order.quantity_filled()

        if trade_qty == Quantity(Decimal("0"), trade_qty.precision): # Oder trade_qty.is_zero() wenn verfügbar
            self.log.error(f"Cannot place SL/TP, filled quantity is zero for order {filled_entry_order.id}.")
            return

        sl_offset_val_calculated = self._pip_value * self.config.stop_loss_pips # Decimal
        sl_offset_px = Price(sl_offset_val_calculated, self._price_precision)   # Price

        # Price * Decimal -> Price oder Decimal? Annahme: Price, sonst anpassen
        tp_dist_calculated = sl_offset_px * self._take_profit_ratio_decimal
        tp_dist_px = Price(Decimal(str(tp_dist_calculated)), self._price_precision) # Zu Price sicher konvertieren

        sl_px_calc: object
        tp_px_calc: object
        if entry_side == OrderSide.BUY:
            sl_px_calc = entry_px_filled - sl_offset_px # Decimal
            tp_px_calc = entry_px_filled + tp_dist_px # Decimal
        elif entry_side == OrderSide.SELL:
            sl_px_calc = entry_px_filled + sl_offset_px # Decimal
            tp_px_calc = entry_px_filled - tp_dist_px # Decimal
        else:
            self.log.error(f"Invalid side for filled order {filled_entry_order.id}. Cannot place SL/TP.")
            return

        sl_px = Price(Decimal(str(sl_px_calc)), self._price_precision)
        tp_px = Price(Decimal(str(tp_px_calc)), self._price_precision)

        if sl_px <= Price(Decimal("0"), sl_px.precision) or tp_px <= Price(Decimal("0"), tp_px.precision):
            self.log.error(f"SL ({sl_px}) or TP ({tp_px}) is zero/negative. Not placing.")
            return

        opposite_side = OrderSide.opposite(entry_side)
        self.log.info(f"Placing SL/TP for entry {filled_entry_order.id}: SL@{sl_px}, TP@{tp_px}, Qty={trade_qty}")

        try:
            sl_order_to_submit = self.order_factory.stop_market(
                instrument_id=self._instrument_id_obj, order_side=opposite_side,
                quantity=trade_qty, stop_price=sl_px, time_in_force=TimeInForce.GTC )
            self.submit_order(order=sl_order_to_submit)
            self._active_stop_loss_cid = sl_order_to_submit.client_order_id
            self.log.info(f"Submitted SL with ClientOrderID: {self._active_stop_loss_cid}")
        except Exception as e:
            self.log.error(f"Error submitting SL order: {e}", exc_info=True)

        try:
            tp_order_to_submit = self.order_factory.limit(
                instrument_id=self._instrument_id_obj, order_side=opposite_side,
                quantity=trade_qty, price=tp_px, time_in_force=TimeInForce.GTC )
            self.submit_order(order=tp_order_to_submit)
            self._active_take_profit_cid = tp_order_to_submit.client_order_id
            self.log.info(f"Submitted TP with ClientOrderID: {self._active_take_profit_cid}")
        except Exception as e:
            self.log.error(f"Error submitting TP order: {e}", exc_info=True)

    def on_order_event(self, event: OrderEvent) -> None:
        order = event.order
        self.log.info(f"OrderEvent: ClientOrderID={order.client_order_id}, Status={order.status.name}, AvgPx={order.avg_px_filled()}, FilledQty={order.quantity_filled()}")

        if self._active_entry_cid and order.client_order_id == self._active_entry_cid:
            self._active_entry_order = order # Update mit dem neuesten Order-Objekt
            if order.status == OrderStatus.FILLED:
                self.log.info(f"Entry order {order.client_order_id} FILLED.")
                self._place_stop_loss_and_take_profit(order) # Pass das gefüllte Order-Objekt
                self._active_entry_cid = None # Nicht mehr aktiv für neue Entries
                self._waiting_for_entry_fill_to_place_sl_tp = False
            elif order.status in [OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                self.log.warning(f"Entry order {order.client_order_id} {order.status.name}.")
                self._active_entry_cid = None
                self._active_entry_order = None
                self._waiting_for_entry_fill_to_place_sl_tp = False
            # Bei anderen Status (z.B. ACCEPTED) bleibt _active_entry_cid gesetzt, _active_entry_order wird aktualisiert.

        elif self._active_stop_loss_cid and order.client_order_id == self._active_stop_loss_cid:
            self._active_stop_loss_order = order
            if order.status == OrderStatus.FILLED:
                self.log.info(f"Stop-Loss order {order.client_order_id} FILLED.")
                if self._active_take_profit_cid:
                    tp_order_to_cancel = self.cache.order(self._active_take_profit_cid)
                    if tp_order_to_cancel and tp_order_to_cancel.is_active:
                        self.cancel_order(tp_order_to_cancel)
                self._clear_sl_tp_tracking()
            elif order.status in [OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                self.log.warning(f"Stop-Loss order {order.client_order_id} {order.status.name}.")
                self._active_stop_loss_cid = None # Nur SL zurücksetzen, TP könnte noch aktiv sein
                self._active_stop_loss_order = None


        elif self._active_take_profit_cid and order.client_order_id == self._active_take_profit_cid:
            self._active_take_profit_order = order
            if order.status == OrderStatus.FILLED:
                self.log.info(f"Take-Profit order {order.client_order_id} FILLED.")
                if self._active_stop_loss_cid:
                    sl_order_to_cancel = self.cache.order(self._active_stop_loss_cid)
                    if sl_order_to_cancel and sl_order_to_cancel.is_active:
                        self.cancel_order(sl_order_to_cancel)
                self._clear_sl_tp_tracking()
            elif order.status in [OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                self.log.warning(f"Take-Profit order {order.client_order_id} {order.status.name}.")
                self._active_take_profit_cid = None # Nur TP zurücksetzen, SL könnte noch aktiv sein
                self._active_take_profit_order = None
    
    def _clear_sl_tp_tracking(self):
        """Hilfsmethode zum Zurücksetzen der SL/TP Order CIDs und Objekte."""
        self.log.debug("Clearing SL/TP CIDs and order objects.")
        self._active_stop_loss_cid = None
        self._active_stop_loss_order = None
        self._active_take_profit_cid = None
        self._active_take_profit_order = None
        # _active_entry_cid und _waiting_for_entry_fill_to_place_sl_tp sollten hier schon None/False sein.

    def on_stop(self) -> None:
        self.log.info(f"FVGStrategy ({self.id}) stopping...")
        open_orders_for_strategy = self.cache.orders_open(strategy_id=self.id)
        if open_orders_for_strategy:
            self.log.info(f"Found {len(open_orders_for_strategy)} open orders to cancel on_stop.")
            for order_to_cancel in open_orders_for_strategy:
                if order_to_cancel.is_active:
                    self.log.info(f"Requesting cancel for active order: {order_to_cancel.client_order_id}")
                    try:
                        self.cancel_order(order_to_cancel)
                    except Exception as e:
                        self.log.error(f"Error canceling order {order_to_cancel.client_order_id} on_stop: {e}", exc_info=True)
        else:
            self.log.info(f"No open orders found for strategy {self.id} to cancel on_stop.")

        self._active_entry_cid = None
        self._active_entry_order = None
        self._active_stop_loss_cid = None
        self._active_stop_loss_order = None
        self._active_take_profit_cid = None
        self._active_take_profit_order = None
        self._waiting_for_entry_fill_to_place_sl_tp = False
        self.log.info("Finished requesting cancels and resetting active order states in on_stop.")

    def on_shutdown(self) -> None:
        self.log.info(f"FVGStrategy ({self.id}) shutting down...")