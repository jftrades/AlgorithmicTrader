# der Unterschied zu FVG_simple_strategy und FVG_simple_execution ist:
# in FVG Strategie probieren wir mal mit Bedingungen, Fees, RiskManagement etc rum um 
# das zukünftig for weitere Strategien schon mal gemacht zu haben einfach

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

class FVGStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    #...
    close_positions_on_stop: bool = True 
    
class FVGStrategy(Strategy):
    def __init__(self, config: FVGStrategyConfig):
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
        self.venue = self.instrument_id.venue
        self.logged_accounts = False  # <--- zum debuuggen

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

    def on_bar (self, bar: Bar) -> None: 
        if not self.logged_accounts: # <--- zum debuuggen
            with open("account_debug.txt", "w") as f:
                for acc in self.cache.accounts():
                    f.write(f"Account: {acc} | Balances: {acc.balances()}\n")
            self.logged_accounts = True

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
            self.bearish_fvgs.append((bar_2.low, bar_0.high))
        
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
                    order_side = OrderSide.BUY
                    account_id = AccountId("BINANCE-001")
                    account = self.cache.account(account_id)
                    usdt_free = account.balance(USDT).free
                    if usdt_free is None:
                        usdt_balance = Decimal("0")
                    else:
                        usdt_balance = Decimal(str(usdt_free).split(" ")[0])
                    self.log.info(f"DEBUG: Aktuelle USDT-Balance: {usdt_balance}")
                    risk_percent = Decimal("0.001")
                    risk_amount = usdt_balance * risk_percent

                    entry_price = bar.close
                    stop_loss = bar.low  # SL unter das aktuelle Low
                    risk_per_unit = abs(entry_price - stop_loss)
                    if risk_per_unit > 0:
                        position_size = risk_amount / risk_per_unit
                    else:
                        position_size = Decimal("0.0")
                    position_size = round(position_size, self.instrument.size_precision)
                    
                    risk = abs(entry_price - stop_loss)
                    take_profit = entry_price + 2 * risk

                    self.log.info(
                        f"Risk-Log | USDT-Balance: {usdt_balance} | RiskAmount: {risk_amount} | "
                        f"Entry: {entry_price} | SL: {stop_loss} | PositionSize: {position_size} | "
                        f"RiskPerUnit: {risk_per_unit}"
                    )    

                    if position_size <= 0:
                        self.log.warning(f"PositionSize <= 0, Trade wird übersprungen! RiskPerUnit: {risk_per_unit}")
                        continue  # oder 'return', je nach Schleife/Kontext
                    max_size = Decimal("0.5")  # oder passend zu deinem Markt
                    if position_size > max_size:
                        position_size = max_size

                    self.log.info(f"Order-Submit: Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Size={position_size}, USDT={usdt_balance}")
                    
                    order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(position_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)

                    # Stop-Loss-Order
                    sl_order = self.order_factory.stop_market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(position_size, self.instrument.size_precision),
                        trigger_price=Price(stop_loss, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sl_order)

                    # Take-Profit-Order
                    tp_order = self.order_factory.limit(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(position_size, self.instrument.size_precision),
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
                    order_side = OrderSide.SELL
                    account_id = AccountId("BINANCE-001")
                    account = self.cache.account(account_id)
                    usdt_free = account.balance(USDT).free
                    if usdt_free is None:
                        usdt_balance = Decimal("0")
                    else:
                        usdt_balance = Decimal(str(usdt_free).split(" ")[0])
                    self.log.info(f"DEBUG: Aktuelle USDT-Balance: {usdt_balance}")
                    risk_percent = Decimal("0.001")
                    risk_amount = usdt_balance * risk_percent

                    entry_price = bar.close
                    stop_loss = bar.high  # SL über das aktuelle high
                    risk_per_unit = abs(stop_loss - entry_price)
                    if risk_per_unit > 0:
                        position_size = risk_amount / risk_per_unit
                    else:
                        position_size = Decimal("0.0")
                    position_size = round(position_size, self.instrument.size_precision)

                    risk = abs(stop_loss - entry_price)
                    take_profit = entry_price - 2 * risk

                    self.log.info(
                        f"Risk-Log | USDT-Balance: {usdt_balance} | RiskAmount: {risk_amount} | "
                        f"Entry: {entry_price} | SL: {stop_loss} | PositionSize: {position_size} | "
                        f"RiskPerUnit: {risk_per_unit}"
                    )    
                    if position_size <= 0:
                        self.log.warning(f"PositionSize <= 0, Trade wird übersprungen! RiskPerUnit: {risk_per_unit}")
                        continue  # oder 'return', je nach Schleife/Kontext

                    order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(position_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)


                    # Stop-Loss-Order
                    sl_order = self.order_factory.stop_market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(position_size, self.instrument.size_precision),
                        trigger_price=Price(stop_loss, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sl_order)

                    # Take-Profit-Order
                    tp_order = self.order_factory.limit(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(position_size, self.instrument.size_precision),
                        price=Price(take_profit, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(tp_order)

                self.bearish_fvgs.remove(gap) # FVG nach Retest entfernen
                
            elif bar.high > gap_high:
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
