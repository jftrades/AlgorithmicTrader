# ================================================================================
# BAR STRATEGY TEMPLATE - Nautilus Trader
# Minimales Template für Bar-basierte Strategien mit Nautilus Trader
# ================================================================================
# Standard Library Importe
from decimal import Decimal
from typing import Any
import sys
from pathlib import Path

# Nautilus Kern offizielle Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder, StopMarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderEvent, PositionEvent
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.currencies import USDT, BTC

# Nautilus Kern eigene Importe !!! immer
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from AlgorithmicTrader.crypto.strategies.tools_crypto_strategies.help_funcs_strategy_crypto import create_tags
from nautilus_trader.common.enums import LogColor

# Weitere/Strategiespezifische Importe
# from nautilus_trader...

class NameDerStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    #...
    close_positions_on_stop: bool = True 
    
class NameDerStrategy(Strategy):
    def __init__(self, config: NameDerStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        if isinstance(config.bar_type, str):
            self.bar_type = BarType.from_str(config.bar_type)
        else:
            self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        #...
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.realized_pnl = 0
        self.bar_counter = 0

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
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

    def on_bar(self, bar: Bar) -> None: 
        self.bar_counter += 1
        # Beispiel für USDT Balance holen:
        # account_id = AccountId("BINANCE-001")
        # account = self.cache.account(account_id)
        # usdt_free = account.balance(USDT).free
        # usdt_balance = Decimal(str(usdt_free).split(" ")[0]) if usdt_free else Decimal("0")
        
        # Beispiel für Bracket Order:
        # bracket_order = self.order_factory.bracket(
        #     instrument_id=self.instrument_id,
        #     order_side=OrderSide.BUY,  # oder SELL
        #     quantity=Quantity(position_size, self.instrument.size_precision),
        #     sl_trigger_price=Price(stop_loss, self.instrument.price_precision),
        #     tp_price=Price(take_profit, self.instrument.price_precision),
        #     time_in_force=TimeInForce.GTC,
        #     entry_tags=create_tags(action="BUY", type="BRACKET", sl=stop_loss, tp=take_profit)
        # )
        # self.submit_order_list(bracket_order)
        # self.collector.add_trade(bracket_order.orders[0])  # Entry Order für Tracking

        # HILFSBLOCK FÜR VISUALIZER: - anpassen je nach Indikatoren etc
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balances_total()
        #self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)

        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)

    # die weiteren on_Methoden...
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
        self.log.info(f"Order filled: {order_filled.commission}", color=LogColor.GREEN)

    def on_position_closed(self, position_closed) -> None:

        realized_pnl = position_closed.realized_pnl  # Realized PnL
        self.realized_pnl += float(realized_pnl) if realized_pnl else 0
        self.collector.add_closed_trade(position_closed)

    def on_position_opened(self, position_opened) -> None:
        realized_pnl = position_opened.realized_pnl
        #self.realized_pnl += float(realized_pnl) if realized_pnl else 0

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()