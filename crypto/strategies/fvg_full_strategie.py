# fvg_strategy.py

from decimal import Decimal
from collections import deque
from typing import Deque, Optional, Tuple # Tuple explizit importieren

# Nautilus Core und Modelle
from nautilus_trader.core.nautilus_pyo3 import InstrumentId
from nautilus_trader.model.strategy import Strategy, StrategyConfig
from nautilus_trader.model.objects import Price, Quantity, Order
from nautilus_trader.model.identifiers import Symbol, Venue # Für Vollständigkeit
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, OrderStatus
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.events import OrderEvent

# Nautilus Konfigurationstypen
from nautilus_trader.config import PositiveInt, PositiveFloat


# --- FVG Strategy Configuration ---
class FVGStrategyConfig(StrategyConfig):
    """
    Configuration for FVGStrategy instances.

    Defines the parameters required to configure and run the Fair Value Gap
    trading strategy.
    """
    instrument_id: str
    """The instrument ID string (e.g., "BTCUSDT.BINANCE")."""
    bar_type: str
    """The bar type string (e.g., "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL")."""
    trade_size_base: Decimal
    """The trade size in base currency (e.g., Decimal("0.01") for BTC)."""
    fvg_min_size_pips: PositiveInt
    """Minimum size of the FVG in pips for it to be considered valid."""
    entry_offset_pips: int
    """Offset in pips from the FVG edge for the entry price (0 for direct entry at the edge)."""
    stop_loss_pips: PositiveInt
    """Stop-loss distance in pips from the entry price."""
    take_profit_ratio: PositiveFloat
    """Take-profit as a multiple of the stop-loss distance (Risk-Reward-Ratio)."""


