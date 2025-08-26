# Standard Library Importe
from decimal import Decimal
from typing import Any
from collections import deque
import datetime
# Nautilus Kern offizielle Importe
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.events import PositionEvent
from nautilus_trader.common.enums import LogColor

from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.base_strategy import BaseStrategy
from tools.indicators.kalman_filter_2D_own_ZScore import KalmanFilterRegressionWithZScore
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTFAnchored
from tools.structure.elastic_reversion_zscore_entry import ElasticReversionZScoreEntry
from tools.indicators.VIX import VIX
from tools.help_funcs.adaptive_parameter_manager_new import AdaptiveParameterManager

class Mean5mregimesStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type_5m: str
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    start_date: str
    end_date: str
    base_parameters: dict
    adaptive_factors: dict
    vwap_anchor_on_kalman_cross: bool = True
    zscore_calculation: dict = None
    gap_threshold_pct: float = 0.1
    vix_fear_threshold: float = 25.0
    close_positions_on_stop: bool = True
    invest_percent: float = 0.10
    only_trade_rth: bool = True

class Mean5mregimesStrategy(BaseStrategy, Strategy):
    def __init__(self, config:Mean5mregimesStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.bar_type_5m = BarType.from_str(config.bar_type_5m)
        self.prev_zscore = None
        self.current_ltf_kalman_mean = None
        self.stopped = False
        self.realized_pnl = 0
        self.bar_counter = 0
        self.prev_close = None
        self.current_zscore = None
        self.collector = BacktestDataCollector()
        
        # Dashboard indicators
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
        self.initialization_window = getattr(config, 'initialization_window', 30)
        self._init_slope_buffer = []
        self._init_window_complete = False
        
        self.adaptive_manager = AdaptiveParameterManager(
            base_params=config.base_parameters,
            adaptive_factors=config.adaptive_factors
        )
        
        adaptive_params, _, _ = self.adaptive_manager.get_adaptive_parameters()
        vwap_params = adaptive_params.get('vwap', {})
        
        anchor_method = vwap_params.get('anchor_method', 'kalman_cross')
        self.vwap_anchor_method = anchor_method
        
        self.vwap_zscore = VWAPZScoreHTFAnchored(
            anchor_method=anchor_method,
            zscore_calculation=getattr(config, 'zscore_calculation', {"simple": {"enabled": True}}),
            gap_threshold_pct=config.gap_threshold_pct,
            min_bars_for_zscore=vwap_params.get('vwap_min_bars_for_zscore', 20),
            reset_grace_period=vwap_params.get('vwap_reset_grace_period', 40),
            require_trade_for_reset=vwap_params.get('vwap_require_trade_for_reset', True),
            rolling_window_bars=vwap_params.get('rolling_window_bars', 288),
            log_callback=self.log.info
        )
        
        self.current_vix_value = None
        
        # LTF Kalman Filter
        self.ltf_kalman = KalmanFilterRegressionWithZScore(
            process_var=adaptive_params['ltf_kalman_process_var'],
            measurement_var=adaptive_params['ltf_kalman_measurement_var'],
            window=10,
            zscore_window=adaptive_params['ltf_kalman_zscore_window']
        )
        self.current_ltf_kalman_mean = None
        self.current_ltf_kalman_slope = None
        self.current_ltf_kalman_zscore = None

        # HTF Kalman Filter
        self.htf_kalman = KalmanFilterRegressionWithZScore(
            process_var=adaptive_params['htf_kalman_process_var'],
            measurement_var=adaptive_params['htf_kalman_measurement_var'],
            window=10,
            zscore_window=adaptive_params['htf_kalman_zscore_window']
        )
        self.current_htf_kalman_mean = None
        self.current_htf_kalman_slope = None
        self.current_htf_kalman_zscore = None

        # Initialize with adaptive parameters
        adaptive_elastic_params = adaptive_params['elastic_entry']
        self.elastic_entry = ElasticReversionZScoreEntry(
            vwap_zscore_indicator=self.vwap_zscore,
            z_min_threshold=adaptive_elastic_params['zscore_long_threshold'],
            z_max_threshold=adaptive_elastic_params['zscore_short_threshold'],
            recovery_delta=adaptive_elastic_params['recovery_delta'],
            reset_neutral_zone_long=1.0,
            reset_neutral_zone_short=-1.0,
            allow_multiple_recoveries=adaptive_elastic_params['allow_multiple_recoveries'],
            recovery_cooldown_bars=adaptive_elastic_params['recovery_cooldown_bars']
        )

        self.allow_stacking = adaptive_elastic_params.get('allow_stacking', False)
        self.max_long_stacked_positions = adaptive_elastic_params.get('max_long_stacked_positions', 3)
        self.max_short_stacked_positions = adaptive_elastic_params.get('max_short_stacked_positions', 3)
        self.additional_zscore_min_gain = adaptive_elastic_params.get('additional_zscore_min_gain', 0.5)
        self.recovery_delta_reentry = adaptive_elastic_params.get('recovery_delta_reentry', 0.3)
        self.stacking_bar_cooldown = adaptive_elastic_params.get('stacking_bar_cooldown', 10)
        
        # Daily stacking reset configuration
        self.allow_daily_stacking_reset = adaptive_elastic_params.get('allow_daily_stacking_reset', False)
        self.current_trading_day = None
        self.daily_long_stacking_reset = False
        self.daily_short_stacking_reset = False
        
        self.long_positions_since_cross = 0
        self.short_positions_since_cross = 0
        self.last_kalman_cross_direction = None
        self.long_entry_zscores = deque(maxlen=200)
        self.short_entry_zscores = deque(maxlen=200)
        self.bars_since_last_long_entry = 0
        self.bars_since_last_short_entry = 0

        # VIX initialization
        self.vix_fear = config.vix_fear_threshold
        self.vix = VIX(start=config.start_date, end=config.end_date, fear_threshold=config.vix_fear_threshold)
        
        # RTH configuration
        self.only_trade_rth = config.only_trade_rth
        self.rth_start_hour = 15
        self.rth_start_minute = 40
        self.rth_end_hour = 21
        self.rth_end_minute = 50

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type_5m)
        self.log.info("Strategy started!")

        self._init_slope_buffer = []
        self._init_window_complete = False

        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)

        self.collector.initialise_logging_indicator("ltf_kalman_mean", 0)
        self.collector.initialise_logging_indicator("htf_kalman_mean", 0)
        self.collector.initialise_logging_indicator("vwap", 0)
        self.collector.initialise_logging_indicator("atr_factor", 1)
        self.collector.initialise_logging_indicator("vwap_zscore", 2)
        self.collector.initialise_logging_indicator("slope_factor", 3)
        self.collector.initialise_logging_indicator("zscore_offset", 4)
        self.collector.initialise_logging_indicator("kalman_zscore", 5)
        self.collector.initialise_logging_indicator("long_risk", 6)
        self.collector.initialise_logging_indicator("short_risk", 7)
        self.collector.initialise_logging_indicator("long_exit", 8)
        self.collector.initialise_logging_indicator("short_exit", 9)
        self.collector.initialise_logging_indicator("vix", 10)
        self.collector.initialise_logging_indicator("position", 11)
        self.collector.initialise_logging_indicator("realized_pnl", 12)
        self.collector.initialise_logging_indicator("unrealized_pnl", 13)
        self.collector.initialise_logging_indicator("equity", 14)


    def get_position(self):
        return self.base_get_position()

    def _notify_vwap_exit_if_needed(self):
        adaptive_params = self.adaptive_manager.get_adaptive_parameters(slope=self.current_htf_kalman_slope)[0]
        anchor_method = adaptive_params.get('vwap', {}).get('anchor_method', 'kalman_cross')
        if anchor_method == 'kalman_cross':
            self.vwap_zscore.notify_exit_trade_occurred()

    def is_rth_time(self, bar: Bar) -> bool:
        if not self.only_trade_rth:
            return True
            
        bar_time = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(self.rth_start_hour, self.rth_start_minute)
        rth_end = datetime.time(self.rth_end_hour, self.rth_end_minute)
        
        return rth_start <= bar_time <= rth_end

    def on_bar(self, bar: Bar) -> None:
        bar_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")

        vix_value = self.vix.get_value_on_date(bar_date)
        if vix_value is not None:
            self.current_vix_value = float(vix_value)
        else:
            self.current_vix_value = None

        self.current_ltf_kalman_mean, self.current_ltf_kalman_slope, self.current_ltf_kalman_zscore = self.ltf_kalman.update(float(bar.close))
        self.current_htf_kalman_mean, self.current_htf_kalman_slope, self.current_htf_kalman_zscore = self.htf_kalman.update(float(bar.close))
        
        self.vwap_zscore.set_kalman_exit_mean(self.current_ltf_kalman_mean)
        
        self.adaptive_manager.update_atr(float(bar.high), float(bar.low), float(self.prev_close) if self.prev_close else None)
        self.adaptive_manager.update_slope(self.current_ltf_kalman_mean, self.current_htf_kalman_slope)
        
        # Check initialization window completion
        if not self._init_window_complete:
            self._init_slope_buffer.append(self.current_htf_kalman_slope)
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

        self._check_hard_stops(bar)

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
        
        self.elastic_entry.update_parameters(
            z_min_threshold=elastic_base['zscore_long_threshold'],
            z_max_threshold=elastic_base['zscore_short_threshold'],
            recovery_delta=elastic_base['recovery_delta']
        )
        
        self.additional_zscore_min_gain = elastic_base['additional_zscore_min_gain']
        self.recovery_delta_reentry = elastic_base['recovery_delta_reentry']
        
        # Check if VWAP has reset
        current_segment_info = self.vwap_zscore.get_segment_info()
        if hasattr(current_segment_info, 'get') and 'segment_start_bar' in current_segment_info:
            current_segment_start = current_segment_info['segment_start_bar']
            if current_segment_start != self.last_vwap_segment_start_bar:
                self.vwap_just_reset = True
                self.last_vwap_segment_start_bar = current_segment_start
                self.bars_since_vwap_reset = 0
                if current_segment_info.get('anchor_reason') in ['new_day', 'new_week']:
                    self.log.info(f"VWAP Reset Detected: {current_segment_info.get('anchor_reason')} - Asymmetric offset and trend state reset", color=LogColor.YELLOW)
                    self.adaptive_manager.reset_trend_state_for_vwap_anchor()
            else:
                self.vwap_just_reset = False
                self.bars_since_vwap_reset += 1
        else:
            self.vwap_just_reset = False
            self.bars_since_vwap_reset += 1
            
        # Calculate asymmetric offset
        asymmetric_offset = self.adaptive_manager.get_asymmetric_offset(self.current_ltf_kalman_mean, slope=self.current_htf_kalman_slope)
        self.current_asymmetric_offset = asymmetric_offset
            
        vwap_value, zscore = self.vwap_zscore.update(bar, asymmetric_offset=asymmetric_offset)
        self.current_zscore = zscore

        # Track zscore for distribution analysis
        if zscore is not None:
            self.adaptive_manager.update_zscore(zscore)

        # Use the VWAP Z-Score for entries
        if zscore is not None:
            self.elastic_entry.update_state(zscore)

        self._check_daily_stacking_reset(bar, zscore, adaptive_params)
        self._check_kalman_cross_for_stacking(bar)
        self.bar_counter += 1

        # Update entry tracking counters
        self.bars_since_last_long_entry += 1
        self.bars_since_last_short_entry += 1

        # Trading logic
        if self.is_rth_time(bar):
            if not self._init_window_complete:
                if self.bar_counter % 50 == 0:
                    self.log.info(f"Trading blocked - initialization window: {len(self._init_slope_buffer)}/{self.initialization_window} bars completed", color=LogColor.CYAN)
                return
                
            if self.current_vix_value is not None:
                regime = self.get_vix_regime(self.current_vix_value)

                if regime == 2:
                    self._notify_vwap_exit_if_needed()
                    self.order_types.close_position_by_market_order()
                else:
                    if self.current_ltf_kalman_mean is not None and zscore is not None:
                        vwap_segment_info = self.vwap_zscore.get_segment_info()
                        bars_in_current_segment = vwap_segment_info.get('bars_in_segment', 0)
                        
                        if bars_in_current_segment < 25:
                            if self.bar_counter % 15 == 0:
                                self.log.info(f"Trading blocked - ZScore evolution period: {bars_in_current_segment}/25 bars since VWAP reset", color=LogColor.CYAN)
                            return
                        
                        self.current_long_risk_factor = adaptive_params['long_risk_factor']
                        self.current_short_risk_factor = adaptive_params['short_risk_factor']
                        
                        if bar.close < self.current_ltf_kalman_mean:
                            self.check_for_long_trades(bar, zscore, adaptive_params)
                        elif bar.close > self.current_ltf_kalman_mean:
                            self.check_for_short_trades(bar, zscore, adaptive_params)

        self.check_for_long_exit(bar, adaptive_params)
        self.check_for_short_exit(bar, adaptive_params)
        self.update_visualizer_data(bar)
        self.prev_close = bar.close
        self.prev_zscore = zscore

    def count_open_position(self) -> int:
        pos = self.portfolio.net_position(self.instrument_id)
        return abs(int(pos)) if pos is not None else 0

    def _check_hard_stops(self, bar: Bar):
        if not self.position_stop_levels:
            return
        
        current_price = float(bar.close)
        positions_to_close = []
        
        for position_id, stop_info in self.position_stop_levels.items():
            if stop_info['side'] == 'long' and current_price <= stop_info['stop_price']:
                positions_to_close.append(position_id)
                self.long_positions_since_cross = max(0, self.long_positions_since_cross - 1)
                self.log.info(f"Long stop loss hit at {current_price:.2f} (stop: {stop_info['stop_price']:.2f}). "
                             f"Positions since cross reset to {self.long_positions_since_cross}", color=LogColor.RED)
                
            elif stop_info['side'] == 'short' and current_price >= stop_info['stop_price']:
                positions_to_close.append(position_id)
                self.short_positions_since_cross = max(0, self.short_positions_since_cross - 1)
                self.log.info(f"Short stop loss hit at {current_price:.2f} (stop: {stop_info['stop_price']:.2f}). "
                             f"Positions since cross reset to {self.short_positions_since_cross}", color=LogColor.RED)
        
        for position_id in positions_to_close:
            self.order_types.close_position_by_market_order()
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
    
    def _check_kalman_cross_for_stacking(self, bar):
        if self.current_ltf_kalman_mean is None:
            return
            
        current_above = bar.close > self.current_ltf_kalman_mean
        current_direction = "up" if current_above else "down"
        
        if self.last_kalman_cross_direction is not None and self.last_kalman_cross_direction != current_direction:
            self.long_positions_since_cross = 0
            self.short_positions_since_cross = 0
            self.long_entry_zscores = []
            self.short_entry_zscores = []
            self.bars_since_last_long_entry = 0
            self.bars_since_last_short_entry = 0
            
            self.elastic_entry.reset_on_cross()
            
            anchor_method = self.vwap_anchor_method
            
            self.log.info(f"Kalman cross detected: {self.last_kalman_cross_direction} -> {current_direction} | Anchor method: {anchor_method}", color=LogColor.CYAN)
            
            if anchor_method == 'kalman_cross':
                self._notify_vwap_exit_if_needed()
                self.log.info(f"Kalman cross detected: {self.last_kalman_cross_direction} -> {current_direction} | VWAP reset", color=LogColor.BLUE)
        
        self.last_kalman_cross_direction = current_direction
    
    def _check_daily_stacking_reset(self, bar, zscore, adaptive_params):
        if not self.allow_daily_stacking_reset:
            return
            
        current_day = bar.ts_event.date()
        
        if self.current_trading_day != current_day:
            self.current_trading_day = current_day
            self.daily_long_stacking_reset = False
            self.daily_short_stacking_reset = False
            return
        
        if zscore is None:
            return
            
        if (zscore <= -2.5 and 
            not self.daily_long_stacking_reset and 
            self.long_positions_since_cross > 0):
            self.daily_long_stacking_reset = True
            self.log.info(f"Daily stacking reset triggered for LONG positions at zscore {zscore:.3f}", color=LogColor.GREEN)
            
        if (zscore >= 2.5 and 
            not self.daily_short_stacking_reset and 
            self.short_positions_since_cross > 0):
            self.daily_short_stacking_reset = True
            self.log.info(f"Daily stacking reset triggered for SHORT positions at zscore {zscore:.3f}", color=LogColor.RED)
    
    def can_stack_long(self, current_zscore: float) -> bool:
        if self.long_positions_since_cross == 0:
            return True
            
        if not self._should_allow_stacking('long'):
            return False
            
        if not self.allow_stacking:
            return False

        if self.daily_long_stacking_reset:
            return True
        
        if self.long_positions_since_cross >= self.max_long_stacked_positions:
            return False
                    
        if self.bars_since_last_long_entry < self.stacking_bar_cooldown:
            return False
            
        if self.long_entry_zscores and current_zscore is not None:
            last_entry_zscore = self.long_entry_zscores[-1]
            zscore_deterioration = last_entry_zscore - current_zscore
            
            if zscore_deterioration < self.additional_zscore_min_gain:
                return False
        
        return True  
    
    def can_stack_short(self, current_zscore: float) -> bool:
        if self.short_positions_since_cross == 0:
            return True
            
        if not self._should_allow_stacking('short'):
            return False
            
        if not self.allow_stacking:
            return False

        if self.daily_short_stacking_reset:
            return True
        
        if self.short_positions_since_cross >= self.max_short_stacked_positions:
            return False
            
        if self.bars_since_last_short_entry < self.stacking_bar_cooldown:
            return False
            
        if self.short_entry_zscores and current_zscore is not None:
            last_entry_zscore = self.short_entry_zscores[-1]
            zscore_deterioration = current_zscore - last_entry_zscore
            
            if zscore_deterioration < self.additional_zscore_min_gain:
                return False
        
        return True

    def get_vix_regime(self, vix_value: float) -> int:
        if vix_value is None:
            return 1  # Default to normal regime
        
        vix_val = float(vix_value) if not isinstance(vix_value, (int, float)) else vix_value
        
        if vix_val >= self.vix_fear:
            return 2  # Fear regime
        else:
            return 1  # Normal regime
    
    def check_for_long_trades(self, bar: Bar, zscore: float, adaptive_params: dict):
        if self.current_ltf_kalman_mean is not None and bar.close >= self.current_ltf_kalman_mean:
            return

        long_min_distance = adaptive_params['elastic_entry']['long_min_distance_from_kalman']
        if self.current_ltf_kalman_zscore is not None and self.current_ltf_kalman_zscore > long_min_distance:
            return

        regime = self.get_vix_regime(self.current_vix_value)
        if regime == 2:
            return
        
        can_enter = self.can_stack_long(zscore)
        if not can_enter:
            return

        long_risk_factor = adaptive_params['long_risk_factor']
        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(long_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return

        long_signal, _, debug_info = self.elastic_entry.check_entry_signals(zscore)
        
        if long_signal:
            entry_reason = debug_info.get('long_entry_reason', 'Recovery signal')
            stack_info = f"Stack {self.long_positions_since_cross + 1}/{self.max_long_stacked_positions}" if self.long_positions_since_cross > 0 else "Initial"
            
            hard_stops_enabled = self.adaptive_manager.is_hard_stop_enabled()['long_enabled']
            re_entry_note = " (RE-ENTRY after SL)" if hard_stops_enabled and self.long_positions_since_cross == 0 else ""
            
            trade_message = self.adaptive_manager.log_trade_state(
                "LONG", float(bar.close), zscore, entry_reason, stack_info, regime, 
                adaptive_params, self.long_positions_since_cross, self.short_positions_since_cross, 
                self.allow_stacking
            )
            self.log.info(f"{trade_message}{re_entry_note}", color=LogColor.MAGENTA)
            
            self.order_types.submit_long_market_order(qty, price=bar.close)
            self.long_positions_since_cross += 1
            self.entry_atr_factor = self.current_atr_factor
            
            self._track_position_entry('long', float(bar.close))
            
            if self.daily_long_stacking_reset:
                self.daily_long_stacking_reset = False
                self.log.info("Daily long stacking reset flag cleared after position entry", color=LogColor.GREEN)
            
            self.long_entry_zscores.append(zscore)
            self.bars_since_last_long_entry = 0

    def check_for_short_trades(self, bar: Bar, zscore: float, adaptive_params: dict):
        if self.current_ltf_kalman_mean is not None and bar.close <= self.current_ltf_kalman_mean:
            return
    
        short_min_distance = adaptive_params['elastic_entry']['short_min_distance_from_kalman']
        if self.current_ltf_kalman_zscore is not None and self.current_ltf_kalman_zscore < short_min_distance:
            return

        regime = self.get_vix_regime(self.current_vix_value)
        if regime == 2:
            return
        
        can_enter = self.can_stack_short(zscore)
        if not can_enter:
            return

        short_risk_factor = adaptive_params['short_risk_factor']
        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(short_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return

        _, short_signal, debug_info = self.elastic_entry.check_entry_signals(zscore)
        
        if short_signal:
            entry_reason = debug_info.get('short_entry_reason', 'Recovery signal')
            stack_info = f"Stack {self.short_positions_since_cross + 1}/{self.max_short_stacked_positions}" if self.short_positions_since_cross > 0 else "Initial"
            
            hard_stops_enabled = self.adaptive_manager.is_hard_stop_enabled()['short_enabled']
            re_entry_note = " (RE-ENTRY after SL)" if hard_stops_enabled and self.short_positions_since_cross == 0 else ""
            
            trade_message = self.adaptive_manager.log_trade_state(
                "SHORT", float(bar.close), zscore, entry_reason, stack_info, regime, 
                adaptive_params, self.long_positions_since_cross, self.short_positions_since_cross, 
                self.allow_stacking
            )
            self.log.info(f"{trade_message}{re_entry_note}", color=LogColor.MAGENTA)
            
            self.order_types.submit_short_market_order(qty, price=bar.close)
            self.short_positions_since_cross += 1
            self.entry_atr_factor = self.current_atr_factor
            
            self._track_position_entry('short', float(bar.close))
            
            if self.daily_short_stacking_reset:
                self.daily_short_stacking_reset = False
                self.log.info("Daily short stacking reset flag cleared after position entry", color=LogColor.RED)
            
            self.short_entry_zscores.append(zscore)
            self.bars_since_last_short_entry = 0

    def check_for_long_exit(self, bar, adaptive_params: dict):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        
        if regime == 2:
            self._notify_vwap_exit_if_needed()
            self.order_types.close_position_by_market_order()
            return

        net_pos = self.portfolio.net_position(self.instrument_id)
        
        if net_pos is not None and net_pos > 0 and self.current_ltf_kalman_zscore is not None:
            long_exit, _ = self.adaptive_manager.get_adaptive_exit_thresholds(slope=self.current_htf_kalman_slope)
            
            if self.current_ltf_kalman_zscore >= long_exit:
                self._notify_vwap_exit_if_needed()
                self.order_types.close_position_by_market_order()

    def check_for_short_exit(self, bar, adaptive_params: dict):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        
        if regime == 2:
            self._notify_vwap_exit_if_needed()
            self.order_types.close_position_by_market_order()
            return
        
        net_pos = self.portfolio.net_position(self.instrument_id)
        
        if net_pos is not None and net_pos < 0 and self.current_ltf_kalman_zscore is not None:
            _, short_exit = self.adaptive_manager.get_adaptive_exit_thresholds(slope=self.current_htf_kalman_slope)
            
            if self.current_ltf_kalman_zscore <= short_exit:
                self._notify_vwap_exit_if_needed()
                self.order_types.close_position_by_market_order()

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        self._notify_vwap_exit_if_needed()
        return self.base_close_position()
    
    def on_stop(self) -> None:
        self.base_on_stop()
        try:
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        except Exception as e:
            self.log.warning(f"Could not calculate unrealized PnL: {e}")
            unrealized_pnl = None
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balance_total()
        equity = usd_balance.as_double() + float(unrealized_pnl) if unrealized_pnl is not None else usd_balance.as_double()
        vwap_value = self.vwap_zscore.current_vwap_value

        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="ltf_kalman_mean", value=self.current_ltf_kalman_mean)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="htf_kalman_mean", value=self.current_htf_kalman_mean)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap", value=vwap_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="atr_factor", value=self.current_atr_factor)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap_zscore", value=self.current_zscore)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="slope_factor", value=self.current_slope_factor)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_zscore", value=self.current_ltf_kalman_zscore)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vix", value=self.current_vix_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="equity", value=equity)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="long_risk", value=self.current_long_risk_factor)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="short_risk", value=self.current_short_risk_factor)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="long_exit", value=self.current_long_exit)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="short_exit", value=self.current_short_exit)

        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

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
    
    def update_visualizer_data(self, bar: Bar) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balance_total()
        equity = usd_balance.as_double() + float(unrealized_pnl) if unrealized_pnl is not None else usd_balance.as_double()
            
        vwap_value = self.vwap_zscore.current_vwap_value

        self.collector.add_indicator(timestamp=bar.ts_event, name="ltf_kalman_mean", value=self.current_ltf_kalman_mean)
        self.collector.add_indicator(timestamp=bar.ts_event, name="htf_kalman_mean", value=self.current_htf_kalman_mean)
        self.collector.add_indicator(timestamp=bar.ts_event, name="vwap", value=vwap_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="atr_factor", value=self.current_atr_factor)
        self.collector.add_indicator(timestamp=bar.ts_event, name="vwap_zscore", value=self.current_zscore)
        self.collector.add_indicator(timestamp=bar.ts_event, name="slope_factor", value=self.current_slope_factor)
        self.collector.add_indicator(timestamp=bar.ts_event, name="zscore_offset", value=self.current_asymmetric_offset)
        self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_zscore", value=self.current_ltf_kalman_zscore)
        self.collector.add_indicator(timestamp=bar.ts_event, name="vix", value=self.current_vix_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="equity", value=equity)
        self.collector.add_indicator(timestamp=bar.ts_event, name="long_risk", value=self.current_long_risk_factor)
        self.collector.add_indicator(timestamp=bar.ts_event, name="short_risk", value=self.current_short_risk_factor)
        self.collector.add_indicator(timestamp=bar.ts_event, name="long_exit", value=self.current_long_exit)
        self.collector.add_indicator(timestamp=bar.ts_event, name="short_exit", value=self.current_short_exit)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)