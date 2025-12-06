from decimal import Decimal
from typing import Any, Dict, Optional, List
from collections import deque
import datetime

from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.events import PositionEvent
from nautilus_trader.common.enums import LogColor

from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from tools.help_funcs.base_strategy import BaseStrategy
from tools.indicators.kalman_filter_2D_own_ZScore import KalmanFilterRegressionWithZScore
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTFAnchored
from tools.structure.elastic_reversion_zscore_entry import ElasticReversionZScoreEntry
from tools.help_funcs.adaptive_parameter_manager_new import AdaptiveParameterManager


class Mean5mregimesStrategyConfig(StrategyConfig):
    instruments: List[dict]
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    base_parameters: dict
    adaptive_factors: dict
    run_id: str
    
    zscore_calculation: dict = None
    gap_threshold_pct: float = 0.1
    vix_fear_threshold: float = 25.0
    close_positions_on_stop: bool = True
    invest_percent: float = 0.10
    only_trade_rth: bool = True
    initialization_window: int = 150

class Mean5mregimesStrategy(BaseStrategy, Strategy):
    def __init__(self, config:Mean5mregimesStrategyConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config)
        self.close_positions_on_stop = config.close_positions_on_stop
        self.risk_manager = None
        self.order_types = None
        
        self.close_positions_on_stop = config.close_positions_on_stop
        self.risk_manager = None
        self.order_types = None
        
        # Global State Variables (werden teilweise pro Instrument verwaltet)
        self.stopped = False
        self.realized_pnl = 0
        self.bar_counter = 0
        
        # Dashboard indicators (global für alle Instrumente)
        self.current_ltf_kalman_mean = None
        self.current_htf_kalman_mean = None
        self.entry_atr_factor = None
        self.current_slope_factor = None
        self.current_atr_factor = None
        self.current_asymmetric_offset = None
        self.current_long_risk_factor = None
        self.current_short_risk_factor = None
        self.current_long_exit = None
        self.current_short_exit = None

        # Hard stop tracking
        self.position_entry_prices = {}
        self.position_stop_levels = {}

        # Track VWAP reset state
        self.last_vwap_segment_start_bar = -1
        self.vwap_just_reset = False
        self.bars_since_vwap_reset = 0

        # General initialization window
        self.initialization_window = getattr(config, 'initialization_window', 150)
        self._init_slope_buffer = []
        self._init_window_complete = False
        
        self.adaptive_manager = AdaptiveParameterManager(
            base_params=config.base_parameters,
            adaptive_factors=config.adaptive_factors
        )
        
        # Initialize global indicators (werden später pro Instrument dupliziert)
        self.add_instrument_context()

    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            # Collector wird bereits von BaseStrategy initialisiert - nicht nochmal machen!
            
            # Adaptive Parameter Setup
            adaptive_params, _, _ = self.adaptive_manager.get_adaptive_parameters()
            vwap_params = adaptive_params.get('vwap', {})
            
            # Get anchor method from base_parameters.vwap.anchor_method, with fallback
            anchor_method = vwap_params.get('anchor_method', 'kalman_cross')
            current_instrument["vwap_anchor_method"] = anchor_method
            
            # VWAP ZScore Indicator
            current_instrument["vwap_zscore"] = VWAPZScoreHTFAnchored(
                anchor_method=anchor_method,
                zscore_calculation=getattr(self.config, 'zscore_calculation', {"simple": {"enabled": True}}),
                gap_threshold_pct=self.config.gap_threshold_pct,
                min_bars_for_zscore=vwap_params.get('vwap_min_bars_for_zscore', 20),
                reset_grace_period=vwap_params.get('vwap_reset_grace_period', 40),
                require_trade_for_reset=vwap_params.get('vwap_require_trade_for_reset', True),
                rolling_window_bars=vwap_params.get('rolling_window_bars', 288),
                log_callback=self.log.info
            )
            
            # Kalman Filters pro Instrument
            current_instrument["ltf_kalman"] = KalmanFilterRegressionWithZScore(
                process_var=adaptive_params['ltf_kalman_process_var'],
                measurement_var=adaptive_params['ltf_kalman_measurement_var'],
                window=10,
                zscore_window=adaptive_params['ltf_kalman_zscore_window']
            )
            
            current_instrument["htf_kalman"] = KalmanFilterRegressionWithZScore(
                process_var=adaptive_params['htf_kalman_process_var'],
                measurement_var=adaptive_params['htf_kalman_measurement_var'],
                window=10,
                zscore_window=adaptive_params['htf_kalman_zscore_window']
            )
            
            # Elastic Entry System pro Instrument
            adaptive_elastic_params = adaptive_params['elastic_entry']
            current_instrument["elastic_entry"] = ElasticReversionZScoreEntry(
                vwap_zscore_indicator=current_instrument["vwap_zscore"],
                z_min_threshold=adaptive_elastic_params['zscore_long_threshold'],
                z_max_threshold=adaptive_elastic_params['zscore_short_threshold'],
                recovery_delta=adaptive_elastic_params['recovery_delta'],
                reset_neutral_zone_long=1.0,
                reset_neutral_zone_short=-1.0,
                allow_multiple_recoveries=adaptive_elastic_params['allow_multiple_recoveries'],
                recovery_cooldown_bars=adaptive_elastic_params['recovery_cooldown_bars']
            )
            
            # Stacking Configuration pro Instrument
            current_instrument["allow_stacking"] = adaptive_elastic_params.get('allow_stacking', False)
            current_instrument["max_long_stacked_positions"] = adaptive_elastic_params.get('max_long_stacked_positions', 3)
            current_instrument["max_short_stacked_positions"] = adaptive_elastic_params.get('max_short_stacked_positions', 3)
            current_instrument["additional_zscore_min_gain"] = adaptive_elastic_params.get('additional_zscore_min_gain', 0.5)
            current_instrument["recovery_delta_reentry"] = adaptive_elastic_params.get('recovery_delta_reentry', 0.3)
            current_instrument["stacking_bar_cooldown"] = adaptive_elastic_params.get('stacking_bar_cooldown', 10)
            
            # Daily stacking reset configuration pro Instrument
            current_instrument["allow_daily_stacking_reset"] = adaptive_elastic_params.get('allow_daily_stacking_reset', False)
            current_instrument["current_trading_day"] = None
            current_instrument["daily_long_stacking_reset"] = False
            current_instrument["daily_short_stacking_reset"] = False
            
            # Position tracking pro Instrument
            current_instrument["long_positions_since_cross"] = 0
            current_instrument["short_positions_since_cross"] = 0
            current_instrument["last_kalman_cross_direction"] = None
            current_instrument["long_entry_zscores"] = deque(maxlen=200)
            current_instrument["short_entry_zscores"] = deque(maxlen=200)
            current_instrument["bars_since_last_long_entry"] = 0
            current_instrument["bars_since_last_short_entry"] = 0
            
            # VIX - bleibt global, wird aber pro Instrument referenziert
            current_instrument["vix_fear"] = self.config.vix_fear_threshold
            # Note: VIX braucht start/end dates - das wird später über Framework gelöst
            current_instrument["vix"] = None  # Wird in on_start initialisiert
            
            # RTH configuration - kann pro Instrument unterschiedlich sein
            current_instrument["only_trade_rth"] = self.config.only_trade_rth
            current_instrument["rth_start_hour"] = 15
            current_instrument["rth_start_minute"] = 40
            current_instrument["rth_end_hour"] = 21
            current_instrument["rth_end_minute"] = 50
            
            # Tracking variables pro Instrument
            current_instrument["prev_close"] = None
            current_instrument["current_zscore"] = None
            current_instrument["last_vwap_segment_start_bar"] = -1
            current_instrument["vwap_just_reset"] = False
            current_instrument["bars_since_vwap_reset"] = 0
            
            # Initialize logging indicators pro Instrument
            current_instrument["collector"].initialise_logging_indicator("ltf_kalman_mean", 0)
            current_instrument["collector"].initialise_logging_indicator("htf_kalman_mean", 0)
            current_instrument["collector"].initialise_logging_indicator("vwap", 0)
            current_instrument["collector"].initialise_logging_indicator("atr_factor", 1)
            current_instrument["collector"].initialise_logging_indicator("vwap_zscore", 2)
            current_instrument["collector"].initialise_logging_indicator("slope_factor", 3)
            current_instrument["collector"].initialise_logging_indicator("zscore_offset", 4)
            current_instrument["collector"].initialise_logging_indicator("kalman_zscore", 5)
            current_instrument["collector"].initialise_logging_indicator("long_risk", 6)
            current_instrument["collector"].initialise_logging_indicator("short_risk", 7)
            current_instrument["collector"].initialise_logging_indicator("long_exit", 8)
            current_instrument["collector"].initialise_logging_indicator("short_exit", 9)
            current_instrument["collector"].initialise_logging_indicator("vix", 10)


    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                self.subscribe_bars(bar_type)
                self.log.info(f"Subscribed to {bar_type} for {inst_id}", color=LogColor.GREEN)
        
        self.log.info(f"Strategy started. Instruments: {', '.join(str(i) for i in self.instrument_ids())}")

        self._init_slope_buffer = []
        self._init_window_complete = False

        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)

    def _notify_vwap_exit_if_needed(self, current_instrument: Dict[str, Any]):
        adaptive_params = self.adaptive_manager.get_adaptive_parameters(slope=self.current_htf_kalman_slope)[0]
        anchor_method = adaptive_params.get('vwap', {}).get('anchor_method', 'kalman_cross')
        if anchor_method == 'kalman_cross':
            current_instrument["vwap_zscore"].notify_exit_trade_occurred()

    def is_rth_time(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument["only_trade_rth"]:
            return True
            
        bar_time = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(current_instrument["rth_start_hour"], current_instrument["rth_start_minute"])
        rth_end = datetime.time(current_instrument["rth_end_hour"], current_instrument["rth_end_minute"])
        
        return rth_start <= bar_time <= rth_end

    def on_bar(self, bar: Bar) -> None:
        # Multi-Instrument Routing: Route bar zu entsprechendem Instrument
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return
        
        # Process bar for this specific instrument
        self.process_bar_for_instrument(bar, current_instrument)

    def process_bar_for_instrument(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        instrument_id = bar.bar_type.instrument_id

        # VIX handling - global aber pro Instrument referenziert
        vix_value = None  # TODO: VIX wird später über Framework initialisiert
        current_vix_value = vix_value

        # Kalman Filter Updates pro Instrument
        current_ltf_kalman_mean, current_ltf_kalman_slope, current_ltf_kalman_zscore = current_instrument["ltf_kalman"].update(float(bar.close))
        current_htf_kalman_mean, current_htf_kalman_slope, current_htf_kalman_zscore = current_instrument["htf_kalman"].update(float(bar.close))
        
        # Update global state variables
        self.current_ltf_kalman_mean = current_ltf_kalman_mean
        self.current_htf_kalman_mean = current_htf_kalman_mean  
        self.current_htf_kalman_slope = current_htf_kalman_slope
        self.current_ltf_kalman_zscore = current_ltf_kalman_zscore
        
        current_instrument["vwap_zscore"].set_kalman_exit_mean(current_ltf_kalman_mean)
        
        self.adaptive_manager.update_atr(float(bar.high), float(bar.low), float(current_instrument["prev_close"]) if current_instrument["prev_close"] else None)
        self.adaptive_manager.update_slope(current_ltf_kalman_mean, current_htf_kalman_slope)
        
        # Check initialization window completion
        if not self._init_window_complete:
            self._init_slope_buffer.append(current_htf_kalman_slope)
            if len(self._init_slope_buffer) >= self.initialization_window:
                import numpy as np
                self.initial_slope = float(np.mean(self._init_slope_buffer))
                self._init_window_complete = True
                self.log.info(f"Initialization window complete (window={self.initialization_window}): initial_slope={self.initial_slope}", color=LogColor.YELLOW)
        
        # Calculate factors based on completion status
        if not self._init_window_complete:
            slope_factor = 1.0
            atr_factor = 1.0
            adaptive_params, _, _ = self.adaptive_manager.get_adaptive_parameters()
            if self.bar_counter % 50 == 0:
                self.log.info(f"Using default factors during init: slope={slope_factor}, atr={atr_factor} (bar {len(self._init_slope_buffer)}/{self.initialization_window})", color=LogColor.CYAN)
        else:
            adaptive_params, slope_factor, atr_factor = self.adaptive_manager.get_adaptive_parameters()
        
        self.current_slope_factor = slope_factor
        self.current_atr_factor = atr_factor

        self._check_hard_stops(bar, current_instrument)

        # Calculate and store risk factors and exit thresholds
        if self._init_window_complete:
            self.current_long_risk_factor = adaptive_params.get('long_risk_factor', 1.0)
            self.current_short_risk_factor = adaptive_params.get('short_risk_factor', 1.0)
            long_exit, short_exit = self.adaptive_manager.get_adaptive_exit_thresholds()
            self.current_long_exit = long_exit
            self.current_short_exit = short_exit
        else:
            self.current_long_risk_factor = 1.0
            self.current_short_risk_factor = 1.0
            self.current_long_exit = None
            self.current_short_exit = None

        elastic_base = adaptive_params['elastic_entry']
        
        current_instrument["elastic_entry"].update_parameters(
            z_min_threshold=elastic_base['zscore_long_threshold'],
            z_max_threshold=elastic_base['zscore_short_threshold'],
            recovery_delta=elastic_base['recovery_delta']
        )
        
        current_instrument["additional_zscore_min_gain"] = elastic_base['additional_zscore_min_gain']
        current_instrument["recovery_delta_reentry"] = elastic_base['recovery_delta_reentry']
        
        # Check if VWAP has reset für dieses Instrument
        current_segment_info = current_instrument["vwap_zscore"].get_segment_info()
        if hasattr(current_segment_info, 'get') and 'segment_start_bar' in current_segment_info:
            current_segment_start = current_segment_info['segment_start_bar']
            if current_segment_start != current_instrument["last_vwap_segment_start_bar"]:
                current_instrument["vwap_just_reset"] = True
                current_instrument["last_vwap_segment_start_bar"] = current_segment_start
                current_instrument["bars_since_vwap_reset"] = 0
                if current_segment_info.get('anchor_reason') in ['new_day', 'new_week']:
                    self.log.info(f"{instrument_id}: VWAP Reset Detected: {current_segment_info.get('anchor_reason')} - Asymmetric offset and trend state reset", color=LogColor.YELLOW)
                    self.adaptive_manager.reset_trend_state_for_vwap_anchor()
            else:
                current_instrument["vwap_just_reset"] = False
                current_instrument["bars_since_vwap_reset"] += 1
        else:
            current_instrument["vwap_just_reset"] = False
            current_instrument["bars_since_vwap_reset"] += 1
            
        # Calculate asymmetric offset
        asymmetric_offset = self.adaptive_manager.get_asymmetric_offset(current_ltf_kalman_mean, slope=current_htf_kalman_slope)
        self.current_asymmetric_offset = asymmetric_offset
            
        vwap_value, zscore = current_instrument["vwap_zscore"].update(bar, asymmetric_offset=asymmetric_offset)
        current_instrument["current_zscore"] = zscore

        # Track zscore for distribution analysis
        if zscore is not None:
            self.adaptive_manager.update_zscore(zscore)

        # Use the VWAP Z-Score for entries
        if zscore is not None:
            current_instrument["elastic_entry"].update_state(zscore)

        self._check_daily_stacking_reset(bar, zscore, adaptive_params, current_instrument)
        self._check_kalman_cross_for_stacking(bar, current_instrument)
        self.bar_counter += 1

        # Update entry tracking counters für dieses Instrument
        current_instrument["bars_since_last_long_entry"] += 1
        current_instrument["bars_since_last_short_entry"] += 1

        # Trading logic für dieses Instrument
        if self.is_rth_time(bar, current_instrument):
            if not self._init_window_complete:
                if self.bar_counter % 50 == 0:
                    self.log.info(f"Trading blocked - initialization window: {len(self._init_slope_buffer)}/{self.initialization_window} bars completed", color=LogColor.CYAN)
                return
            
            # Check VIX regime if available
            regime = 1  # Default to normal regime
            if current_vix_value is not None:
                regime = self.get_vix_regime(current_vix_value, current_instrument)
                if regime == 2:
                    self._notify_vwap_exit_if_needed(current_instrument)
                    self.order_types.close_position_by_market_order()
                    return
            
            # Execute trading logic (regardless of VIX availability)
            if current_ltf_kalman_mean is not None and zscore is not None:
                vwap_segment_info = current_instrument["vwap_zscore"].get_segment_info()
                bars_in_current_segment = vwap_segment_info.get('bars_in_segment', 0)
                
                if bars_in_current_segment < 25:
                    if self.bar_counter % 15 == 0:
                        self.log.info(f"{instrument_id}: Trading blocked - ZScore evolution period: {bars_in_current_segment}/25 bars since VWAP reset", color=LogColor.CYAN)
                    return
                
                # We're reaching trading logic! Log this
                if self.bar_counter % 50 == 0:
                    self.log.info(f"{instrument_id}: TRADING LOGIC REACHED - price={float(bar.close):.2f}, kalman_mean={current_ltf_kalman_mean:.2f}, zscore={zscore:.3f}", color=LogColor.MAGENTA)
                
                self.current_long_risk_factor = adaptive_params['long_risk_factor']
                self.current_short_risk_factor = adaptive_params['short_risk_factor']
                
                if bar.close < current_ltf_kalman_mean:
                    self.check_for_long_trades(bar, zscore, adaptive_params, current_instrument)
                elif bar.close > current_ltf_kalman_mean:
                    self.check_for_short_trades(bar, zscore, adaptive_params, current_instrument)

        self.check_for_long_exit(bar, adaptive_params, current_instrument)
        self.check_for_short_exit(bar, adaptive_params, current_instrument)
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)
        current_instrument["prev_close"] = bar.close

    def count_open_position(self, instrument_id: InstrumentId) -> int:
        pos = self.portfolio.net_position(instrument_id)
        return abs(int(pos)) if pos is not None else 0

    def _check_hard_stops(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        
        if not self.position_stop_levels:
            return
        
        current_price = float(bar.close)
        positions_to_close = []
        
        for position_id, stop_info in self.position_stop_levels.items():
            if stop_info['side'] == 'long' and current_price <= stop_info['stop_price']:
                positions_to_close.append(position_id)
                current_instrument["long_positions_since_cross"] = max(0, current_instrument["long_positions_since_cross"] - 1)
                self.log.info(f"{instrument_id}: Long stop loss hit at {current_price:.2f} (stop: {stop_info['stop_price']:.2f}). "
                             f"Positions since cross reset to {current_instrument['long_positions_since_cross']}", color=LogColor.RED)
                
            elif stop_info['side'] == 'short' and current_price >= stop_info['stop_price']:
                positions_to_close.append(position_id)
                current_instrument["short_positions_since_cross"] = max(0, current_instrument["short_positions_since_cross"] - 1)
                self.log.info(f"{instrument_id}: Short stop loss hit at {current_price:.2f} (stop: {stop_info['stop_price']:.2f}). "
                             f"Positions since cross reset to {current_instrument['short_positions_since_cross']}", color=LogColor.RED)
        
        for position_id in positions_to_close:
            self.close_position(instrument_id)
            del self.position_stop_levels[position_id]
            if position_id in self.position_entry_prices:
                del self.position_entry_prices[position_id]

    def _track_position_entry(self, side: str, entry_price: float):
        if not self.adaptive_manager.is_hard_stop_enabled()[f'{side}_enabled']:
            return
        
        position_id = f"{side}_{len(self.position_entry_prices)}"
        self.position_entry_prices[position_id] = entry_price
        
        stop_levels = self.adaptive_manager.get_hard_stop_levels(entry_price)
        if side == 'long' and stop_levels['long_enabled']:
            self.position_stop_levels[position_id] = {
                'side': 'long',
                'stop_price': stop_levels['long_stop_price']
            }
        elif side == 'short' and stop_levels['short_enabled']:
            self.position_stop_levels[position_id] = {
                'side': 'short', 
                'stop_price': stop_levels['short_stop_price']
            }

    def _should_allow_stacking(self, side: str) -> bool:
        adaptive_params, _, _ = self.adaptive_manager.get_adaptive_parameters()
        elastic_params = adaptive_params.get('elastic_entry', {})
        
        if not elastic_params.get('allow_stacking', True):
            return False
            
        hard_stops = self.adaptive_manager.is_hard_stop_enabled()
        if hard_stops[f'{side}_enabled']:
            return False
        
        return True
    
    def _check_kalman_cross_for_stacking(self, bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        
        if self.current_ltf_kalman_mean is None:
            return
            
        current_above = bar.close > self.current_ltf_kalman_mean
        current_direction = "up" if current_above else "down"
        
        # Only trigger cross if we have a previous direction AND it's different
        if (current_instrument["last_kalman_cross_direction"] is not None and 
            current_instrument["last_kalman_cross_direction"] != current_direction):
            
            current_instrument["long_positions_since_cross"] = 0
            current_instrument["short_positions_since_cross"] = 0
            current_instrument["long_entry_zscores"] = []
            current_instrument["short_entry_zscores"] = []
            current_instrument["bars_since_last_long_entry"] = 0
            current_instrument["bars_since_last_short_entry"] = 0
            
            current_instrument["elastic_entry"].reset_on_cross()
            
            anchor_method = current_instrument["vwap_anchor_method"]
            
            self.log.info(f"{instrument_id}: Kalman cross detected: {current_instrument['last_kalman_cross_direction']} -> {current_direction} | Anchor method: {anchor_method}", color=LogColor.CYAN)
            
            # Only reset VWAP on kalman cross if anchor method is 'kalman_cross'
            if anchor_method == 'kalman_cross':
                self._notify_vwap_exit_if_needed(current_instrument)
                self.log.info(f"{instrument_id}: Kalman cross detected: {current_instrument['last_kalman_cross_direction']} -> {current_direction} | VWAP reset", color=LogColor.BLUE)
        
        current_instrument["last_kalman_cross_direction"] = current_direction
    
    def _check_daily_stacking_reset(self, bar, zscore, adaptive_params, current_instrument: Dict[str, Any]):
        if not current_instrument["allow_daily_stacking_reset"]:
            return
            
        current_day = bar.ts_event.date()
        
        if current_instrument["current_trading_day"] != current_day:
            current_instrument["current_trading_day"] = current_day
            current_instrument["daily_long_stacking_reset"] = False
            current_instrument["daily_short_stacking_reset"] = False
            return
        
        if zscore is None:
            return
            
        if (zscore <= -2.5 and 
            not current_instrument["daily_long_stacking_reset"] and 
            current_instrument["long_positions_since_cross"] > 0):
            current_instrument["daily_long_stacking_reset"] = True
            self.log.info(f"Daily stacking reset triggered for LONG positions at zscore {zscore:.3f}", color=LogColor.GREEN)
            
        if (zscore >= 2.5 and 
            not current_instrument["daily_short_stacking_reset"] and 
            current_instrument["short_positions_since_cross"] > 0):
            current_instrument["daily_short_stacking_reset"] = True
            self.log.info(f"Daily stacking reset triggered for SHORT positions at zscore {zscore:.3f}", color=LogColor.RED)
    
    def can_stack_long(self, current_zscore: float, current_instrument: Dict[str, Any]) -> bool:
        if current_instrument["long_positions_since_cross"] == 0:
            return True
            
        if not self._should_allow_stacking('long'):
            return False
            
        if not current_instrument["allow_stacking"]:
            return False

        if current_instrument["daily_long_stacking_reset"]:
            return True
        
        if current_instrument["long_positions_since_cross"] >= current_instrument["max_long_stacked_positions"]:
            return False
                    
        if current_instrument["bars_since_last_long_entry"] < current_instrument["stacking_bar_cooldown"]:
            return False
            
        if current_instrument["long_entry_zscores"] and current_zscore is not None:
            last_entry_zscore = current_instrument["long_entry_zscores"][-1]
            zscore_deterioration = last_entry_zscore - current_zscore
            
            if zscore_deterioration < current_instrument["additional_zscore_min_gain"]:
                return False
        
        return True  
    
    def can_stack_short(self, current_zscore: float, current_instrument: Dict[str, Any]) -> bool:
        if current_instrument["short_positions_since_cross"] == 0:
            return True
            
        if not self._should_allow_stacking('short'):
            return False
            
        if not current_instrument["allow_stacking"]:
            return False

        if current_instrument["daily_short_stacking_reset"]:
            return True
        
        if current_instrument["short_positions_since_cross"] >= current_instrument["max_short_stacked_positions"]:
            return False
            
        if current_instrument["bars_since_last_short_entry"] < current_instrument["stacking_bar_cooldown"]:
            return False
            
        if current_instrument["short_entry_zscores"] and current_zscore is not None:
            last_entry_zscore = current_instrument["short_entry_zscores"][-1]
            zscore_deterioration = current_zscore - last_entry_zscore
            
            if zscore_deterioration < current_instrument["additional_zscore_min_gain"]:
                return False
        
        return True

    def get_vix_regime(self, vix_value: float, current_instrument: Dict[str, Any]) -> int:
        if vix_value is None:
            return 1  # Default to normal regime
        
        vix_val = float(vix_value) if not isinstance(vix_value, (int, float)) else vix_value
        
        if vix_val >= current_instrument["vix_fear"]:
            return 2  # Fear regime
        else:
            return 1  # Normal regime
    
    def check_for_long_trades(self, bar: Bar, zscore: float, adaptive_params: dict, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        
        if self.current_ltf_kalman_mean is not None and bar.close >= self.current_ltf_kalman_mean:
            return

        long_min_distance = adaptive_params['elastic_entry']['long_min_distance_from_kalman']
        if self.current_ltf_kalman_zscore is not None and self.current_ltf_kalman_zscore > long_min_distance:
            return

        regime = self.get_vix_regime(None, current_instrument)  # VIX handling wird später implementiert
        if regime == 2:
            return
        
        can_enter = self.can_stack_long(zscore, current_instrument)
        if not can_enter:
            return

        long_risk_factor = adaptive_params['long_risk_factor']
        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(long_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price, instrument_id)
        if not valid_position or qty <= 0:
            if self.bar_counter % 100 == 0:  # Debug log less frequently
                self.log.info(f"{instrument_id}: Long blocked - invalid position size: qty={qty}, valid={valid_position}, invest_percent={invest_percent}", color=LogColor.YELLOW)
            return

        long_signal, _, debug_info = current_instrument["elastic_entry"].check_entry_signals(zscore)
        
        if long_signal:
            entry_reason = debug_info.get('long_entry_reason', 'Recovery signal')
            stack_info = f"Stack {current_instrument['long_positions_since_cross'] + 1}/{current_instrument['max_long_stacked_positions']}" if current_instrument["long_positions_since_cross"] > 0 else "Initial"
            
            hard_stops_enabled = self.adaptive_manager.is_hard_stop_enabled()['long_enabled']
            re_entry_note = " (RE-ENTRY after SL)" if hard_stops_enabled and current_instrument["long_positions_since_cross"] == 0 else ""
            
            trade_message = self.adaptive_manager.log_trade_state(
                "LONG", float(bar.close), zscore, entry_reason, stack_info, regime, 
                adaptive_params, current_instrument["long_positions_since_cross"], current_instrument["short_positions_since_cross"], 
                current_instrument["allow_stacking"]
            )
            self.log.info(f"{instrument_id}: {trade_message}{re_entry_note}", color=LogColor.MAGENTA)
            
            self.submit_long_market_order(instrument_id, qty)
            current_instrument["long_positions_since_cross"] += 1
            self.entry_atr_factor = self.current_atr_factor
            
            self._track_position_entry('long', float(bar.close))
            
            if current_instrument["daily_long_stacking_reset"]:
                current_instrument["daily_long_stacking_reset"] = False
                self.log.info(f"{instrument_id}: Daily long stacking reset flag cleared after position entry", color=LogColor.GREEN)
            
            current_instrument["long_entry_zscores"].append(zscore)
            current_instrument["bars_since_last_long_entry"] = 0
        else:
            if self.bar_counter % 100 == 0 and zscore is not None:  # Debug log for no signal, less frequent
                self.log.info(f"{instrument_id}: Long blocked - no elastic entry signal: zscore={zscore:.3f}", color=LogColor.YELLOW)

    def check_for_short_trades(self, bar: Bar, zscore: float, adaptive_params: dict, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        
        if self.current_ltf_kalman_mean is not None and bar.close <= self.current_ltf_kalman_mean:
            return
    
        short_min_distance = adaptive_params['elastic_entry']['short_min_distance_from_kalman']
        if self.current_ltf_kalman_zscore is not None and self.current_ltf_kalman_zscore < short_min_distance:
            return

        regime = self.get_vix_regime(None, current_instrument)  # VIX handling wird später implementiert
        if regime == 2:
            return
        
        can_enter = self.can_stack_short(zscore, current_instrument)
        if not can_enter:
            return

        short_risk_factor = adaptive_params['short_risk_factor']
        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(short_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price, instrument_id)
        if not valid_position or qty <= 0:
            if self.bar_counter % 100 == 0:  # Debug log less frequently
                self.log.info(f"{instrument_id}: Short blocked - invalid position size: qty={qty}, valid={valid_position}, invest_percent={invest_percent}", color=LogColor.YELLOW)
            return

        _, short_signal, debug_info = current_instrument["elastic_entry"].check_entry_signals(zscore)
        
        if short_signal:
            entry_reason = debug_info.get('short_entry_reason', 'Recovery signal')
            stack_info = f"Stack {current_instrument['short_positions_since_cross'] + 1}/{current_instrument['max_short_stacked_positions']}" if current_instrument["short_positions_since_cross"] > 0 else "Initial"
            
            hard_stops_enabled = self.adaptive_manager.is_hard_stop_enabled()['short_enabled']
            re_entry_note = " (RE-ENTRY after SL)" if hard_stops_enabled and current_instrument["short_positions_since_cross"] == 0 else ""
            
            trade_message = self.adaptive_manager.log_trade_state(
                "SHORT", float(bar.close), zscore, entry_reason, stack_info, regime, 
                adaptive_params, current_instrument["long_positions_since_cross"], current_instrument["short_positions_since_cross"], 
                current_instrument["allow_stacking"]
            )
            self.log.info(f"{instrument_id}: {trade_message}{re_entry_note}", color=LogColor.MAGENTA)
            
            self.submit_short_market_order(instrument_id, qty)
            current_instrument["short_positions_since_cross"] += 1
            self.entry_atr_factor = self.current_atr_factor
            
            self._track_position_entry('short', float(bar.close))
            
            if current_instrument["daily_short_stacking_reset"]:
                current_instrument["daily_short_stacking_reset"] = False
                self.log.info(f"{instrument_id}: Daily short stacking reset flag cleared after position entry", color=LogColor.RED)
            
            current_instrument["short_entry_zscores"].append(zscore)
            current_instrument["bars_since_last_short_entry"] = 0
        else:
            if self.bar_counter % 100 == 0 and zscore is not None:  # Debug log for no signal, less frequent
                self.log.info(f"{instrument_id}: Short blocked - no elastic entry signal: zscore={zscore:.3f}", color=LogColor.YELLOW)

    def check_for_long_exit(self, bar, adaptive_params: dict, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        
        current_vix_value = None  # VIX handling wird später implementiert
        if current_vix_value is not None:
            regime = self.get_vix_regime(current_vix_value, current_instrument)
            if regime == 2:
                self._notify_vwap_exit_if_needed(current_instrument)
                self.close_position(instrument_id)
                return

        net_pos = self.portfolio.net_position(instrument_id)
        
        if net_pos is not None and net_pos > 0 and self.current_ltf_kalman_zscore is not None:
            long_exit, _ = self.adaptive_manager.get_adaptive_exit_thresholds(slope=self.current_htf_kalman_slope)
            
            if self.current_ltf_kalman_zscore >= long_exit:
                self._notify_vwap_exit_if_needed(current_instrument)
                self.close_position(instrument_id)
            
            if self.current_ltf_kalman_zscore >= long_exit:
                self._notify_vwap_exit_if_needed(current_instrument)
                self.close_position(instrument_id)

    def check_for_short_exit(self, bar, adaptive_params: dict, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        
        current_vix_value = None  # VIX handling wird später implementiert
        if current_vix_value is not None:
            regime = self.get_vix_regime(current_vix_value, current_instrument)
            if regime == 2:
                self._notify_vwap_exit_if_needed(current_instrument)
                self.close_position(instrument_id)
                return
        
        net_pos = self.portfolio.net_position(instrument_id)
        
        if net_pos is not None and net_pos < 0 and self.current_ltf_kalman_zscore is not None:
            _, short_exit = self.adaptive_manager.get_adaptive_exit_thresholds(slope=self.current_htf_kalman_slope)
            
            if self.current_ltf_kalman_zscore <= short_exit:
                self._notify_vwap_exit_if_needed(current_instrument)
                self.close_position(instrument_id)

    def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_long_market_order(instrument_id, qty)

    def submit_short_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self, instrument_id: Optional[InstrumentId] = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument:
            self._notify_vwap_exit_if_needed(current_instrument)
        
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)
    
    def on_stop(self) -> None:
        BaseStrategy.on_stop(self)  # Explicitly call BaseStrategy.on_stop() to avoid MRO issues
        
        # Only add strategy-specific distribution monitoring here
        distribution_config = self.adaptive_manager.adaptive_factors.get('distribution_monitor', {})
        
        if distribution_config.get('slope_distribution', {}).get('enabled', False):
            self.adaptive_manager.print_slope_distribution()
            
        if distribution_config.get('atr_distribution', {}).get('enabled', False):
            if distribution_config.get('slope_distribution', {}).get('enabled', False):
                print("\n")
            self.adaptive_manager.print_atr_distribution()
            
        if distribution_config.get('zscore_distribution', {}).get('enabled', False):
            if (distribution_config.get('slope_distribution', {}).get('enabled', False) or 
                distribution_config.get('atr_distribution', {}).get('enabled', False)):
                print("\n")
            self.adaptive_manager.print_zscore_distribution()
    
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        self.log.info(f"Position closed: {position_closed}")
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)
            
        vwap_value = current_instrument["vwap_zscore"].current_vwap_value

        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="ltf_kalman_mean", value=self.current_ltf_kalman_mean)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="htf_kalman_mean", value=self.current_htf_kalman_mean)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap", value=vwap_value)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="atr_factor", value=self.current_atr_factor)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vwap_zscore", value=current_instrument["current_zscore"])
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="slope_factor", value=self.current_slope_factor)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="zscore_offset", value=self.current_asymmetric_offset)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="kalman_zscore", value=self.current_ltf_kalman_zscore)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="vix", value=None)  # VIX wird später implementiert
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="long_risk", value=self.current_long_risk_factor)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="short_risk", value=self.current_short_risk_factor)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="long_exit", value=self.current_long_exit)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="short_exit", value=self.current_short_exit)
        current_instrument["collector"].add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close, bar_type=bar.bar_type)