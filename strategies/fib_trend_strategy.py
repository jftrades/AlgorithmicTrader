# strategy for simple trend following Fibonacci retracement strategy
from decimal import Decimal
from typing import Any, Dict, List
from datetime import datetime, timezone, time


# Nautilus Core Imports
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.common.enums import LogColor

# Internal Strategy Framework Imports
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager

# Add strategy-specific imports here
from tools.structure.PivotArchive import PivotArchive
from tools.structure.fib_retracement import FibRetracementTool
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage

# -------------------------------------------------
# Multi-Instrument Configuration
# -------------------------------------------------
class FibTrendStrategyConfig(StrategyConfig):
    instruments: List[dict]  # Each entry: {"instrument_id": <InstrumentId>, "bar_types": List of <BarType>, "trade_size_usdt": <Decimal|int|float>}
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    run_id: str

    ema_lookback: int = 14
    min_bars_after_ema_cross: int = 5
    
    # Fibonacci Parameters
    fib_entry_level: float = 0.618
    fib_sl_level: float = 1.0
    fib_only_tp_level: float = -0.62
    
    # Entry tolerances
    fib_entry_tolerance: float = 0.002
    fib_sl_buffer: float = 0.001

    close_positions_on_stop: bool = True
    only_trade_rth: bool = True