class FVGStrategy(Strategy):
    """
    A strategy that identifies Fair Value Gaps (FVGs) based on a 3-bar pattern
    and attempts to enter trades with a limit order.

    Upon a successful entry, it places a stop-loss and a take-profit order.
    It manages one trade (entry, SL, TP) at a time for the configured instrument.
    """

    def __init__(self, config: FVGStrategyConfig):
        """
        Initializes the FVGStrategy instance.

        Parameters
        ----------
        config : FVGStrategyConfig
            The configuration object for this strategy instance.
        """
        super().__init__(config)
        self.config: FVGStrategyConfig = config

        self._instrument_id_obj: InstrumentId = InstrumentId.from_str(self.config.instrument_id)
        self._bar_type_obj: BarType = BarType.from_str(self.config.bar_type)
        self._trade_size_base_qty: Quantity = Quantity(self.config.trade_size_base, precision=8) # Initial
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
        """
        Called once when the strategy is started.

        Retrieves instrument details, refines trade quantity precision,
        and subscribes to necessary market data.
        """
        self.log.info(f"FVGStrategy ({self.id}) starting...")
        self._instrument = self.get_instrument(self._instrument_id_obj)
        if self._instrument is None:
            self.log.error(f"Instrument {self._instrument_id_obj} not found. Strategy stopping.")
            self.stop()
            return

        self._pip_value = self._instrument.pip_value
        self._price_precision = self._instrument.price_precision

        if self._pip_value is None or self._pip_value.is_zero():
            self.log.error(f"Pip value for {self._instrument.id} is invalid. Strategy stopping.")
            self.stop()
            return

        if self._instrument.base_precision is not None:
             self._trade_size_base_qty = Quantity(self.config.trade_size_base, precision=self._instrument.base_precision)
             self.log.info(f"Refined trade size: {self._trade_size_base_qty} (Precision: {self._instrument.base_precision})")
        else:
             self.log.warning(f"Instrument has no base_precision. Using default precision for trade size: {self._trade_size_base_qty.precision}")

        self.log.info(f"Instrument: {self._instrument.id}, PipVal: {self._pip_value}, PxPrec: {self._price_precision}, TradeQty: {self._trade_size_base_qty}")

        self.subscribe_instruments(self._instrument_id_obj)
        self.request_bars(instrument_id=self._instrument_id_obj, bar_type=self._bar_type_obj)
        self.log.info(f"Subscribed and requested bars for {self._instrument_id_obj} ({self._bar_type_obj})")

    # --- Kernlogik-Methoden ---
    def on_bar(self, bar: Bar) -> None:
        """
        Called by the system when a new bar of the configured `bar_type` is received.

        Adds the bar to a buffer and checks for FVG patterns to initiate trades.

        Parameters
        ----------
        bar : Bar
            The newly received bar data.
        """
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < 3:
            return

        fvg_details = self._check_for_fvg()
        if fvg_details:
            side, low_b, high_b = fvg_details
            self.log.info(f"FVG at {bar.close_time}: Side={side.name}, Low={low_b}, High={high_b}")
            self._handle_fvg_entry(direction=side, fvg_low_boundary=low_b, fvg_high_boundary=high_b)
    
    def _check_for_fvg(self) -> Optional[Tuple[OrderSide, Price, Price]]:
        """
        Checks the 3-bar pattern in `_bar_buffer` for a Fair Value Gap.

        A bullish FVG is formed if c3.low > c1.high.
        A bearish FVG is formed if c3.high < c1.low.
        The FVG must also meet the `fvg_min_size_pips` requirement.

        Returns
        -------
        Optional[Tuple[OrderSide, Price, Price]]
            A tuple containing (OrderSide, fvg_low_boundary, fvg_high_boundary) if a valid FVG is found.
            Returns `None` otherwise.
        """
        c1: Bar = self._bar_buffer[0]
        # c2: Bar = self._bar_buffer[1] # Currently unused in FVG logic itself
        c3: Bar = self._bar_buffer[2]

        fvg_size_pips: Optional[Decimal] = None
        fvg_low_boundary: Optional[Price] = None
        fvg_high_boundary: Optional[Price] = None
        direction: Optional[OrderSide] = None

        if c3.low > c1.high: # Bullish FVG
            direction = OrderSide.BUY
            fvg_low_boundary = c1.high
            fvg_high_boundary = c3.low
        elif c3.high < c1.low: # Bärisches FVG
            direction = OrderSide.SELL
            fvg_low_boundary = c3.high
            fvg_high_boundary = c1.low

        if direction: 
            fvg_size_price_units = fvg_high_boundary - fvg_low_boundary
            if self._pip_value and not self._pip_value.is_zero():
                fvg_size_pips = fvg_size_price_units.value / self._pip_value.value
            else:
                self.log.warning("Cannot calculate FVG size in pips: Pip value is invalid.")
                return None
            self.log.debug(f"Potential {direction.name} FVG: Size={fvg_size_pips:.2f} pips.")
            if fvg_size_pips >= self.config.fvg_min_size_pips:
                return direction, fvg_low_boundary, fvg_high_boundary
            else:
                self.log.debug(f"FVG too small: {fvg_size_pips:.2f} < {self.config.fvg_min_size_pips} pips.")
        return None

    def _handle_fvg_entry(self, direction: OrderSide, fvg_low_boundary: Price, fvg_high_boundary: Price) -> None:
        """
        Handles the logic for placing an entry order based on a detected FVG.

        Checks for existing active orders or positions before placing a new limit order.

        Parameters
        ----------
        direction : OrderSide
            The side of the trade (BUY or SELL).
        fvg_low_boundary : Price
            The lower price boundary of the FVG.
        fvg_high_boundary : Price
            The upper price boundary of the FVG.
        """
        if self._active_entry_order and self._active_entry_order.is_active:
            self.log.debug(f"Active entry order {self._active_entry_order.id} exists. Skipping entry.")
            return
        current_pos = self.portfolio.current_position(self._instrument_id_obj)
        if current_pos and not current_pos.is_flat:
            self.log.debug(f"Position for {self._instrument_id_obj} exists: {current_pos.quantity}. Skipping entry.")
            return

        offset_val = self._pip_value * self.config.entry_offset_pips
        entry_px: Price
        if direction == OrderSide.BUY:
            entry_px = fvg_high_boundary - offset_val
        elif direction == OrderSide.SELL:
            entry_px = fvg_low_boundary + offset_val
        else:
            self.log.error(f"Invalid direction: {direction} for FVG entry.")
            return

        entry_px = entry_px.round(self._price_precision)
        if entry_px <= Price.zero(entry_px.precision):
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

    def on_order_event(self, event: OrderEvent) -> None:
        """
        Handles order events to manage the lifecycle of trades.

        This includes placing SL/TP orders upon entry fill, and managing
        OCO (One-Cancels-Other) logic for SL and TP orders.

        Parameters
        ----------
        event : OrderEvent
            The order event received from the system.
        """
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

    def _place_stop_loss_and_take_profit(self, filled_entry_order: Order) -> None:
        """
        Places stop-loss and take-profit orders after an entry order is filled.

        Parameters
        ----------
        filled_entry_order : Order
            The entry order that has been filled.
        """
        entry_px_filled = filled_entry_order.avg_px_filled()
        entry_side = filled_entry_order.side
        trade_qty = filled_entry_order.quantity_filled()

        if trade_qty.is_zero():
            self.log.error(f"Cannot place SL/TP, filled quantity is zero for order {filled_entry_order.id}.")
            return

        sl_offset_px = self._pip_value * self.config.stop_loss_pips
        sl_px: Price
        tp_px: Price

        if entry_side == OrderSide.BUY:
            sl_px = entry_px_filled - sl_offset_px
            tp_dist_px = sl_offset_px * self._take_profit_ratio_decimal
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

        if sl_px <= Price.zero(sl_px.precision) or tp_px <= Price.zero(tp_px.precision):
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

    # --- Ende / Aufräum-Methoden ---
    def on_stop(self) -> None:
        """
        Called once when the strategy is stopped.

        Performs cleanup, such as canceling any open orders.
        """
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
        """
        Called once when the trading node is shutting down.

        Last chance for any cleanup before the process exits.
        """
        self.log.info(f"FVGStrategy ({self.id}) shutting down...") 