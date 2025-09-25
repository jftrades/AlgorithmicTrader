from decimal import Decimal
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from tools.help_funcs.help_funcs_strategy import create_tags

class OrderTypes:
    def __init__(self, strategy):
        self.strategy = strategy

    def _resolve_instrument(self, instrument_id):
        if instrument_id is None:
            raise ValueError("instrument_id muss explizit übergeben werden (kein globales primäres Instrument).")
        inst = self.strategy.cache.instrument(instrument_id)
        if inst is None:
            raise ValueError(f"Instrument {instrument_id} nicht im Cache.")
        return inst, instrument_id

    def _collector(self, instrument_id):
        return self.strategy.instrument_dict[instrument_id]["collector"]

    # -------------------------------------------------
    # Market Orders
    # -------------------------------------------------
    def submit_long_market_order(self, instrument_id, quantity: Decimal, price: Decimal = None):
        inst, instrument_id = self._resolve_instrument(instrument_id)
        order = self.strategy.order_factory.market(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(quantity, inst.size_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="BUY", type="OPEN"),
        )
        self.strategy.submit_order(order)
        self._collector(instrument_id).add_trade(order)
        return order

    def submit_short_market_order(self, instrument_id, quantity: Decimal, price: Decimal = None):
        inst, instrument_id = self._resolve_instrument(instrument_id)
        order = self.strategy.order_factory.market(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity(quantity, inst.size_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="SHORT", type="OPEN"),
        )
        self.strategy.submit_order(order)
        self._collector(instrument_id).add_trade(order)
        return order

    # -------------------------------------------------
    # Bracket Orders
    # -------------------------------------------------
    def submit_long_bracket_order(self, instrument_id, quantity: Decimal, entry_price: Decimal, stop_loss: Decimal, take_profit: Decimal):
        inst, instrument_id = self._resolve_instrument(instrument_id)
        bracket_order = self.strategy.order_factory.bracket(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(quantity, inst.size_precision),
            sl_trigger_price=Price(stop_loss, inst.price_precision),
            tp_price=Price(take_profit, inst.price_precision),
            time_in_force=TimeInForce.GTC,
            entry_tags=create_tags(action="BUY", type="OPEN"),
        )
        self.strategy.submit_order_list(bracket_order)
        self._collector(instrument_id).add_trade(bracket_order.orders[0])
        self.strategy.log.info(
            f"Bracket BUY {instrument_id}: Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Qty={quantity}"
        )
        return bracket_order

    def submit_short_bracket_order(self, instrument_id, quantity: Decimal, entry_price: Decimal, stop_loss: Decimal, take_profit: Decimal):
        inst, instrument_id = self._resolve_instrument(instrument_id)
        bracket_order = self.strategy.order_factory.bracket(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity(quantity, inst.size_precision),
            sl_trigger_price=Price(stop_loss, inst.price_precision),
            tp_price=Price(take_profit, inst.price_precision),
            time_in_force=TimeInForce.GTC,
            entry_tags=create_tags(action="SHORT", type="OPEN"),
        )
        self.strategy.submit_order_list(bracket_order)
        self._collector(instrument_id).add_trade(bracket_order.orders[0])
        self.strategy.log.info(
            f"Bracket SELL {instrument_id}: Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Qty={quantity}"
        )
        return bracket_order

    # -------------------------------------------------
    # Limit Orders
    # -------------------------------------------------
    def submit_long_limit_order(self, instrument_id, quantity: Decimal, limit_price: Decimal):
        inst, instrument_id = self._resolve_instrument(instrument_id)
        order = self.strategy.order_factory.limit(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(quantity, inst.size_precision),
            limit_price=Price(limit_price, inst.price_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="BUY", type="OPEN"),
        )
        self.strategy.submit_order(order)
        self._collector(instrument_id).add_trade(order)
        self.strategy.log.info(f"Limit BUY {instrument_id}: Qty={quantity}, Limit={limit_price}")
        return order

    def submit_short_limit_order(self, instrument_id, quantity: Decimal, limit_price: Decimal):
        inst, instrument_id = self._resolve_instrument(instrument_id)
        order = self.strategy.order_factory.limit(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity(quantity, inst.size_precision),
            limit_price=Price(limit_price, inst.price_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="SHORT", type="OPEN"),
        )
        self.strategy.submit_order(order)
        self._collector(instrument_id).add_trade(order)
        self.strategy.log.info(f"Limit SELL {instrument_id}: Qty={quantity}, Limit={limit_price}")
        return order

    # -------------------------------------------------
    # Close Position
    # -------------------------------------------------
    def close_position_by_market_order(self, instrument_id):
        position = self.strategy.get_position(instrument_id)
        if position is None or position.quantity == 0:
            self.strategy.log.info(f"[{instrument_id}] No open position to close.")
            return None
        # Engine Close
        self.strategy.base_close_position(instrument_id)
        return position