from decimal import Decimal
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce

class OrderTypes:
    def __init__(self):
        pass

    def submit_market_order(self, strategy, side: str, quantity: Decimal, price: Decimal = None, tags: dict = None):
        """
        Submit a market order (buy/sell).
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        order = strategy.order_factory.market(
            instrument_id=strategy.instrument_id,
            order_side=order_side,
            quantity=Quantity(quantity, strategy.instrument.size_precision),
            time_in_force=TimeInForce.GTC,
            entry_tags=tags or {}
        )
        strategy.submit_order(order)
        strategy.log.info(f"Market Order: Side={side.upper()}, Qty={quantity}, Price={price}")

    def submit_limit_order(self, strategy, side: str, quantity: Decimal, limit_price: Decimal, tags: dict = None):
        """
        Submit a limit order (buy/sell).
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        order = strategy.order_factory.limit(
            instrument_id=strategy.instrument_id,
            order_side=order_side,
            quantity=Quantity(quantity, strategy.instrument.size_precision),
            limit_price=Price(limit_price, strategy.instrument.price_precision),
            time_in_force=TimeInForce.GTC,
            entry_tags=tags or {}
        )
        strategy.submit_order(order)
        strategy.log.info(f"Limit Order: Side={side.upper()}, Qty={quantity}, Limit={limit_price}")

    def submit_bracket_order(self, strategy, side: str, quantity: Decimal, entry_price: Decimal, stop_loss: Decimal, take_profit: Decimal, tags: dict = None):
        """
        Submit a bracket order (entry + SL + TP).
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        bracket_order = strategy.order_factory.bracket(
            instrument_id=strategy.instrument_id,
            order_side=order_side,
            quantity=Quantity(quantity, strategy.instrument.size_precision),
            sl_trigger_price=Price(stop_loss, strategy.instrument.price_precision),
            tp_price=Price(take_profit, strategy.instrument.price_precision),
            time_in_force=TimeInForce.GTC,
            entry_tags=tags or {}
        )
        strategy.submit_order_list(bracket_order)
        strategy.collector.add_trade(bracket_order.orders[0])
        strategy.log.info(
            f"Bracket Order: Side={side.upper()}, Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Qty={quantity}"

        )   

    #def long_setup(self, rsi_value, is_breakout, breakout_dir):
        #self.order_types.handle_long_setup(
            #strategy=self,
            #rsi_value=rsi_value,
            #is_breakout=is_breakout,
            #breakout_dir=breakout_dir,
            #breakout_analyser=self.breakout_analyser,
            #risk_manager=self.risk_manager,
            #rsi_oversold=self.rsi_oversold,
            #rsi_oversold_triggered=getattr(self, "rsi_oversold_triggered", False),
            #risk_per_trade=0.01
        #)

    #def short_setup(self, rsi_value, is_breakout, breakout_dir):
        #self.order_types.handle_short_setup(
            #strategy=self,
            #rsi_value=rsi_value,
            #is_breakout=is_breakout,
            #breakout_dir=breakout_dir,
            #breakout_analyser=self.breakout_analyser,
            #risk_manager=self.risk_manager,
            #rsi_overbought=self.rsi_overbought,
            #rsi_overbought_triggered=getattr(self, "rsi_overbought_triggered", False),
            #risk_per_trade=0.01
        #)