class FibTrendStrategy(BaseStrategy, Strategy):
    def __init__(self, config: FibTrendStrategyConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config) 
    
        # Remove: primary instrument derivations (self.instrument_id, self.bar_type, etc.)
        self.risk_manager = None
        self.order_types = None
        self.add_instrument_context()

    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            current_instrument["collector"].initialise_logging_indicator("position", 1)
            current_instrument["collector"].initialise_logging_indicator("realized_pnl", 2)
            current_instrument["collector"].initialise_logging_indicator("unrealized_pnl", 3)
            current_instrument["collector"].initialise_logging_indicator("balance", 4)
            current_instrument["collector"].initialise_logging_indicator("ema", 0)
            
            # Initialize Fibonacci level indicators for visualization
            current_instrument["collector"].initialise_logging_indicator("fib_1_0", 0)
            current_instrument["collector"].initialise_logging_indicator("fib_0_786", 0) 
            current_instrument["collector"].initialise_logging_indicator("fib_0_618", 0)
            current_instrument["collector"].initialise_logging_indicator("fib_0_5", 0)
            current_instrument["collector"].initialise_logging_indicator("fib_0_0", 0)
            current_instrument["collector"].initialise_logging_indicator("fib_ext_0_27", 0)
            current_instrument["collector"].initialise_logging_indicator("fib_ext_0_62", 0)
            current_instrument["collector"].initialise_logging_indicator("fib_ext_1_0", 0)

            # Strategy-specific indicators
            current_instrument["bar_counter"] = 0
            current_instrument["min_bars_after_ema_cross"] = self.config.min_bars_after_ema_cross
            current_instrument["only_trade_rth"] = self.config.only_trade_rth
            current_instrument["rth_start_hour"] = 14
            current_instrument["rth_start_minute"] = 30
            current_instrument["rth_end_hour"] = 21
            current_instrument["rth_end_minute"] = 0
            
            # Fibonacci trading parameters
            current_instrument["fib_entry_level"] = self.config.fib_entry_level
            current_instrument["fib_sl_level"] = self.config.fib_sl_level
            current_instrument["fib_only_tp_level"] = self.config.fib_only_tp_level
            current_instrument["fib_entry_tolerance"] = self.config.fib_entry_tolerance
            current_instrument["fib_sl_buffer"] = self.config.fib_sl_buffer
            
            # Initialize EMA indicators
            current_instrument["ema"] = ExponentialMovingAverage(self.config.ema_lookback)
            current_instrument["ema_reset"] = ExponentialMovingAverage(30)  # For trending readjustment
            
            # Initialize Pivot Archive and Fibonacci Tool
            current_instrument["pivot_archive"] = PivotArchive(strength=2)
            current_instrument["fib_tool"] = FibRetracementTool(current_instrument["pivot_archive"])
            
            # EMA crossover tracking
            current_instrument["prev_price_above_ema"] = None
            current_instrument["bars_since_ema_cross"] = 0
            current_instrument["last_ema_cross_direction"] = None  # 'bullish' or 'bearish'

    def is_rth_time(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument["only_trade_rth"]:
            return True
            
        bar_time = datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=timezone.utc).time()
        rth_start = time(current_instrument["rth_start_hour"], current_instrument["rth_start_minute"])
        rth_end = time(current_instrument["rth_end_hour"], current_instrument["rth_end_minute"])
        
        return rth_start <= bar_time <= rth_end

    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                self.log.info(f"Subscribing to bars: {str(bar_type)}", color=LogColor.GREEN)
                self.subscribe_bars(bar_type)
                self.register_indicator_for_bars(bar_type, ctx["ema"])
                self.register_indicator_for_bars(bar_type, ctx["ema_reset"])
        
        self.log.info(f"Strategy started. Instruments: {', '.join(str(i) for i in self.instrument_ids())}")
        
        # Initialize risk and order management
        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)

    # -------------------------------------------------
    # Event Routing
    # -------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return

        current_instrument["bar_counter"] += 1

        # Provide EMA Reset to PivotArchive for trending readjustment
        if current_instrument["ema_reset"].initialized:
            current_instrument["pivot_archive"].set_ema_reset(current_instrument["ema_reset"].value)

        # Update Pivot Archive and Fibonacci Tool
        pivot_changed = current_instrument["pivot_archive"].update(bar)
        fib_changed = current_instrument["fib_tool"].update(bar)

        
        # Check for pending orders to avoid endless order loops
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
            
        self.entry_logic(bar, current_instrument)
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

    # -------------------------------------------------
    # Entry Logic per Instrument
    # -------------------------------------------------
    def entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        
        if not self.is_rth_time(bar, current_instrument):
            return
            
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return
        if not current_instrument["ema"].initialized:
            self.log.info(f"EMA not ready yet for {instrument_id}, bars needed: {self.config.ema_lookback}")
            return
            
        # Get current EMA value and price
        current_ema = current_instrument["ema"].value
        current_price = float(bar.close)
        
        # Determine if price is above or below EMA
        price_above_ema = current_price > current_ema
        
        # Check for EMA crossover and update tracking
        if current_instrument["prev_price_above_ema"] is not None:
            if not current_instrument["prev_price_above_ema"] and price_above_ema:
                current_instrument["last_ema_cross_direction"] = "bullish"
                current_instrument["bars_since_ema_cross"] = 0
            
            elif current_instrument["prev_price_above_ema"] and not price_above_ema:
                current_instrument["last_ema_cross_direction"] = "bearish"
                current_instrument["bars_since_ema_cross"] = 0
        
        # Increment bars since last crossover
        if current_instrument["last_ema_cross_direction"] is not None:
            current_instrument["bars_since_ema_cross"] += 1
        
        current_instrument["prev_price_above_ema"] = price_above_ema
        
        if current_instrument["bars_since_ema_cross"] < current_instrument["min_bars_after_ema_cross"]:
            return
            
        net_position = self.portfolio.net_position(instrument_id)
        if net_position and net_position != 0:
            return
            
        # Get current Fibonacci levels
        fib_levels = current_instrument["fib_tool"].get_key_levels()
        if not fib_levels:
            return
            
        # Check if we have a valid retracement setup
        fib_retracement = current_instrument["fib_tool"].get_current_fibonacci()
        if not fib_retracement:
            if current_instrument["bar_counter"] % 100 == 0:
                current_instrument["pivot_archive"].get_key_levels()
            return
            
        # Get entry, SL, and TP levels using configurable parameters
        entry_level = current_instrument["fib_entry_level"]     # From YAML: 0.618
        sl_level = current_instrument["fib_sl_level"]           # From YAML: 1.0  
        tp_level = current_instrument["fib_only_tp_level"]      # From YAML: -0.62
        
        # Get the actual prices for these levels
        fib_entry_price = fib_retracement.get_level_price(entry_level) if fib_retracement else None
        fib_sl_price = fib_retracement.get_level_price(sl_level) if fib_retracement else None
        fib_tp_price = fib_retracement.get_level_price(tp_level) if fib_retracement else None
        
        if not all([fib_entry_price, fib_sl_price, fib_tp_price]):
            return
            
        if not self._is_safe_entry(current_price, fib_entry_price, fib_sl_price, price_above_ema):
            return
            
        entry_tolerance = current_instrument["fib_entry_tolerance"]
        price_diff_percent = abs(current_price - fib_entry_price) / fib_entry_price
        
        if price_diff_percent > entry_tolerance:
            return
            
        # LONG ENTRY LOGIC: Above EMA + price near 61.8% fib level
        if price_above_ema and current_instrument["last_ema_cross_direction"] == "bullish":
            if fib_retracement.direction == "bearish":  # FIXED: Should be bearish for LONG entries
                if abs(current_price - fib_entry_price) <= (fib_entry_price * entry_tolerance):
                    self._execute_long_entry(bar, current_instrument, fib_entry_price, fib_sl_price, fib_tp_price)
        
        # SHORT ENTRY LOGIC: Below EMA + price near 61.8% fib level  
        elif not price_above_ema and current_instrument["last_ema_cross_direction"] == "bearish":
            if fib_retracement.direction == "bullish":  # FIXED: Should be bullish for SHORT entries
                if abs(current_price - fib_entry_price) <= (fib_entry_price * entry_tolerance):
                    self._execute_short_entry(bar, current_instrument, fib_entry_price, fib_sl_price, fib_tp_price)
    
    def _is_safe_entry(self, current_price: float, entry_price: float, sl_price: float, is_long: bool) -> bool:
        sl_distance = abs(current_price - sl_price) / current_price
        if sl_distance < 0.005: 
            return False
        
        # Check if already past stop loss
        if is_long and current_price <= sl_price:
            return False
        elif not is_long and current_price >= sl_price:
            return False
            
        return True
    
    def _execute_long_entry(self, bar: Bar, current_instrument: Dict[str, Any], entry_price: float, sl_price: float, tp_price: float):
        instrument_id = bar.bar_type.instrument_id
        
        sl_with_buffer = sl_price - (sl_price * current_instrument["fib_sl_buffer"])
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, int(trade_size_usdt / entry_price))
        
        self.log.info(f"LONG FIBONACCI ENTRY - {instrument_id} | Entry: {entry_price:.2f} | SL: {sl_with_buffer:.2f} | TP: {tp_price:.2f}", color=LogColor.GREEN)
        
        self.order_types.submit_long_bracket_order(
            instrument_id, qty,
            Decimal(str(entry_price)), Decimal(str(sl_with_buffer)), Decimal(str(tp_price))
        )
    
    def _execute_short_entry(self, bar: Bar, current_instrument: Dict[str, Any], entry_price: float, sl_price: float, tp_price: float):
        instrument_id = bar.bar_type.instrument_id
        
        sl_with_buffer = sl_price + (sl_price * current_instrument["fib_sl_buffer"])
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, int(trade_size_usdt / entry_price))
        
        self.log.info(f"SHORT FIBONACCI ENTRY - {instrument_id} | Entry: {entry_price:.2f} | SL: {sl_with_buffer:.2f} | TP: {tp_price:.2f}", color=LogColor.RED)
        
        self.order_types.submit_short_bracket_order(
            instrument_id, qty,
            Decimal(str(entry_price)), Decimal(str(sl_with_buffer)), Decimal(str(tp_price))
        )

    # -------------------------------------------------
    # Order Submission Wrappers
    # -------------------------------------------------
    def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_long_market_order(instrument_id, qty)

    def submit_short_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    # -------------------------------------------------
    # Visualizer / Logging per Instrument
    # -------------------------------------------------
    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)
        
        # Add EMA indicator value for visualization
        ema_value = float(current_instrument["ema"].value) if current_instrument["ema"].value is not None else None
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="ema", value=ema_value)
        
        # Add Fibonacci levels for visualization
        fib_levels = current_instrument["fib_tool"].get_key_levels()
        for level_name, level_price in fib_levels.items():
            if level_price is not None:
                current_instrument["collector"].add_indicator(
                    timestamp=bar.ts_event, 
                    name=level_name, 
                    value=float(level_price)
                )
        
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: InstrumentId = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId required (no global primary instrument anymore).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)