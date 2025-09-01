# in here will be the code for the VP_VWAP_trend_strategy
# the VP will be used if broken to indicate trend day and VWAP will be used for entry

from decimal import Decimal
from typing import Any, Dict, List
import pandas as pd

from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.common.enums import LogColor

from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager

from tools.indicators.VWAP_intraday import VWAPIntraday
from nautilus_trader.indicators.atr import AverageTrueRange


class VPVWAPTrendStrategyConfig(StrategyConfig):
    instruments: List[dict]
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    run_id: str
    bars_after_break: int = 5
    entry_band_long: float = 0.0
    entry_band_short: float = 0.0
    sl_atr_multiplier: float = 2.0
    tp_atr_multiplier: float = 4.0
    atr_period: int = 14
    close_positions_on_stop: bool = True

class VPVWAPTrendStrategy(BaseStrategy, Strategy):
    def __init__(self, config: VPVWAPTrendStrategyConfig):
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
            current_instrument["collector"].initialise_logging_indicator("vwap", 5)
            current_instrument["collector"].initialise_logging_indicator("vwap_upper_band", 6)
            current_instrument["collector"].initialise_logging_indicator("vwap_lower_band", 7)
            current_instrument["collector"].initialise_logging_indicator("pdh", 8)
            current_instrument["collector"].initialise_logging_indicator("pdl", 9)
            
            # Indicators
            current_instrument["vwap_indicator"] = VWAPIntraday()
            current_instrument["atr"] = AverageTrueRange(period=self.config.atr_period)
            
            # State tracking
            current_instrument["prev_day_high"] = None
            current_instrument["prev_day_low"] = None
            current_instrument["pdh_pdl_broken"] = False
            current_instrument["break_direction"] = None
            current_instrument["bars_since_break"] = 0
            current_instrument["second_bar_price"] = None
            current_instrument["bar_counter"] = 0
            current_instrument["last_day"] = None

    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                self.log.info(f"Subscribing to bars: {str(bar_type)}", color=LogColor.GREEN)
                self.subscribe_bars(bar_type)
        
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
        current_day = pd.Timestamp(bar.ts_init, tz="UTC").day
        
        # Track previous day high/low
        if current_instrument["last_day"] is not None and current_day != current_instrument["last_day"]:
            # New day - reset states
            current_instrument["pdh_pdl_broken"] = False
            current_instrument["break_direction"] = None
            current_instrument["bars_since_break"] = 0
            current_instrument["second_bar_price"] = None
            
        current_instrument["last_day"] = current_day
        
        # Update indicators
        current_instrument['vwap_indicator'].update(bar)
        current_instrument["atr"].handle_bar(bar)
        
        if not current_instrument['vwap_indicator'].initialized or not current_instrument["atr"].initialized:
            return
        
        # Store daily H/L for comparison
        if current_instrument["prev_day_high"] is None:
            current_instrument["prev_day_high"] = bar.high
            current_instrument["prev_day_low"] = bar.low
        else:
            if current_day != current_instrument["last_day"]:
                current_instrument["prev_day_high"] = bar.high
                current_instrument["prev_day_low"] = bar.low
        
        # Check for pending orders
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
        current_price = bar.close
        vwap_indicator = current_instrument["vwap_indicator"]
        
        # Step 1: Check for PDH/PDL break
        if not current_instrument["pdh_pdl_broken"]:
            if (current_instrument["prev_day_high"] and current_price > current_instrument["prev_day_high"]):
                current_instrument["pdh_pdl_broken"] = True
                current_instrument["break_direction"] = "high"
                current_instrument["bars_since_break"] = 0
                self.log.info(f"PDH broken: {current_price} > {current_instrument['prev_day_high']}")
                
            elif (current_instrument["prev_day_low"] and current_price < current_instrument["prev_day_low"]):
                current_instrument["pdh_pdl_broken"] = True
                current_instrument["break_direction"] = "low"
                current_instrument["bars_since_break"] = 0
                self.log.info(f"PDL broken: {current_price} < {current_instrument['prev_day_low']}")
            return
        
        # Step 2: Count bars after break and store second bar price
        current_instrument["bars_since_break"] += 1
        if current_instrument["bars_since_break"] == 2:
            current_instrument["second_bar_price"] = current_price
            
        # Step 3: Wait for required bars after break (more robust logic)
        if current_instrument["bars_since_break"] <= self.config.bars_after_break:
            return
            
        # Step 4 & 5: Execute long or short entry
        if current_instrument["break_direction"] == "high":
            self._execute_long_entry(bar, current_instrument, vwap_indicator)
        else:
            self._execute_short_entry(bar, current_instrument, vwap_indicator)

    def _execute_long_entry(self, bar: Bar, current_instrument: Dict[str, Any], vwap_indicator):
        """Execute long entry after PDH break and retrace to VWAP band"""
        current_price = bar.close
        vwap_value = vwap_indicator.value
        
        # Get entry level based on long band configuration
        if self.config.entry_band_long == 0.0:
            entry_level = vwap_value
        else:
            _, upper_band, lower_band = vwap_indicator.get_bands(self.config.entry_band_long)
            entry_level = vwap_value if lower_band is None else lower_band
        
        # Check if price retraced to entry level
        if current_price > entry_level:
            return
            
        # Get ATR for SL/TP calculation
        atr_value = current_instrument["atr"].value
        if atr_value is None or atr_value <= 0:
            return
            
        # Calculate levels
        entry_price = current_price
        sl_distance = atr_value * self.config.sl_atr_multiplier
        tp_distance = atr_value * self.config.tp_atr_multiplier
        sl_price = entry_price - sl_distance
        tp_price = entry_price + tp_distance
        
        # 1% risk position sizing
        risk_amount = self.portfolio.base_currency.balance().amount.as_double() * (self.config.risk_percent / 100)
        position_size = int(risk_amount / sl_distance)
        
        if position_size > 0:
            self.order_types.submit_long_bracket_order(
                bar.bar_type.instrument_id, position_size, 
                Decimal(str(entry_price)), Decimal(str(sl_price)), Decimal(str(tp_price))
            )
            current_instrument["pdh_pdl_broken"] = False
            self.log.info(f"LONG entry: {entry_price}, SL: {sl_price}, TP: {tp_price}, Size: {position_size}")

    def _execute_short_entry(self, bar: Bar, current_instrument: Dict[str, Any], vwap_indicator):
        """Execute short entry after PDL break and retrace to VWAP band"""
        current_price = bar.close
        vwap_value = vwap_indicator.value
        
        # Get entry level based on short band configuration
        if self.config.entry_band_short == 0.0:
            entry_level = vwap_value
        else:
            _, upper_band, lower_band = vwap_indicator.get_bands(self.config.entry_band_short)
            entry_level = vwap_value if upper_band is None else upper_band
        
        # Check if price retraced to entry level
        if current_price < entry_level:
            return
            
        # Get ATR for SL/TP calculation
        atr_value = current_instrument["atr"].value
        if atr_value is None or atr_value <= 0:
            return
            
        # Calculate levels
        entry_price = current_price
        sl_distance = atr_value * self.config.sl_atr_multiplier
        tp_distance = atr_value * self.config.tp_atr_multiplier
        sl_price = entry_price + sl_distance
        tp_price = entry_price - tp_distance
        
        # 1% risk position sizing
        risk_amount = self.portfolio.base_currency.balance().amount.as_double() * (self.config.risk_percent / 100)
        position_size = int(risk_amount / sl_distance)
        
        if position_size > 0:
            self.order_types.submit_short_bracket_order(
                bar.bar_type.instrument_id, position_size,
                Decimal(str(entry_price)), Decimal(str(sl_price)), Decimal(str(tp_price))
            )
            current_instrument["pdh_pdl_broken"] = False
            self.log.info(f"SHORT entry: {entry_price}, SL: {sl_price}, TP: {tp_price}, Size: {position_size}")

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
        
        vwap_indicator = current_instrument["vwap_indicator"]
        if vwap_indicator.initialized:
            # Log VWAP and bands
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap", value=float(vwap_indicator.value))
            
            _, upper_1, lower_1 = vwap_indicator.get_bands(1.0)
            if upper_1 is not None:
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_upper_band", value=float(upper_1))
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_lower_band", value=float(lower_1))
        
        # Log PDH/PDL
        if current_instrument["prev_day_high"]:
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="pdh", value=float(current_instrument["prev_day_high"]))
        if current_instrument["prev_day_low"]:
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="pdl", value=float(current_instrument["prev_day_low"]))
        
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