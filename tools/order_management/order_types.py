from decimal import Decimal
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from tools.help_funcs.help_funcs_strategy import create_tags

class OrderTypes:
    def __init__(self, strategy):
        self.strategy = strategy
        pass

    def submit_long_market_order(self, quantity: Decimal): 
        order = self.strategy.order_factory.market(
            instrument_id=self.strategy.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(quantity, self.strategy.instrument.size_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="BUY", type="OPEN")
        )
        self.strategy.submit_order(order)

    def submit_short_market_order(self, quantity: Decimal): 
        order = self.strategy.order_factory.market(
            instrument_id=self.strategy.instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity(quantity, self.strategy.instrument.size_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="SHORT", type="OPEN")
        )
        self.strategy.submit_order(order)
    

    def submit_long_bracket_order(self, quantity: Decimal, entry_price: Decimal, stop_loss: Decimal, take_profit: Decimal):
        bracket_order = self.strategy.order_factory.bracket(
            instrument_id=self.strategy.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(quantity, self.strategy.instrument.size_precision),
            sl_trigger_price=Price(stop_loss, self.strategy.instrument.price_precision),
            tp_price=Price(take_profit, self.strategy.instrument.price_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="BUY", type="OPEN")
        )
        self.strategy.submit_order_list(bracket_order)
        self.strategy.collector.add_trade(bracket_order.orders[0])
        self.strategy.log.info(
            f"Bracket Order: Side={OrderSide.BUY.upper()}, Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Qty={quantity}"
        )   

    def submit_short_bracket_order(self, quantity: Decimal, entry_price: Decimal, stop_loss: Decimal, take_profit: Decimal):
        bracket_order = self.strategy.order_factory.bracket(
            instrument_id=self.strategy.instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity(quantity, self.strategy.instrument.size_precision),
            sl_trigger_price=Price(stop_loss, self.strategy.instrument.price_precision),
            tp_price=Price(take_profit, self.strategy.instrument.price_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="SHORT", type="OPEN")
        )
        self.strategy.submit_order_list(bracket_order)
        self.strategy.collector.add_trade(bracket_order.orders[0])
        self.strategy.log.info(
            f"Bracket Order: Side={OrderSide.SELL.upper()}, Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Qty={quantity}"
        )
    
    def submit_long_limit_order(self, strategy, quantity: Decimal, limit_price: Decimal):
        order = strategy.order_factory.limit(
            instrument_id=strategy.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(quantity, strategy.instrument.size_precision),
            limit_price=Price(limit_price, strategy.instrument.price_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="BUY", type="OPEN")
        )
        strategy.submit_order(order)
        strategy.log.info(f"Limit Order: Side={OrderSide.BUY.upper()}, Qty={quantity}, Limit={limit_price}")

    def submit_short_limit_order(self, strategy, quantity: Decimal, limit_price: Decimal):
        order = strategy.order_factory.limit(
            instrument_id=strategy.instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity(quantity, strategy.instrument.size_precision),
            limit_price=Price(limit_price, strategy.instrument.price_precision),
            time_in_force=TimeInForce.GTC,
            tags=create_tags(action="SHORT", type="OPEN")
        )
        strategy.submit_order(order)
        strategy.log.info(f"Limit Order: Side={OrderSide.SELL.upper()}, Qty={quantity}, Limit={limit_price}")