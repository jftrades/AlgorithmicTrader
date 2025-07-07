# Standard Library Importe
from decimal import Decimal
import time
from typing import Any

# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, TradeTick, BarType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from AlgorithmicTrader.crypto.strategies.help_funcs_strategy_crypto import create_tags
from nautilus_trader.common.enums import LogColor

# Nautilus Strategie spezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector

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
        self.realized_pnl = 0
        self.stopped = False  # Flag to indicate if the strategy has been stopped
        
    
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
        self.collector.initialise_logging_indicator("position", 2)
        self.collector.initialise_logging_indicator("realized_pnl", 3)
        self.collector.initialise_logging_indicator("unrealized_pnl", 4)
        self.collector.initialise_logging_indicator("account_balance", 5)
        #self.collector.initialise_logging_indicator("balance", 5)
        
        
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

    def on_bar(self, bar: Bar) -> None:
        self.rsi.handle_bar(bar)
        if not self.rsi.initialized:
            return

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


        
        
        # Debug: Alle Portfolio-Methoden anzeigen
        #if hasattr(self, 'portfolio'):
        #    portfolio_methods = [method for method in dir(self.portfolio) if not method.startswith('_')]
         #   methods_str = "\n".join(f"  - {method}" for method in sorted(portfolio_methods))
            #self.log.info(f"🔍 PORTFOLIO ATTRIBUTES/METHODS:\n{methods_str}\n{'=' * 50}", color=LogColor.RED)

        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)  # Unrealized PnL
        #realized_pnl = self.portfolio.realized_pnl(self.instrument_id)
        #self.log.info(f"position.quantity: {net_position}", LogColor.RED)
        
        # Get account balance using venue
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double() if account else None
        #self.log.info(f"acc balances: {usdt_balance}", LogColor.RED)

        self.collector.add_indicator(timestamp=bar.ts_event, name="account_balance", value=usdt_balance)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="RSI", value=float(rsi_value) if rsi_value is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
    
        #self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=float(usdt_balance) if usdt_balance is not None else None)
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

        # Notiz von Ferdi: sowohl def on_trade_tick als auch def on_close_position als auch def on_error
        # sind hier theoreitisch nicht notwendig, da sie nur für die Fehlerbehandlung und das Logging
        # genutzt werden. Ausser natürlich unser Code wird komplexer und wir brauchen sie
        # trotzdem für Praxis genau wie on_start einfach in die Projekt mit einfügen ig


# def on_trade_tick als auch def on_close_position als auch def on_error
        # sind hier theoreitisch nicht notwendig, da sie nur für die Fehlerbehandlung und das Logging
        # genutzt werden. Ausser natürlich unser Code wird komplexer und wir brauchen sie
        # trotzdem für Praxis genau wie on_start einfach in die Projekt mit einfügen ig

