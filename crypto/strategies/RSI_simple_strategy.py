# Standard Library Importe
from decimal import Decimal
from typing import Any
import pandas as pd

# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, TradeTick, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce

# Nautilus Strategie spezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from nautilus_trader.core.datetime import unix_nanos_to_dt


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
        self.prev_rsi = None
        self.just_closed = False


    def on_start(self) -> None:
        """Strategie-Start mit verbessertem Logging"""
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        
        self.log.info("="*50)
        self.log.info("🚀 RSI STRATEGY STARTED")
        self.log.info(f"📊 Instrument: {self.instrument_id}")
        self.log.info(f"📈 Bar Type: {self.bar_type}")
        self.log.info(f"💰 Trade Size: {self.trade_size}")
        self.log.info(f"🔢 RSI Period: {self.rsi_period}")
        self.log.info(f"📉 RSI Oversold: {self.rsi_oversold}")
        self.log.info(f"📈 RSI Overbought: {self.rsi_overbought}")
        self.log.info("="*50)

    def get_total_position_size(self):
        """Berechne Position Size MIT Vorzeichen (+ für LONG, - für SHORT)"""
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        
        total_quantity = 0.0
        for pos in positions:
            signed_qty = float(pos.signed_qty)
            total_quantity += signed_qty
        
        return total_quantity

    def close_all_positions(self):
        """Schließe ALLE Positionen mit EINER Order basierend auf Netto-Position"""
        total_position = self.get_total_position_size()
        
        if abs(total_position) <= 0.001:
            self.log.info("No significant position to close")
            return
        
        order_side = OrderSide.SELL if total_position > 0 else OrderSide.BUY
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=order_side,
            quantity=Quantity(abs(total_position), self.instrument.size_precision),
            time_in_force=TimeInForce.GTC,
        )
        self.log.info(f"🔄 CLOSING total position: {total_position} with single order")
        self.submit_order(order)

    def on_bar(self, bar: Bar) -> None:
        """Haupthandelslogik mit detailliertem Logging"""
        self.rsi.handle_bar(bar)
        if not self.rsi.initialized:
            return

        rsi_value = self.rsi.value
        total_position = self.get_total_position_size()
        
        # Kompaktes Bar-Logging
        bar_time = pd.to_datetime(bar.ts_event, unit='ns')
        self.log.info(f"📊 [{bar_time}] Price: {bar.close}, RSI: {rsi_value:.2f}, Position: {total_position}")
        
        if self.prev_rsi is not None:
            # Signal-Detection
            long_signal = self.prev_rsi >= self.rsi_oversold and rsi_value < self.rsi_oversold
            short_signal = self.prev_rsi <= self.rsi_overbought and rsi_value > self.rsi_overbought
            
            # LONG SIGNAL
            if long_signal:
                self.log.info(f"🟢 LONG SIGNAL! RSI crossed below {self.rsi_oversold}")
                if total_position < -0.001:
                    self.log.info(f"🔄 Closing SHORT position (Total: {total_position})")
                    self.close_all_positions()
                elif abs(total_position) <= 0.001:
                    self.log.info(f"🚀 Opening LONG position, size: {self.trade_size}")
                    order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)

            # SHORT SIGNAL  
            elif short_signal:
                self.log.info(f"🔴 SHORT SIGNAL! RSI crossed above {self.rsi_overbought}")
                if total_position > 0.001:
                    self.log.info(f"🔄 Closing LONG position (Total: {total_position})")
                    self.close_all_positions()
                elif abs(total_position) <= 0.001:
                    self.log.info(f"📉 Opening SHORT position, size: {self.trade_size}")
                    order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(self.trade_size, self.instrument.size_precision),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)

        self.prev_rsi = rsi_value

    def on_stop(self) -> None:
        """Strategie-Stop mit finaler Position-Schließung"""
        self.log.info("="*50)
        self.log.info("🛑 STRATEGY STOPPING - FORCE CLOSING ALL POSITIONS")
        total_position = self.get_total_position_size()
        self.log.info(f"📊 Final Position Size: {total_position}")
        
        if abs(total_position) > 0.001:
            self.close_all_positions()
            self.log.info("✅ All positions closed")
        else:
            self.log.info("✅ No positions to close")
        
        self.log.info("🏁 RSI STRATEGY STOPPED")
        self.log.info("="*50)

    def on_error(self, error: Exception) -> None:
        """Fehlerbehandlung mit Position-Schließung"""
        self.log.error(f"❌ STRATEGY ERROR: {error}")
        if self.close_positions_on_stop:
            self.log.info("🔄 Closing all positions due to error")
            self.close_all_positions()
        self.stop()

        # Notiz von Ferdi: sowohl def on_trade_tick als auch def on_close_position als auch def on_error
        # sind hier theoreitisch nicht notwendig, da sie nur für die Fehlerbehandlung und das Logging
        # genutzt werden. Ausser natürlich unser Code wird komplexer und wir brauchen sie
        # trotzdem für Praxis genau wie on_start einfach in die Projekt mit einfügen ig

            
