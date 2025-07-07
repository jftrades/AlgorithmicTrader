# hier rein kommt die normale simple RSI strategy, nur mit Tick Daten
# das wird die erste implementuerung von tick Daten

# Standard Library Importe
from decimal import Decimal
from typing import Any
import sys
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta, timezone

# Nautilus Kern offizielle Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType, TradeTick, QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder, StopMarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderEvent, PositionEvent
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.model.enums import AggressorSide  # für BUY/SELL

# Nautilus Kern eigene Importe !!! immer
VIS_PATH = Path(__file__).resolve().parent.parent / "data" / "visualizing"
if str(VIS_PATH) not in sys.path:
    sys.path.insert(0, str(VIS_PATH))

from backtest_visualizer_prototype import BacktestDataCollector  # Optional visualization
from AlgorithmicTrader.crypto.strategies.help_funcs_strategy_crypto import create_tags
from nautilus_trader.common.enums import LogColor

# Weitere/Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from nautilus_trader.model.objects import Currency

class RSITickSimpleStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    tick_buffer_size: int = 1000
    close_positions_on_stop: bool = True 
    
class RSITickSimpleStrategy(Strategy):
    def __init__(self, config: RSITickSimpleStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.tick_buffer_size = config.tick_buffer_size 
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.last_rsi_cross = None 
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.realized_pnl = 0
        self.stopped = False  # Flag to indicate if the strategy has been stopped
        self.tick_counter = 0
        self.trade_ticks = []


    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_trade_ticks(self.instrument_id)
        bar_type = BarType.from_str(f"{self.instrument_id}-5-MINUTE-LAST-INTERNAL")
        self.subscribe_bars(bar_type)
        self.subscribe_trade_ticks(self.instrument_id)
        self.log.info("Tick Strategy started!")

        self.collector = BacktestDataCollector()  # Optional visualization
        self.collector.initialise_logging_indicator("position", 1)
        self.collector.initialise_logging_indicator("realized_pnl", 2)
        self.collector.initialise_logging_indicator("unrealized_pnl", 3)
        self.collector.initialise_logging_indicator("balance", 4)

        # Get the account using the venue instead of account_id
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        if account:
            usdt_balance = account.balance_total(Currency.from_str("USDT"))
            self.log.info(f"USDT balance: {usdt_balance}")
        else:
            self.log.warning(f"No account found for venue: {venue}")

    def get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None

    def on_bar(self, bar: Bar):
        self.rsi.handle_bar(bar)
        self.last_rsi = self.rsi.value if self.rsi.initialized else None
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
        

    def on_trade_tick(self, tick: TradeTick) -> None:  
        rsi_value = self.rsi.value if self.rsi.initialized else None
        if rsi_value is None:
            return  # RSI noch nicht initialisiert, daher keine Logik ausführen
        self.tick_counter += 1
        self.trade_ticks.append(tick)
        if len(self.trade_ticks) > self.tick_buffer_size:
            self.trade_ticks.pop(0)
        
        # Prüfe, ob bereits eine Order offen ist (pending), um Endlos-Orders zu vermeiden
        open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        if open_orders:
            return  # Warten, bis Order ausgeführt ist

        # Entry/Exit-Logik - tick-genau
        if rsi_value > self.rsi_overbought:
            if self.last_rsi_cross != "rsi_overbought":
                self.close_position()
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=Quantity(self.trade_size, self.instrument.size_precision),
                    time_in_force=TimeInForce.GTC,
                    tags=create_tags(action="SHORT", type="OPEN")
                )
                self.submit_order(order)
                self.collector.add_trade(order)
            self.last_rsi_cross = "rsi_overbought"
        elif rsi_value < self.rsi_oversold:
            if self.last_rsi_cross != "rsi_oversold":
                self.close_position()
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=Quantity(self.trade_size, self.instrument.size_precision),
                    time_in_force=TimeInForce.GTC,
                    tags=create_tags(action="BUY", type="OPEN")
                )
                self.submit_order(order)
                self.collector.add_trade(order)
            self.last_rsi_cross = "rsi_oversold"

        # VISUALIZER UPDATE - Jeden Tick für vollständige Tick-Daten
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balances_total()
        #self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)
        
        self.tick_counter += 1
        if self.tick_counter % 1000 == 0:
            self.collector.add_indicator(timestamp=tick.ts_event, name="position", value=net_position)
            self.collector.add_indicator(timestamp=tick.ts_event, name="RSI", value=float(rsi_value))
            self.collector.add_indicator(timestamp=tick.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
            self.collector.add_indicator(timestamp=tick.ts_event, name="realized_pnl", value=float(self.realized_pnl))
            self.collector.add_indicator(timestamp=tick.ts_event, name="balance", value=usdt_balance)

    # weitere on methoden z.B.
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
                self.log.info(f"Position quantity is zero, nothing to close.")
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
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")
        self.stopped = True  
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
        realized_pnl = float(self.portfolio.realized_pnl(self.instrument_id))  # Unrealized PnL
        #self.log.info(f"position.quantity: {net_position}", LogColor.RED)
        self.realized_pnl += unrealized_pnl+realized_pnl if unrealized_pnl is not None else 0
        unrealized_pnl = 0
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double() 
        self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)


        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="account_balance", value=usdt_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
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
    
    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()