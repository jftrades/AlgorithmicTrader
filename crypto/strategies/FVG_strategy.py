# Standard Library Importe
from decimal import Decimal
from typing import Any
import sys
from pathlib import Path


# Nautilus Kern offizielle Importe (für Backtest eigentlich immer hinzufügen)
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

# Nautilus Kern eigene Importe !!! immer
VIS_PATH = Path(__file__).resolve().parent.parent / "data" / "visualizing"
if str(VIS_PATH) not in sys.path:
    sys.path.insert(0, str(VIS_PATH))

from backtest_visualizer_prototype import BacktestDataCollector
from AlgorithmicTrader.crypto.strategies.help_funcs import create_tags
from nautilus_trader.common.enums import LogColor

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
        self.realized_pnl = 0
        self.bar_counter = 0

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.subscribe_trade_ticks(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)
        self.log.info("Strategy started!")

        self.collector = BacktestDataCollector()
        self.collector.initialise_logging_indicator("position", 1)
        self.collector.initialise_logging_indicator("realized_pnl", 2)
        self.collector.initialise_logging_indicator("unrealized_pnl", 3)
        self.collector.initialise_logging_indicator("balance", 4)


    def get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None

    def on_bar (self, bar: Bar) -> None: 
        self.bar_counter += 1

        self.bar_buffer.append(bar)
        if len(self.bar_buffer) < 3:
            return
        
        bar_2 = self.bar_buffer[-3]
        bar_1 = self.bar_buffer[-2]
        bar_0 = self.bar_buffer[-1]

        # Bullische FVG
        if bar_0.low > bar_2.high:
            self.log.info(f"Bullische FVG erkannt: Gap von {bar_2.high} bis {bar_0.low}")
            self.bullish_fvgs.append((bar_0.low, bar_2.high, self.bar_counter)) # self bar counter speichert die 3te bar die FVG enstehen lässt -> die creation bar

        # Bearishe FVG
        if bar_0.high < bar_2.low:
            self.log.info(f"Bearishe FVG erkannt: Gap von {bar_2.low} bis {bar_0.high}") 
            self.bearish_fvgs.append((bar_2.low, bar_0.high, self.bar_counter))
        
        # Buffer auf die letzten 3 Bars begrenzen
        if len(self.bar_buffer) > 3:
            self.bar_buffer.pop(0)

        position = self.get_position()
        # Bullishe FVG erkennen und Kaufmethode
        for gap in self.bullish_fvgs[:]:
            gap_high, gap_low, creation_bar = gap
            if self.bar_counter <= creation_bar:
                continue
            
            if gap_low <= bar.low <= gap_high:
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
                    
                    # Risk Management - Reduzierte Risiko% und Mindestkapital-Check
                    min_account_balance = Decimal("1000.0")  # Mindestens 1000 USDT für Trading
                    if usdt_balance < min_account_balance:
                        self.log.warning(f"Konto-Balance zu niedrig für Trading: {usdt_balance} < {min_account_balance}")
                        continue
                    
                    risk_percent = Decimal("0.005")  # Reduziert von 1% auf 0.5%
                    risk_amount = usdt_balance * risk_percent

                    entry_price = bar.close
                    stop_loss = bar.low  # SL unter das aktuelle Low
                    risk_per_unit = abs(entry_price - stop_loss)

                    # DEBUG: Schauen wir uns die Werte an
                    self.log.info(f"DEBUG: Entry={entry_price}, SL={stop_loss}, Risk_per_unit={risk_per_unit}")
                    self.log.info(f"DEBUG: Risk als % vom Entry: {(risk_per_unit/entry_price)*100:.4f}%")
                    
                    # FIX: Minimum Risk Distance setzen
                    min_risk_percent = Decimal("0.002")  # Mindestens 0.2% vom Entry-Preis
                    min_risk_distance = entry_price * min_risk_percent
                    
                    if risk_per_unit < min_risk_distance:
                        # Stop-Loss ist zu nah - setze ihn weiter weg
                        stop_loss = entry_price - min_risk_distance
                        risk_per_unit = min_risk_distance
                        self.log.info(f"Stop-Loss zu nah! Angepasst auf: {stop_loss}")

                    if risk_per_unit > 0:
                        position_size = risk_amount / risk_per_unit
                    else:
                        position_size = Decimal("0.0")
                    
                    # HEBEL-KONTROLLE: Verhindert versteckten Hebel durch Positionsgrößen-Limitierung
                    # Problem: Ohne diese Prüfung können wir Positionen kaufen, die größer sind als unser Kapital
                    # Beispiel: 10.000 USDT Balance, aber 8 BTC kaufen (320.000 USDT Wert) = 32x Hebel!
                    max_leverage = Decimal("2.0")  # Maximal 2:1 Hebel erlaubt
                    max_position_value = usdt_balance * max_leverage  # Max. Positionswert basierend auf Balance
                    max_position_size = max_position_value / entry_price  # Max. BTC die wir kaufen können
                    
                    # Nehme das MINIMUM von Risk-basierter Size und Leverage-limitierter Size
                    if position_size > max_position_size:
                        self.log.warning(
                            f"HEBEL-WARNUNG: Position zu groß! Risk-Size: {position_size}, Max-Size: {max_position_size} "
                            f"(Positionswert: {position_size * entry_price:.0f} USDT bei {usdt_balance} USDT Balance)"
                        )
                        position_size = max_position_size  # Limitiere auf max. erlaubte Größe
                    
                    position_size = round(position_size, self.instrument.size_precision)
                    
                    # Debug-Info: Zeige tatsächlichen Hebel an
                    actual_position_value = position_size * entry_price
                    actual_leverage = actual_position_value / usdt_balance if usdt_balance > 0 else Decimal("0")
                    self.log.info(f"HEBEL-CHECK: PositionWert={actual_position_value:.0f} USDT, Hebel={actual_leverage:.2f}x")
                    
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
                    
                    # Bracket Order für BUY (Entry + SL + TP in einem)
                    bracket_order = self.order_factory.bracket(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(position_size, self.instrument.size_precision),
                        sl_trigger_price=Price(stop_loss, self.instrument.price_precision),
                        tp_price=Price(take_profit, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                        entry_tags=create_tags(action="BUY", type="BRACKET", sl=stop_loss, tp=take_profit)
                    )
                    self.submit_order_list(bracket_order)
                    # Add the entry order (first order in the bracket) to collector
                    self.collector.add_trade(bracket_order.orders[0])
                
                    self.log.info(f"Order-Submit: Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Size={position_size}, USDT={usdt_balance}")

                self.bullish_fvgs.remove(gap) # FVG nach Retest entfernen
                
            elif bar.low < gap_low:
                self.log.info(f"Bullische FVG durchtraded: {gap}")
                self.bullish_fvgs.remove(gap)  # FVG nach Durchbruch entfernen

        # Bearishe FVG erkennen und Kaufmethode
        for gap in self.bearish_fvgs[:]:
            gap_high, gap_low, creation_bar = gap
            if self.bar_counter <= creation_bar:
                continue

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
                    
                    # Risk Management - Reduzierte Risiko% und Mindestkapital-Check
                    min_account_balance = Decimal("1000.0")  # Mindestens 1000 USDT für Trading
                    if usdt_balance < min_account_balance:
                        self.log.warning(f"Konto-Balance zu niedrig für Trading: {usdt_balance} < {min_account_balance}")
                        continue
                    
                    risk_percent = Decimal("0.005")  # Reduziert von 1% auf 0.5%
                    risk_amount = usdt_balance * risk_percent

                    entry_price = bar.close
                    stop_loss = bar.high  # SL über das aktuelle high
                    risk_per_unit = abs(stop_loss - entry_price)

                 # FIX: Minimum Risk Distance
                    min_risk_percent = Decimal("0.002")  # Mindestens 0.2%
                    min_risk_distance = entry_price * min_risk_percent
                    
                    if risk_per_unit < min_risk_distance:
                        stop_loss = entry_price + min_risk_distance
                        risk_per_unit = min_risk_distance
                        self.log.info(f"Stop-Loss zu nah! Angepasst auf: {stop_loss}")

                    if risk_per_unit > 0:
                        position_size = risk_amount / risk_per_unit
                    else:
                        position_size = Decimal("0.0")
                    
                    # HEBEL-KONTROLLE: Verhindert versteckten Hebel durch Positionsgrößen-Limitierung
                    # Problem: Ohne diese Prüfung können wir Positionen kaufen, die größer sind als unser Kapital
                    # Beispiel: 10.000 USDT Balance, aber 8 BTC shorten (320.000 USDT Wert) = 32x Hebel!
                    max_leverage = Decimal("2.0")  # Maximal 2:1 Hebel erlaubt
                    max_position_value = usdt_balance * max_leverage  # Max. Positionswert basierend auf Balance
                    max_position_size = max_position_value / entry_price  # Max. BTC die wir shorten können
                    
                    # Nehme das MINIMUM von Risk-basierter Size und Leverage-limitierter Size
                    if position_size > max_position_size:
                        self.log.warning(
                            f"HEBEL-WARNUNG: Position zu groß! Risk-Size: {position_size}, Max-Size: {max_position_size} "
                            f"(Positionswert: {position_size * entry_price:.0f} USDT bei {usdt_balance} USDT Balance)"
                        )
                        position_size = max_position_size  # Limitiere auf max. erlaubte Größe
                    
                    position_size = round(position_size, self.instrument.size_precision)
                    
                    # Debug-Info: Zeige tatsächlichen Hebel an
                    actual_position_value = position_size * entry_price
                    actual_leverage = actual_position_value / usdt_balance if usdt_balance > 0 else Decimal("0")
                    self.log.info(f"HEBEL-CHECK: PositionWert={actual_position_value:.0f} USDT, Hebel={actual_leverage:.2f}x")

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

                    # Bracket Order für SELL (Entry + SL + TP in einem)
                    bracket_order = self.order_factory.bracket(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(position_size, self.instrument.size_precision),
                        sl_trigger_price=Price(stop_loss, self.instrument.price_precision),
                        tp_price=Price(take_profit, self.instrument.price_precision),
                        time_in_force=TimeInForce.GTC,
                        entry_tags=create_tags(action="SHORT", type="BRACKET", sl=stop_loss, tp=take_profit)
                    )
                    self.submit_order_list(bracket_order)
                    # Add the entry order (first order in the bracket) to collector
                    self.collector.add_trade(bracket_order.orders[0])

                    self.log.info(f"Order-Submit: Entry={entry_price}, SL={stop_loss}, TP={take_profit}, Size={position_size}, USDT={usdt_balance}")

                self.bearish_fvgs.remove(gap) # FVG nach Retest entfernen
                
            elif bar.high > gap_high:
                self.log.info(f"Bearishe FVG durchtraded: {gap}")
                self.bearish_fvgs.remove(gap)  # FVG nach Durchbruch entfernen

    # HILFSBLOCK FÜR VISUALIZER: - anpassen je nach Indikatoren etc
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
        #self.log.info(f"position.quantity: {net_position}", LogColor.RED)
        
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        #usdt_balance = account.balance_total(Currency.from_str("USDT")) if account else None
        usdt_balance = account.balances_total()
        self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)

        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
        #self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=float(usdt_balance) if usdt_balance is not None else None)


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

        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

    # on_order_filled, on_position_closed und on_position_opened immer hinzufügen für skript
    def on_order_filled(self, order_filled) -> None:
        """
        Actions to be performed when an order is filled.
        """

        ret = self.collector.add_trade_details(order_filled)
        self.log.info(
            f"Order filled: {order_filled.commission}", color=LogColor.GREEN)
        

    def on_position_closed(self, position_closed) -> None:

        realized_pnl = position_closed.realized_pnl  # Realized PnL
        self.realized_pnl += float(realized_pnl) if realized_pnl else 0
    

    def on_position_opened(self, position_opened) -> None:
        realized_pnl = position_opened.realized_pnl  # Realized PnL
        #self.realized_pnl += float(realized_pnl) if realized_pnl else 0

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()
