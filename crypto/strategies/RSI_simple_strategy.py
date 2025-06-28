# Standard Library Importe
from decimal import Decimal
from typing import Any

# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, TradeTick, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from help_funcs import create_tags
from nautilus_trader.common.enums import LogColor

# Nautilus Strategie spezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex

################
import sys
from pathlib import Path

# Pfad zum visualizing-Ordner hinzufügen
VIS_PATH = Path(__file__).resolve().parent.parent / "data" / "visualizing"
if str(VIS_PATH) not in sys.path:
    sys.path.insert(0, str(VIS_PATH))

from backtest_visualizer_prototype import BacktestDataCollector
###################



# ab hier der Code für die Strategie
class RSISimpleStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    close_positions_on_stop: bool = True
    
    
class RSISimpleStrategy(Strategy):
    def __init__(self, config: RSISimpleStrategyConfig):
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
        self.close_positions_on_stop = config.close_positions_on_stop
        self.rsi = RelativeStrengthIndex(period=self.rsi_period)
        self.last_rsi_cross = None
    
        # Debug: Welche Attribute/Möglichkeiten gibt es?
        print("STRATEGY DIR:", dir(self))
        if hasattr(self, "portfolio"):
            print("PORTFOLIO DIR:", dir(self.portfolio))

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.subscribe_trade_ticks(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)
        self.log.info("Strategy started!")
        self.collector = BacktestDataCollector()
        self.collector.initialise_logging_indicator("RSI", 1)
        

    def get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None

    def on_bar(self, bar: Bar) -> None:
        self.rsi.handle_bar(bar)
        if not self.rsi.initialized:
            return
        self.log.info(f"position is not None and position.is_open: {self.get_position() is not None and self.get_position().is_open}", LogColor.CYAN)

        rsi_value = self.rsi.value
        position = self.get_position()

        # Prüfe, ob bereits eine Order offen ist (pending), um Endlos-Orders zu vermeiden
        open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        if open_orders:
            return  # Warten, bis Order ausgeführt ist

        # Entry/Exit-Logik
        if rsi_value > self.rsi_overbought:
            if self.last_rsi_cross is not "rsi_overbought":
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
        if rsi_value < self.rsi_oversold:
            if self.last_rsi_cross is not "rsi_oversold":
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
            
        self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=float(rsi_value) if rsi_value is not None else None)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)

    def close_position(self) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        if net_position is not None and net_position != 0:
            self.log.info(f"Closing position for {self.instrument_id} at market price.")
            self.log.info(f"position.quantity: {net_position}", LogColor.RED)
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
            self.submit_order(order)
            self.collector.add_trade(order)
        else:
            self.log.info(f"No open position to close for {self.instrument_id}.")

    def on_stop(self) -> None:
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")
        logging_message = self.collector.save_data()
        self.log.info(logging_message)
        #self.collector.visualize()  # Visualize the data if enabled

    def on_order_filled(self, order_filled) -> None:
        """
        Actions to be performed when an order is filled.
        """

        ret = self.collector.add_trade_details(order_filled)
        #self.log.info(
        #        f"Order filled: {order_filled.client_order_id} {ret}",
        #        color=LogColor.RED,
        #    )

    def on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()

        # Notiz von Ferdi: sowohl def on_trade_tick als auch def on_close_position als auch def on_error
        # sind hier theoreitisch nicht notwendig, da sie nur für die Fehlerbehandlung und das Logging
        # genutzt werden. Ausser natürlich unser Code wird komplexer und wir brauchen sie
        # trotzdem für Praxis genau wie on_start einfach in die Projekt mit einfügen ig


