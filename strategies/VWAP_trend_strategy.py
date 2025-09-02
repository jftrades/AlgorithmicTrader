# in here will be the code for the VP_VWAP_trend_strategy
# the VP will be used if broken to indicate trend day and VWAP will be used for entry

# problems rn:
# - we have to define what which open means (if we open above through gap should directly look for VWAP trend following)
# - risk not working rigt -> 
from decimal import Decimal
from typing import Any, Dict, List

from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.common.enums import LogColor

from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager

from tools.indicators.VWAP_intraday import VWAPIntraday
from nautilus_trader.indicators.atr import AverageTrueRange


class VWAPTrendStrategyConfig(StrategyConfig):
    instruments: List[dict]
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    run_id: str
    min_bars_vwap_extremes: int = 10
    min_band_trend_long: float = 1.0
    min_band_trend_short: float = 1.0
    entry_band_long: float = 0.0
    entry_band_short: float = 0.0
    sl_atr_multiplier: float = 2.0
    tp_atr_multiplier: float = 4.0
    atr_period: int = 14
    close_positions_on_stop: bool = True
    only_trade_rth: bool = True

class VWAPTrendStrategy(BaseStrategy, Strategy):
    def __init__(self, config: VWAPTrendStrategyConfig):
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
            current_instrument["collector"].initialise_logging_indicator("vwap", 0)
            current_instrument["collector"].initialise_logging_indicator("vwap_upper_band", 0)
            current_instrument["collector"].initialise_logging_indicator("vwap_lower_band", 0)
            current_instrument["collector"].initialise_logging_indicator("vwap_upper_band_2", 0)
            current_instrument["collector"].initialise_logging_indicator("vwap_lower_band_2", 0)
            current_instrument["collector"].initialise_logging_indicator("vwap_upper_band_3", 0)
            current_instrument["collector"].initialise_logging_indicator("vwap_lower_band_3", 0)
            current_instrument["collector"].initialise_logging_indicator("pdh", 8)
            current_instrument["collector"].initialise_logging_indicator("pdl", 9)
            
            # Indicators
            current_instrument["vwap_indicator"] = VWAPIntraday()
            # Configure VWAP extremes tracking with strategy parameters
            current_instrument["vwap_indicator"].configure_extremes(
                min_bars_vwap_extremes=self.config.min_bars_vwap_extremes,
                min_band_trend_long=self.config.min_band_trend_long,
                min_band_trend_short=self.config.min_band_trend_short
            )
            current_instrument["atr"] = AverageTrueRange(period=self.config.atr_period)
            
            # State tracking
            current_instrument["prev_day_high"] = None
            current_instrument["prev_day_low"] = None
            current_instrument["daily_highs"] = []  # List of all highs for current day (sorted descending)
            current_instrument["daily_lows"] = []   # List of all lows for current day (sorted ascending)
            current_instrument["last_bar_date"] = None
            current_instrument["pdh_broken"] = False
            current_instrument["pdl_broken"] = False
            current_instrument["bar_counter"] = 0
            current_instrument["only_trade_rth"] = self.config.only_trade_rth
            current_instrument["traded_today"] = False
            current_instrument["prev_bar_close"] = None
            current_instrument["opening_validated"] = False  # Track if opening is within PDH/PDL range
            current_instrument["first_bar_of_day"] = True    # Track first bar to capture opening
            # RTH setup for US futures/stocks (9:30 AM - 4:00 PM ET = 14:30 - 21:00 UTC)
            current_instrument["rth_start_hour"] = 14
            current_instrument["rth_start_minute"] = 30
            current_instrument["rth_end_hour"] = 21
            current_instrument["rth_end_minute"] = 0

    def is_rth_time(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument["only_trade_rth"]:
            return True
            
        import datetime
        bar_time = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(current_instrument["rth_start_hour"], current_instrument["rth_start_minute"])
        rth_end = datetime.time(current_instrument["rth_end_hour"], current_instrument["rth_end_minute"])
        
        return rth_start <= bar_time <= rth_end

    def has_valid_previous_day_levels(self, current_instrument: Dict[str, Any]) -> bool:
        """Check if we have valid previous day high/low levels for trading."""
        return (current_instrument["prev_day_high"] is not None and 
                current_instrument["prev_day_low"] is not None)

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
        
        # Get current bar date
        import datetime
        current_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).date()
        
        # Check if new day started
        if current_instrument["last_bar_date"] != current_date:
            # SMART: Only update prev_day levels if we actually had trading data yesterday
            if current_instrument["daily_highs"] and current_instrument["daily_lows"]:
                # Save the highest high and lowest low from the complete 24h previous day
                current_instrument["prev_day_high"] = current_instrument["daily_highs"][0]  # Highest value from complete day
                current_instrument["prev_day_low"] = current_instrument["daily_lows"][0]    # Lowest value from complete day
                self.log.info(f"New trading day: Updated PDH={float(current_instrument['prev_day_high']):.2f}, PDL={float(current_instrument['prev_day_low']):.2f}")
            else:
                # No trading data yesterday (weekend/holiday) - keep existing prev_day levels
                if current_instrument["prev_day_high"] is not None and current_instrument["prev_day_low"] is not None:
                    self.log.info(f"Weekend/Holiday: Preserving PDH={float(current_instrument['prev_day_high']):.2f}, PDL={float(current_instrument['prev_day_low']):.2f}")
                else:
                    self.log.info("First day of strategy - no previous day levels available")
            
            # NOW reset for new day (after preserving/updating previous day values)
            current_instrument["daily_highs"] = []
            current_instrument["daily_lows"] = []
            current_instrument["last_bar_date"] = current_date
            current_instrument["traded_today"] = False
            current_instrument["pdh_broken"] = False
            current_instrument["pdl_broken"] = False
            current_instrument["opening_validated"] = False
            current_instrument["first_bar_of_day"] = True
        
        # Validate opening is within PDH/PDL range (first bar of the day)
        if (current_instrument["first_bar_of_day"] and 
            self.has_valid_previous_day_levels(current_instrument)):
            
            opening_price = bar.open
            prev_day_high = current_instrument["prev_day_high"]
            prev_day_low = current_instrument["prev_day_low"]
            
            if prev_day_low <= opening_price <= prev_day_high:
                current_instrument["opening_validated"] = True
                self.log.info(f"Opening VALIDATED: {float(opening_price):.2f} within PDL={float(prev_day_low):.2f} - PDH={float(prev_day_high):.2f}")
            else:
                current_instrument["opening_validated"] = False
                self.log.info(f"Opening REJECTED: {float(opening_price):.2f} outside PDL={float(prev_day_low):.2f} - PDH={float(prev_day_high):.2f}")
            
            current_instrument["first_bar_of_day"] = False
        elif current_instrument["first_bar_of_day"] and not self.has_valid_previous_day_levels(current_instrument):
            # First day or no valid levels - reject opening
            current_instrument["opening_validated"] = False
            current_instrument["first_bar_of_day"] = False
            self.log.info("Opening REJECTED: No valid previous day levels available")
        
        # Add current bar's high/low to sorted lists (convert Price objects to float)
        current_instrument["daily_highs"].append(float(bar.high))
        current_instrument["daily_lows"].append(float(bar.low))
        
        # Keep lists sorted: highs descending (highest first), lows ascending (lowest first)
        current_instrument["daily_highs"].sort(reverse=True)
        current_instrument["daily_lows"].sort()
        
        # Update indicators
        current_instrument['vwap_indicator'].update(bar)
        current_instrument["atr"].handle_bar(bar)
        
        if not current_instrument['vwap_indicator'].initialized or not current_instrument["atr"].initialized:
            return
        
        # Check for pending orders
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        
        # Store previous bar close
        prev_close = current_instrument["prev_bar_close"]
        current_instrument["prev_bar_close"] = bar.close
            
        self.entry_logic(bar, current_instrument, prev_close)
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

    # -------------------------------------------------
    # Entry Logic per Instrument
    # -------------------------------------------------
    def entry_logic(self, bar: Bar, current_instrument: Dict[str, Any], prev_close: float = None):
        # Robust break detection using prev_day_high and prev_day_low
        prev_day_high = current_instrument["prev_day_high"]
        prev_day_low = current_instrument["prev_day_low"]
        
        # ROBUST: Require valid previous day levels (handles weekends/holidays properly)
        if prev_close is None or prev_day_high is None or prev_day_low is None:
            # Log why we're not trading if it's during RTH
            if self.is_rth_time(bar, current_instrument):
                if prev_day_high is None or prev_day_low is None:
                    self.log.info("No previous day levels available - skipping trades (possible first day)")
            return
        
        vwap_indicator = current_instrument["vwap_indicator"]
        
        # Step 1: ALWAYS detect breaks (even outside RTH) to maintain proper state
        if prev_close < prev_day_high and bar.close > prev_day_high:
            current_instrument["pdh_broken"] = True
            current_instrument["pdl_broken"] = False  # Reset opposite break
            self.log.info(f"PDH break detected: prev={float(prev_close):.2f} < PDH={prev_day_high:.2f} < current={float(bar.close):.2f}")
                
        elif prev_close > prev_day_low and bar.close < prev_day_low:
            current_instrument["pdl_broken"] = True
            current_instrument["pdh_broken"] = False  # Reset opposite break
            self.log.info(f"PDL break detected: prev={float(prev_close):.2f} > PDL={prev_day_low:.2f} > current={float(bar.close):.2f}")

        # Step 2: ONLY enter trades during RTH
        if not self.is_rth_time(bar, current_instrument):
            return
        
        # Check if opening was within PDH/PDL range (first filter)
        if not current_instrument["opening_validated"]:
            return
            
        # Check if we already have a position (no stacking)
        net_position = self.portfolio.net_position(bar.bar_type.instrument_id)
        if net_position and net_position != 0:
            return
            
        # Check if we already traded today (no re-entries)
        if current_instrument["traded_today"]:
            return

        # Step 3: Entry logic with VWAP extremes validation
        vwap_status = vwap_indicator.get_trend_validation_status()
        
        if (current_instrument["pdh_broken"] and 
            not current_instrument["traded_today"] and
            vwap_status['long_trend_validated']):  # NEW: Use VWAP indicator's validation
            
            # Long entry after PDH break - wait for retrace to entry band
            _, upper_band, lower_band = vwap_indicator.get_bands(1.0)
            if lower_band is not None:
                # Calculate entry level: VWAP - (multiplier * distance_to_lower_band)
                band_distance = vwap_indicator.value - lower_band
                entry_level = vwap_indicator.value - (self.config.entry_band_long * band_distance)
            else:
                entry_level = vwap_indicator.value  # Fallback to VWAP
            
            if entry_level and bar.close <= entry_level:
                self.log.info(f"LONG entry on retrace to band: close={float(bar.close):.2f} <= entry_level={float(entry_level):.2f} (trend validated: {vwap_status['bars_above_long_band']} bars)")
                self._execute_long_entry(bar, current_instrument, vwap_indicator)

        elif (current_instrument["pdl_broken"] and 
              not current_instrument["traded_today"] and
              vwap_status['short_trend_validated']):  # NEW: Use VWAP indicator's validation
              
            # Short entry after PDL break - wait for retrace to entry band  
            _, upper_band, lower_band = vwap_indicator.get_bands(1.0)
            if upper_band is not None:
                # Calculate entry level: VWAP + (multiplier * distance_to_upper_band)
                band_distance = upper_band - vwap_indicator.value
                entry_level = vwap_indicator.value + (self.config.entry_band_short * band_distance)
            else:
                entry_level = vwap_indicator.value  # Fallback to VWAP
            
            if entry_level and bar.close >= entry_level:
                self.log.info(f"SHORT entry on retrace to band: close={float(bar.close):.2f} >= entry_level={float(entry_level):.2f} (trend validated: {vwap_status['bars_below_short_band']} bars)")
                self._execute_short_entry(bar, current_instrument, vwap_indicator)

    def _execute_long_entry(self, bar: Bar, current_instrument: Dict[str, Any], vwap_indicator):
        entry_price = bar.close
        atr_value = current_instrument["atr"].value
        
        if atr_value is None or atr_value <= 0:
            return
            
        # Calculate levels
        sl_distance = atr_value * self.config.sl_atr_multiplier
        tp_distance = atr_value * self.config.tp_atr_multiplier
        sl_price = entry_price - sl_distance
        tp_price = entry_price + tp_distance
        
        # Calculate position size using RiskManager
        invest_percent = Decimal(str(self.config.risk_percent * 10))
        position_size, valid_position = self.risk_manager.calculate_investment_size(
            invest_percent, Decimal(str(entry_price)), bar.bar_type.instrument_id
        )
        
        if valid_position and position_size > 0:
            self.order_types.submit_long_bracket_order(
                bar.bar_type.instrument_id, position_size, 
                Decimal(str(entry_price)), Decimal(str(sl_price)), Decimal(str(tp_price))
            )
            current_instrument["traded_today"] = True
            self.log.info(f"LONG entry: {entry_price}, SL: {sl_price}, TP: {tp_price}, Size: {position_size}")

    def _execute_short_entry(self, bar: Bar, current_instrument: Dict[str, Any], vwap_indicator):
        """Execute short entry after PDL break"""
        entry_price = bar.close
        atr_value = current_instrument["atr"].value
        
        if atr_value is None or atr_value <= 0:
            return
            
        # Calculate levels
        sl_distance = atr_value * self.config.sl_atr_multiplier
        tp_distance = atr_value * self.config.tp_atr_multiplier
        sl_price = entry_price + sl_distance
        tp_price = entry_price - tp_distance
        
        # Calculate position size using RiskManager
        invest_percent = Decimal(str(self.config.risk_percent * 10))
        position_size, valid_position = self.risk_manager.calculate_investment_size(
            invest_percent, Decimal(str(entry_price)), bar.bar_type.instrument_id
        )
        
        if valid_position and position_size > 0:
            self.order_types.submit_short_bracket_order(
                bar.bar_type.instrument_id, position_size,
                Decimal(str(entry_price)), Decimal(str(sl_price)), Decimal(str(tp_price))
            )
            current_instrument["traded_today"] = True
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
            
            # 1-sigma bands
            _, upper_1, lower_1 = vwap_indicator.get_bands(1.0)
            if upper_1 is not None:
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_upper_band", value=float(upper_1))
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_lower_band", value=float(lower_1))
            
            # 2-sigma bands
            _, upper_2, lower_2 = vwap_indicator.get_bands(2.0)
            if upper_2 is not None:
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_upper_band_2", value=float(upper_2))
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_lower_band_2", value=float(lower_2))
            
            # 3-sigma bands
            _, upper_3, lower_3 = vwap_indicator.get_bands(3.0)
            if upper_3 is not None:
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_upper_band_3", value=float(upper_3))
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_lower_band_3", value=float(lower_3))
        
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