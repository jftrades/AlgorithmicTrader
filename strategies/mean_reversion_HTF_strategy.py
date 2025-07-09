# hier rein kommt dann die HTF mean reversion strategy basierend auf:
# RSI, vllt VWAP und breakout oder so in der richtigen Zone - rumprobieren
# diese strat wird dann gehedged mit einer nur trendfollowing strategie

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
from tools.help_funcs.help_funcs_strategy import create_tags
from nautilus_trader.common.enums import LogColor

# Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex


class MeanReversionHTFStrategyIndexConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    close_positions_on_stop: bool = True 

class MeanReversionHTFStrategyIndex(Strategy):
    def __init__(self, config:MeanReversionHTFStrategyIndexConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        if isinstance(config.bar_type, str):
            self.bar_type = BarType.from_str(config.bar_type)
        else:
            self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.last_rsi_cross = None
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.realized_pnl = 0
        self.bar_counter = 0
        self.stopped = False

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.log.info("Strategy started!")

        self.collector = BacktestDataCollector()
        self.collector.initialise_logging_indicator("RSI", 1)
        self.collector.initialise_logging_indicator("position", 2)
        self.collector.initialise_logging_indicator("realized_pnl", 3)
        self.collector.initialise_logging_indicator("unrealized_pnl", 4)
        self.collector.initialise_logging_indicator("balance", 5)

    def get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None
    
    def long_setup(self, rsi_value):
        if rsi_value < self.rsi_oversold:
            self.rsi_oversold_triggered = True

        if self.rsi_oversold_triggered and rsi_value <= 0.45:
            if <weitere_bedingung_1> and <weitere_bedingung_2>:
                self.close_position()
        pass

    def short_setup(self, rsi_value):
        if rsi_value > self.rsi_oversold:
            self.rsi_overbought_triggered = True
        pass

        if self.rsi_overbought_triggered and rsi_value <= 0.55:
            if <weitere_bedingung_1> and <weitere_bedingung_2>:
                self.close_position()
        pass
    
    def on_bar(self, bar: Bar) -> None:
        self.bar_counter += 1
        # USDT Balance vor jeder Bar holen: (für z.B.prozentuales Risk management)
        account_id = AccountId("BINANCE-001")
        account = self.cache.account(account_id)
        usdt_free = account.balance(USDT).free
        usdt_balance = Decimal(str(usdt_free).split(" ")[0]) if usdt_free else Decimal("0")
        rsi_value = self.rsi.value

        # Prüfe, ob bereits eine Order offen ist (pending), um Endlos-Orders zu vermeiden
        open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        if open_orders:
            return  # Warten, bis Order ausgeführt ist
        
        # Kennzeichnen, ob Schwellen schon überschritten wurden:
        if not hasattr(self, "rsi_overbought_triggered"):
            self.rsi_overbought_triggered = False
        if not hasattr(self, "rsi_oversold_triggered"):
            self.rsi_oversold_triggered = False

        # LONG Setup wird ausgeführt:
        self.long_setup(rsi_value)
        # SHORT Setup wird ausgeführt:
        self.short_setup(rsi_value)

        # VISUALIZER UPDATEN
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balances_total()
        #self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)
        
        self.collector.add_indicator(timestamp=bar.ts_event, name="account_balance", value=usdt_balance)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=float(rsi_value) if rsi_value is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        if net_position is not None and net_position != 0:
            self.log.info(f"Closing position for {self.instrument_id} at market price.")
            #self.log.info(f"position.quantity: {net_position}", LogColor.RED)
            # Always submit the opposite side to close
            if net_position > 0:
                order_side = OrderSide.SELL
                action = "SHORT"
            elif net_position < 0:
                order_side = OrderSide.BUY
                action = "BUY"
            else:
                self.log.info("Position quantity is zero, nothing to close.")
                return
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=order_side,
                quantity=Quantity(abs(net_position), self.instrument.size_precision),
                time_in_force=TimeInForce.GTC,
                tags=create_tags(action=action, type="CLOSE")
            )
            #unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
            #self.realized_pnl += float(unrealized_pnl) if unrealized_pnl else 0
            self.submit_order(order)
            self.collector.add_trade(order)
        else:
            self.log.info(f"No open position to close for {self.instrument_id}.")
            
        if self.stopped:
            logging_message = self.collector.save_data()
            self.log.info(logging_message, color=LogColor.GREEN)
    
    def on_stop(self) -> None:
        position = self.get_position()
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")
        self.stopped = True  

        # VISUALIZER UPDATEN
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balances_total()
        #self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)

        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="balance", value=usdt_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="RSI", value=float(self.last_rsi) if self.last_rsi is not None else None)
        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)
        #self.collector.visualize()  # Visualize the data if enabled

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
