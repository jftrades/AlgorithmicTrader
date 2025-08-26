import numpy as np
from collections import deque
from tools.help_funcs.distrubition_monitor import ATRDistributionMonitor, SlopeDistributionMonitor, ZScoreDistributionMonitor


class RobustATRCalculator:
    def __init__(self, atr_window: int = 14, percentile_window: int = 200, outlier_threshold: float = 3.0):
        self.atr_window = atr_window
        self.percentile_window = percentile_window
        self.alpha = 2.0 / (atr_window + 1) 
        self.atr_history = deque(maxlen=percentile_window)
        self.current_atr = None
        self.current_percentile = 0.5
        self.prev_close = None
        
    def _soft_clamp(self, value: float, min_val: float = 0.05, max_val: float = 0.95, steepness: float = 10.0) -> float:
        if value <= min_val:
            return min_val + (max_val - min_val) / (1 + np.exp(steepness * (min_val - value)))
        elif value >= max_val:
            return max_val - (max_val - min_val) / (1 + np.exp(steepness * (value - max_val)))
        else:
            return value
    
    def _calculate_percentile_efficient(self, value: float, sorted_history: list) -> float:
        if not sorted_history:
            return 0.5
            
        left, right = 0, len(sorted_history)
        while left < right:
            mid = (left + right) // 2
            if sorted_history[mid] < value:
                left = mid + 1
            else:
                right = mid
        
        return left / len(sorted_history)
    
    def update(self, high: float, low: float, prev_close: float = None) -> tuple:
        if prev_close is not None:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        elif self.prev_close is not None:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
        else:
            tr = high - low
        
        if self.current_atr is None:
            self.current_atr = tr
        else:
            self.current_atr = self.alpha * tr + (1 - self.alpha) * self.current_atr
        
        self.atr_history.append(self.current_atr)
        self.prev_close = prev_close if prev_close is not None else high
        
        if len(self.atr_history) > 10:
            sorted_history = sorted(list(self.atr_history))
            percentile = self._calculate_percentile_efficient(self.current_atr, sorted_history)
            self.current_percentile = self._soft_clamp(percentile)
        
        return self.current_atr, self.current_percentile


