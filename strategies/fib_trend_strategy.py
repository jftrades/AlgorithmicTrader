# strategy for simple trend following Fibonacci retracement strategy
from decimal import Decimal
from typing import Any, Dict, List
import pandas as pd
from datetime import datetime


# Nautilus Core Imports
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.common.enums import LogColor

# Internal Strategy Framework Imports
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager

# Add strategy-specific imports here
from tools.structure.PivotArchive import PivotArchive
from tools.structure.fib_retracement import FibRetracement
from nautilus_trader.indicators.atr import AverageTrueRange
from nautilus_trader.indicators.ema import ExponentialMovingAverage

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
            
            # Strategy-specific indicators
            current_instrument["bar_counter"] = 0
            current_instrument["min_bars_after_ema_cross"] = self.config.min_bars_after_ema_cross
            current_instrument["only_trade_rth"] = self.config.only_trade_rth
            current_instrument["rth_start_hour"] = 14
            current_instrument["rth_start_minute"] = 30
            current_instrument["rth_end_hour"] = 21
            current_instrument["rth_end_minute"] = 0
            
            # Initialize EMA indicator
            current_instrument["ema"] = ExponentialMovingAverage(self.config.ema_lookback)
            
            # EMA crossover tracking
            current_instrument["prev_price_above_ema"] = None
            current_instrument["bars_since_ema_cross"] = 0
            current_instrument["last_ema_cross_direction"] = None  # 'bullish' or 'bearish'

    def is_rth_time(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument["only_trade_rth"]:
            return True
            
        import datetime
        bar_time = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(current_instrument["rth_start_hour"], current_instrument["rth_start_minute"])
        rth_end = datetime.time(current_instrument["rth_end_hour"], current_instrument["rth_end_minute"])
        
        return rth_start <= bar_time <= rth_end

    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                self.log.info(f"Subscribing to bars: {str(bar_type)}", color=LogColor.GREEN)
                self.subscribe_bars(bar_type)
                self.register_indicator_for_bars(bar_type, ctx["ema"])
        
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

        current_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).date()

        
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
        if not self.is_rth_time(bar, current_instrument):
            return
            
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return
        if not current_instrument["ema"].initialized:
            self.log.info(f"EMA not ready yet for {instrument_id}, bars needed: {current_instrument['ema_lookback']}")
            return
            
        # Get current EMA value and price
        current_ema = current_instrument["ema"].value
        
        # Determine if price is above or below EMA
        price_above_ema = bar.close > current_ema
        
        # Check for EMA crossover
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
        
        # Store current state for next bar comparison
        current_instrument["prev_price_above_ema"] = price_above_ema

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