# ================================================================================
# TICK STRATEGY TEMPLATE - Nautilus Trader
# ================================================================================
# Minimales Template für Tick-basierte Strategien mit Nautilus Trader
# 
# FEATURES:
# - Reine Tick-Verarbeitung (kein Bar-Logic)
# - Integrierte BacktestDataCollector-Visualisierung
# - Beispiele für Bracket Orders und Balance-Checks (auskommentiert)
# - Tick-Buffer für Performance-Optimierung
# - Clean, minimal, und leicht erweiterbar
# ================================================================================

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

class NameDerTickStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    trade_size: Decimal
    tick_buffer_size: int = 1000
    #...
    close_positions_on_stop: bool = True 
    
class NameDerTickStrategy(Strategy):
    def __init__(self, config: NameDerTickStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.tick_buffer_size = config.tick_buffer_size 
        #...
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.realized_pnl = 0
        # weitere wichtige tick-spezfische Methoden
        self.tick_counter = 0
        self.trade_ticks = []
        # wenn man mit den Tick Daten eigene Bars erstellt, dann brauchen wir noch zb folgendes bzw anpassen
        #self.current_bar = None
        #self.bar_duration_ns = 60 * 1_000_000_000 #1 Minute in Nanosekunden

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_trade_ticks(self.instrument_id)
        self.log.info("Tick Strategy started!")

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

    def on_trade_tick(self, tick: TradeTick) -> None:  
        self.tick_counter += 1

        # Tick zu Buffer hinzufügen
        self.trade_ticks.append(tick)
        if len(self.trade_ticks) > self.tick_buffer_size:
            self.trade_ticks.pop(0)
        
        # Optional: Eigene Bars aus Ticks erstellen
        #self.update_custom_bar(tick)
        
        # Beispiel für USDT Balance holen:
        # account_id = AccountId("BINANCE-001")
        # account = self.cache.account(account_id)
        # usdt_free = account.balance(USDT).free
        # usdt_balance = Decimal(str(usdt_free).split(" ")[0]) if usdt_free else Decimal("0")
        
        # Beispiel für Bracket Order:
        # bracket_order = self.order_factory.bracket(
        #     instrument_id=self.instrument_id,
        #     order_side=OrderSide.BUY,  # oder SELL
        #     quantity=Quantity(self.trade_size, self.instrument.size_precision),
        #     sl_trigger_price=Price(tick.price * Decimal("0.98"), self.instrument.price_precision),
        #     tp_price=Price(tick.price * Decimal("1.03"), self.instrument.price_precision),
        #     time_in_force=TimeInForce.GTC,
        #     entry_tags=create_tags(action="BUY", type="TICK_BRACKET", signal_price=str(tick.price))
        # )
        # self.submit_order_list(bracket_order)
        # self.collector.add_trade(bracket_order.orders[0])

        # VISUALIZER UPDATE (alle 100 Ticks für Performance)
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balances_total()
        #self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)
           
        self.collector.add_indicator(timestamp=tick.ts_event, name="position", value=net_position)
        self.collector.add_indicator(timestamp=tick.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=tick.ts_event, name="realized_pnl", value=float(self.realized_pnl))
        self.collector.add_bar(timestamp=tick.ts_event, open_=tick.price, high=tick.price, low=tick.price, close=tick.price)

    # weitere on methoden z.B.
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
        self.log.info(f"Tick Strategy stopped! Processed {self.tick_counter:,} ticks")

        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

    # on_order_filled, on_position_closed und on_position_opened immer hinzufügen für skript
    def on_order_filled(self, order_filled) -> None:
        """
        Actions to be performed when an order is filled.
        """
        ret = self.collector.add_trade_details(order_filled)
        self.log.info(f"Order filled: {order_filled.commission}", color=LogColor.GREEN)

    def on_position_closed(self, position_closed) -> None:
        realized_pnl = position_closed.realized_pnl
        self.realized_pnl += float(realized_pnl) if realized_pnl else 0

    def on_position_opened(self, position_opened) -> None:
        realized_pnl = position_opened.realized_pnl
        #self.realized_pnl += float(realized_pnl) if realized_pnl else 0

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()