class AdaptiveParameterManager:
    def __init__(self, base_params: dict, adaptive_factors: dict, kalman_filter=None):
        self.base_params = base_params
        self.adaptive_factors = adaptive_factors
        self.current_slope = 0.0
        self.current_kalman_mean = None
        
        if self.adaptive_factors.get('atr', {}).get('enabled', False):
            atr_config = self.adaptive_factors['atr']
            self.atr_calculator = RobustATRCalculator(
                atr_window=atr_config.get('window', 14),
                percentile_window=atr_config.get('percentile_window', 500),
                outlier_threshold=atr_config.get('outlier_threshold', 3.0)
            )
        else:
            self.atr_calculator = None
        
        base_section = self.base_params.get('base_parameters', self.base_params)
        hard_stop_window = base_section.get('ATR_window_if_use_SL', 20)
        self.hard_stop_atr_calculator = RobustATRCalculator(
            atr_window=hard_stop_window,
            percentile_window=100,
            outlier_threshold=2.0
        )
        
        self.atr_monitor = ATRDistributionMonitor(max_values=100000) if self.adaptive_factors.get('distribution_monitor', {}).get('atr_distribution', {}).get('enabled', False) else None
        self.slope_monitor = SlopeDistributionMonitor(max_values=100000) if self.adaptive_factors.get('distribution_monitor', {}).get('slope_distribution', {}).get('enabled', False) else None
        self.zscore_monitor = ZScoreDistributionMonitor(max_values=100000) if self.adaptive_factors.get('distribution_monitor', {}).get('zscore_distribution', {}).get('enabled', False) else None
    
    def update_slope(self, ltf_kalman_mean: float, htf_kalman_slope: float):
        if ltf_kalman_mean is not None:
            self.current_kalman_mean = ltf_kalman_mean
        if htf_kalman_slope is not None:
            self.current_slope = htf_kalman_slope
            if self.slope_monitor is not None:
                self.slope_monitor.add_slope(htf_kalman_slope)
        return ltf_kalman_mean, htf_kalman_slope
    
    def update_atr(self, high: float, low: float, prev_close: float = None):
        if self.atr_calculator is not None:
            current_atr, percentile = self.atr_calculator.update(high, low, prev_close)
            if self.atr_monitor is not None and current_atr is not None:
                self.atr_monitor.add_atr(current_atr)
        
        self.hard_stop_atr_calculator.update(high, low, prev_close)
        
        if self.atr_calculator is not None:
            return current_atr, percentile
        return None, 0.5
    
    def update_zscore(self, zscore_value: float):
        if self.zscore_monitor is not None and zscore_value is not None:
            self.zscore_monitor.add_zscore(zscore_value)
    
    def _get_normalized_slope(self, slope: float = None) -> float:
        slope_to_use = slope if slope is not None else self.current_slope
        
        if slope_to_use is None:
            return 0.0
        
        slope_config = self.adaptive_factors.get('slope', {})
        max_bull_slope = slope_config.get('max_bull_slope', 0.02)
        max_bear_slope = slope_config.get('max_bear_slope', -0.02)
        
        clamped_slope = max(max_bear_slope, min(max_bull_slope, slope_to_use))
        
        if clamped_slope >= 0:
            normalized = clamped_slope / max_bull_slope
        else:
            normalized = clamped_slope / abs(max_bear_slope)
        
        return normalized

    def calculate_slope_based_risk_factors(self, slope: float = None) -> tuple:
        slope_risk_config = self.base_params.get('slope_risk_scaling', {})
        
        if not slope_risk_config.get('enabled', False):
            return 1.0, 1.0
        
        normalized_slope = self._get_normalized_slope(slope)
        
        base_long_risk = slope_risk_config.get('base_long_risk', 1.0)
        base_short_risk = slope_risk_config.get('base_short_risk', 1.0)
        max_long_risk_uptrend = slope_risk_config.get('max_long_risk_uptrend', 2.0)
        max_long_risk_downtrend = slope_risk_config.get('max_long_risk_downtrend', 0.1)
        max_short_risk_uptrend = slope_risk_config.get('max_short_risk_uptrend', 0.1)
        max_short_risk_downtrend = slope_risk_config.get('max_short_risk_downtrend', 2.0)
        
        if normalized_slope >= 0:
            long_risk = base_long_risk + normalized_slope * (max_long_risk_uptrend - base_long_risk)
            short_risk = base_short_risk - normalized_slope * (base_short_risk - max_short_risk_uptrend)
        else:
            long_risk = base_long_risk - abs(normalized_slope) * (base_long_risk - max_long_risk_downtrend)
            short_risk = base_short_risk + abs(normalized_slope) * (max_short_risk_downtrend - base_short_risk)
        
        return long_risk, short_risk
    
    def calculate_slope_based_exit_thresholds(self, slope: float = None) -> tuple:
        slope_exit_config = self.base_params.get('slope_exit_scaling', {})
        
        if not slope_exit_config.get('enabled', False):
            return 5.0, -5.0
        
        normalized_slope = self._get_normalized_slope(slope)
        
        base_long_exit = slope_exit_config.get('base_long_exit', 5.0)
        base_short_exit = slope_exit_config.get('base_short_exit', -5.0)
        max_long_exit_uptrend = slope_exit_config.get('max_long_exit_uptrend', 20.0)
        max_long_exit_downtrend = slope_exit_config.get('max_long_exit_downtrend', 2.0)
        max_short_exit_uptrend = slope_exit_config.get('max_short_exit_uptrend', -2.0)
        max_short_exit_downtrend = slope_exit_config.get('max_short_exit_downtrend', -20.0)
        
        if normalized_slope >= 0:
            long_exit = base_long_exit + normalized_slope * (max_long_exit_uptrend - base_long_exit)
            short_exit = base_short_exit - normalized_slope * (base_short_exit - max_short_exit_uptrend)
        else:
            long_exit = base_long_exit - abs(normalized_slope) * (base_long_exit - max_long_exit_downtrend)
            short_exit = base_short_exit + abs(normalized_slope) * (max_short_exit_downtrend - base_short_exit)
        
        return long_exit, short_exit
    
    def calculate_slope_based_asymmetric_offset(self, slope: float = None) -> float:
        slope_offset_config = self.base_params.get('slope_asymmetric_offset', {})
        
        if not slope_offset_config.get('enabled', False):
            return 0.0
        
        normalized_slope = self._get_normalized_slope(slope)
        
        base_offset = slope_offset_config.get('base_offset', 0.0)
        max_offset_uptrend = slope_offset_config.get('max_offset_uptrend', 1.8)
        max_offset_downtrend = slope_offset_config.get('max_offset_downtrend', -1.8)
        
        if normalized_slope >= 0:
            offset = base_offset + normalized_slope * (max_offset_uptrend - base_offset)
        else:
            offset = base_offset + abs(normalized_slope) * (max_offset_downtrend - base_offset)
        
        return offset
    
    def calculate_atr_factor(self) -> float:
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return 1.0
            
        atr_config = self.adaptive_factors['atr']
        
        if self.atr_calculator is None or len(self.atr_calculator.atr_history) < 20:
            return 1.0
        
        current_percentile = self.atr_calculator.current_percentile
        
        factor = atr_config['min'] + current_percentile * (atr_config['max'] - atr_config['min'])
        
        return factor
    
    def get_adaptive_exit_thresholds(self, entry_atr_factor: float = None, slope: float = None) -> tuple:
        return self.calculate_slope_based_exit_thresholds(slope)
    
    def get_adaptive_parameters(self, slope: float = None) -> tuple:
        slope_to_use = slope if slope is not None else self.current_slope
        
        normalized_slope = self._get_normalized_slope(slope_to_use)
        atr_factor = self.calculate_atr_factor()
        
        adaptive_params = {}
        
        elastic_base = self.base_params['elastic_entry']
        adaptive_params['elastic_entry'] = {
            'zscore_long_threshold': elastic_base['zscore_long_threshold'] * atr_factor,
            'zscore_short_threshold': elastic_base['zscore_short_threshold'] * atr_factor,
            'recovery_delta': elastic_base['recovery_delta'] * atr_factor,
            'long_min_distance_from_kalman': elastic_base['long_min_distance_from_kalman'] * atr_factor,
            'short_min_distance_from_kalman': elastic_base['short_min_distance_from_kalman'] * atr_factor,
            'additional_zscore_min_gain': elastic_base['additional_zscore_min_gain'] * atr_factor,
            'recovery_delta_reentry': elastic_base['recovery_delta_reentry'] * atr_factor,
            'allow_multiple_recoveries': elastic_base['allow_multiple_recoveries'],
            'recovery_cooldown_bars': elastic_base['recovery_cooldown_bars'],
            'stacking_bar_cooldown': elastic_base['stacking_bar_cooldown'],
            'allow_stacking': elastic_base.get('allow_stacking', True),
            'max_long_stacked_positions': elastic_base.get('max_long_stacked_positions', 3),
            'max_short_stacked_positions': elastic_base.get('max_short_stacked_positions', 3),
        }
        
        long_exit, short_exit = self.get_adaptive_exit_thresholds(None, slope_to_use)
        adaptive_params['kalman_zscore_exit_long'] = long_exit
        adaptive_params['kalman_zscore_exit_short'] = short_exit
        
        adaptive_params['long_risk_factor'], adaptive_params['short_risk_factor'] = self.calculate_slope_based_risk_factors(slope_to_use)
        
        vwap_base = self.base_params.get('vwap', {})
        adaptive_params['vwap'] = {
            'anchor_method': vwap_base.get('anchor_method', 'kalman_cross'),
            'vwap_require_trade_for_reset': vwap_base.get('vwap_require_trade_for_reset', True),
            'vwap_min_bars_for_zscore': vwap_base.get('vwap_min_bars_for_zscore', 20),
            'vwap_reset_grace_period': vwap_base.get('vwap_reset_grace_period', 40),
            'rolling_window_bars': vwap_base.get('rolling_window_bars', 288),
        }
        
        adaptive_params['ltf_kalman_process_var'] = self.base_params['ltf_kalman_process_var']
        adaptive_params['ltf_kalman_measurement_var'] = self.base_params['ltf_kalman_measurement_var']
        adaptive_params['ltf_kalman_zscore_window'] = self.base_params['ltf_kalman_zscore_window']
        
        adaptive_params['htf_kalman_process_var'] = self.base_params['htf_kalman_process_var']
        adaptive_params['htf_kalman_measurement_var'] = self.base_params['htf_kalman_measurement_var']
        adaptive_params['htf_kalman_zscore_window'] = self.base_params['htf_kalman_zscore_window']
        
        return adaptive_params, normalized_slope, atr_factor
    
    def get_asymmetric_offset(self, base_mean: float = None, force_reset: bool = False, slope: float = None) -> float:
        if force_reset:
            return 0.0
            
        slope_offset_config = self.base_params.get('slope_asymmetric_offset', {})
        if slope_offset_config.get('enabled', False):
            effective_slope = slope if slope is not None else self.current_slope
            return self.calculate_slope_based_asymmetric_offset(effective_slope)
        
        return 0.0
    
    def get_hard_stop_levels(self, entry_price: float) -> dict:
        hard_stop_atr = self.hard_stop_atr_calculator.current_atr
        if hard_stop_atr is None:
            return {'long_enabled': False, 'short_enabled': False}
        
        base_section = self.base_params.get('base_parameters', self.base_params)
        long_config = base_section.get('use_hard_stop_long', {})
        short_config = base_section.get('use_hard_stop_short', {})
        
        result = {
            'long_enabled': long_config.get('enabled', False),
            'short_enabled': short_config.get('enabled', False),
            'hard_stop_atr': hard_stop_atr
        }
        
        if result['long_enabled']:
            atr_multiplier = long_config.get('atr_stop_long', 2)
            result['long_stop_price'] = entry_price - (hard_stop_atr * atr_multiplier)
        
        if result['short_enabled']:
            atr_multiplier = short_config.get('atr_stop_short', 2)
            result['short_stop_price'] = entry_price + (hard_stop_atr * atr_multiplier)
        
        return result
    
    def is_hard_stop_enabled(self) -> dict:
        base_section = self.base_params.get('base_parameters', self.base_params)
        return {
            'long_enabled': base_section.get('use_hard_stop_long', {}).get('enabled', False),
            'short_enabled': base_section.get('use_hard_stop_short', {}).get('enabled', False)
        }
    
    def log_trade_state(self, trade_type: str, price: float, zscore: float, entry_reason: str, 
                       stack_info: str, regime: int, adaptive_params: dict, 
                       long_positions: int, short_positions: int, allow_stacking: bool):
        
        _, normalized_slope, atr_factor = self.get_adaptive_parameters()
        
        message = f"{trade_type.upper()} ${price:.2f} | ZScore: {zscore:.3f} | Adaptive values: slope={normalized_slope:.3f}, atr={atr_factor:.3f}"
        
        return message

    def reset_trend_state_for_vwap_anchor(self):
        if hasattr(self, 'current_slope'):
            self.current_slope = 0.0
    
    def print_slope_distribution(self):
        if self.slope_monitor is not None:
            self.slope_monitor.print_distribution()
    
    def print_atr_distribution(self):
        if self.atr_monitor is not None:
            self.atr_monitor.print_distribution()
    
    def print_zscore_distribution(self):
        if self.zscore_monitor is not None:
            self.zscore_monitor.print_distribution()
