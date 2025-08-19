import numpy as np
from collections import deque
from tools.help_funcs.distrubition_monitor import SlopeDistributionMonitor, ATRDistributionMonitor


class RobustATRCalculator:
    def __init__(self, atr_window: int = 14, percentile_window: int = 200, outlier_threshold: float = 3.0):
        self.atr_window = atr_window
        self.percentile_window = percentile_window
        self.outlier_threshold = outlier_threshold
        
        self.tr_history = deque(maxlen=atr_window)
        self.atr_history = deque(maxlen=percentile_window)
        self.current_atr = None
        self.current_percentile = 0.5
        
    def _winsorize_tr(self, tr_values: list, threshold: float = 3.0) -> list:
        """Apply winsorization to remove outliers from True Range values"""
        if len(tr_values) < 3:
            return tr_values
            
        tr_array = np.array(tr_values)
        median = np.median(tr_array)
        mad = np.median(np.abs(tr_array - median))
        
        # Modified Z-score using median absolute deviation
        if mad == 0:
            return tr_values
        
        # Winsorize outliers
        upper_limit = median + threshold * mad / 0.6745
        lower_limit = max(0, median - threshold * mad / 0.6745)
        
        winsorized = np.clip(tr_array, lower_limit, upper_limit)
        return winsorized.tolist()
    
    def _soft_clamp(self, value: float, min_val: float = 0.05, max_val: float = 0.95, steepness: float = 10.0) -> float:
        """Soft clamping using sigmoid function"""
        if value <= min_val:
            return min_val + (max_val - min_val) / (1 + np.exp(steepness * (min_val - value)))
        elif value >= max_val:
            return max_val - (max_val - min_val) / (1 + np.exp(steepness * (value - max_val)))
        else:
            return value
    
    def _calculate_percentile_efficient(self, value: float, sorted_history: list) -> float:
        """Efficient percentile calculation using binary search"""
        if not sorted_history:
            return 0.5
            
        # Binary search for insertion point
        left, right = 0, len(sorted_history)
        while left < right:
            mid = (left + right) // 2
            if sorted_history[mid] < value:
                left = mid + 1
            else:
                right = mid
        
        return left / len(sorted_history)
    
    def update(self, high: float, low: float, prev_close: float = None) -> tuple:
        """Update ATR calculation with robust outlier handling"""
        # Calculate True Range
        if prev_close is not None:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        else:
            tr = high - low
        
        self.tr_history.append(tr)
        
        # Apply winsorization if we have enough data
        if len(self.tr_history) >= 5:
            winsorized_tr = self._winsorize_tr(list(self.tr_history))
            current_atr = np.mean(winsorized_tr)
        else:
            current_atr = np.mean(self.tr_history)
        
        self.current_atr = current_atr
        self.atr_history.append(current_atr)
        
        # Calculate percentile efficiently
        if len(self.atr_history) > 10:
            sorted_history = sorted(list(self.atr_history))
            percentile = self._calculate_percentile_efficient(current_atr, sorted_history)
            self.current_percentile = self._soft_clamp(percentile)
        
        return current_atr, self.current_percentile


class AdaptiveParameterManager:
    def calculate_slope_factor(self, slope: float) -> float:
        if not self.adaptive_factors.get('slope', {}).get('enabled', False):
            return 1.0
        
        slope_config = self.adaptive_factors['slope']
        
        if self.slope_monitor and len(self.slope_monitor.values) >= 200:
            normalized_slope = self._calculate_percentile_based_factor(
                slope, self.slope_monitor, is_absolute=True
            )
            scale_factor = slope_config['min'] + normalized_slope * (slope_config['max'] - slope_config['min'])
            return scale_factor
        
        return 1.0
    def __init__(self, base_params: dict, adaptive_factors: dict, kalman_filter=None):
        self.base_params = base_params
        self.adaptive_factors = adaptive_factors
        self.kalman = kalman_filter
        self.current_slope = 0.0
        self.current_kalman_mean = None
        
        self.smoothed_combined_factor = 1.0
        self.factor_alpha = 0.2
        
        if self.adaptive_factors.get('atr', {}).get('enabled', False):
            atr_config = self.adaptive_factors['atr']
            self.atr_calculator = RobustATRCalculator(
                atr_window=atr_config.get('window', 14),
                percentile_window=atr_config.get('percentile_window', 200),
                outlier_threshold=atr_config.get('outlier_threshold', 3.0)
            )
            self.current_atr_percentile = 0.5
        else:
            self.atr_calculator = None
            self.current_atr_percentile = 0.5
        
        # Slope Distribution Monitor - always create if slope factors are enabled
        if self.adaptive_factors.get('slope', {}).get('enabled', False):
            self.slope_monitor = SlopeDistributionMonitor(max_values=100000)  # Conservative limit
        else:
            self.slope_monitor = None
        
        # ATR Distribution Monitor - always create if ATR factors are enabled  
        if self.adaptive_factors.get('atr', {}).get('enabled', False):
            self.atr_monitor = ATRDistributionMonitor(max_values=100000)  # Conservative limit
        else:
            self.atr_monitor = None
    
    def update_slope(self, ltf_kalman_mean: float, htf_kalman_slope: float):
        if ltf_kalman_mean is not None:
            self.current_kalman_mean = ltf_kalman_mean
        if htf_kalman_slope is not None:
            self.current_slope = htf_kalman_slope
            if self.slope_monitor is not None:
                self.slope_monitor.add_slope(htf_kalman_slope)
        return ltf_kalman_mean, htf_kalman_slope
    
    def update_market_data(self, ltf_kalman_mean: float, htf_kalman_slope: float, high: float, low: float, prev_close: float = None):
        self.update_slope(ltf_kalman_mean, htf_kalman_slope)
        self.update_atr(high, low, prev_close)
    
    def update_atr(self, high: float, low: float, prev_close: float = None):
        """Update ATR with robust calculation"""
        if self.atr_calculator is not None:
            current_atr, percentile = self.atr_calculator.update(high, low, prev_close)
            self.current_atr_percentile = percentile
            if self.atr_monitor is not None and current_atr is not None:
                self.atr_monitor.add_atr(current_atr)
            return current_atr, percentile
        return None, self.current_atr_percentile
    
    def _calculate_percentile_based_factor(self, value: float, monitor, is_absolute: bool = False) -> float:
        if len(monitor.values) < 200:
            return 0.5
        
        percentiles = monitor._calculate_weighted_percentiles([5, 95])
        p5, p95 = percentiles[5], percentiles[95]
        
        if p5 is None or p95 is None or p95 <= p5:
            return 0.5
        
        comparison_value = abs(value) if is_absolute else value
        
        if is_absolute:
            p5, p95 = abs(p5), abs(p95)
            if p5 > p95:
                p5, p95 = p95, p5
        
        if comparison_value <= p5:
            return 0.0
        elif comparison_value >= p95:
            return 1.0
        else:
            normalized = (comparison_value - p5) / (p95 - p5)
            return max(0.0, min(1.0, normalized))
    
    def _robust_factor_combination(self, slope_factor: float, atr_factor: float) -> float:
        combination_config = self.adaptive_factors.get('combination', {})
        min_combined = combination_config.get('min_combined_factor', 0.3)
        max_combined = combination_config.get('max_combined_factor', 3.0)
        
        slope_weight = 0.7
        atr_weight = 0.3
        
        raw_combined_factor = (slope_factor * slope_weight) + (atr_factor * atr_weight)
        raw_combined_factor = np.clip(raw_combined_factor, min_combined, max_combined)
        self.smoothed_combined_factor = (self.factor_alpha * raw_combined_factor + 
                                       (1 - self.factor_alpha) * self.smoothed_combined_factor)
        return self.smoothed_combined_factor
    
    def calculate_slope_based_risk_factors(self, slope: float = None) -> tuple:
        slope_risk_config = self.base_params.get('slope_risk_scaling', {})
        
        if not slope_risk_config.get('enabled', False):
            return 1.0, 1.0
        
        slope_to_use = slope if slope is not None else self.current_slope
        slope_config = self.adaptive_factors.get('slope', {})
        sensitivity = slope_config.get('sensitivity', 0.04)
        
        base_long_risk = slope_risk_config.get('base_long_risk', 1.0)
        base_short_risk = slope_risk_config.get('base_short_risk', 1.0)
        max_long_risk_uptrend = slope_risk_config.get('max_long_risk_uptrend', 2.0)
        max_long_risk_downtrend = slope_risk_config.get('max_long_risk_downtrend', 0.1)
        max_short_risk_uptrend = slope_risk_config.get('max_short_risk_uptrend', 0.1)
        max_short_risk_downtrend = slope_risk_config.get('max_short_risk_downtrend', 2.0)
        scaling_method = slope_risk_config.get('scaling_method', 'linear')
        
        normalized_slope = slope_to_use / sensitivity
        normalized_slope = np.clip(normalized_slope, -1.0, 1.0)
        
        if scaling_method == 'linear':
            if normalized_slope >= 0:
                long_risk = base_long_risk + normalized_slope * (max_long_risk_uptrend - base_long_risk)
                short_risk = base_short_risk + normalized_slope * (max_short_risk_uptrend - base_short_risk)
            else:
                long_risk = base_long_risk + abs(normalized_slope) * (max_long_risk_downtrend - base_long_risk)
                short_risk = base_short_risk + abs(normalized_slope) * (max_short_risk_downtrend - base_short_risk)
        
        elif scaling_method == 'exponential':
            exp_factor = np.exp(abs(normalized_slope)) - 1
            if normalized_slope >= 0:
                long_risk = base_long_risk + exp_factor * (max_long_risk_uptrend - base_long_risk) / (np.e - 1)
                short_risk = base_short_risk + exp_factor * (max_short_risk_uptrend - base_short_risk) / (np.e - 1)
            else:
                long_risk = base_long_risk + exp_factor * (max_long_risk_downtrend - base_long_risk) / (np.e - 1)
                short_risk = base_short_risk + exp_factor * (max_short_risk_downtrend - base_short_risk) / (np.e - 1)
        
        elif scaling_method == 'logarithmic':
            log_factor = np.log1p(abs(normalized_slope)) / np.log(2)
            if normalized_slope >= 0:
                long_risk = base_long_risk + log_factor * (max_long_risk_uptrend - base_long_risk)
                short_risk = base_short_risk + log_factor * (max_short_risk_uptrend - base_short_risk)
            else:
                long_risk = base_long_risk + log_factor * (max_long_risk_downtrend - base_long_risk)
                short_risk = base_short_risk + log_factor * (max_short_risk_downtrend - base_short_risk)
        
        else:
            long_risk = base_long_risk
            short_risk = base_short_risk
        
        return long_risk, short_risk
    
    def calculate_slope_based_exit_thresholds(self, slope: float = None) -> tuple:
        slope_exit_config = self.base_params.get('slope_exit_scaling', {})
        
        if not slope_exit_config.get('enabled', False):
            adaptive_exit_config = self.base_params.get('adaptive_exit', {})
            long_base = adaptive_exit_config.get('long_base_exit', 5.0)
            short_base = adaptive_exit_config.get('short_base_exit', -5.0)
            return long_base, short_base
        
        slope_to_use = slope if slope is not None else self.current_slope
        slope_config = self.adaptive_factors.get('slope', {})
        sensitivity = slope_config.get('sensitivity', 0.04)
        
        base_long_exit = slope_exit_config.get('base_long_exit', 5.0)
        base_short_exit = slope_exit_config.get('base_short_exit', -5.0)
        max_long_exit_uptrend = slope_exit_config.get('max_long_exit_uptrend', 20.0)
        max_long_exit_downtrend = slope_exit_config.get('max_long_exit_downtrend', 2.0)
        max_short_exit_uptrend = slope_exit_config.get('max_short_exit_uptrend', -2.0)
        max_short_exit_downtrend = slope_exit_config.get('max_short_exit_downtrend', -20.0)
        scaling_method = slope_exit_config.get('scaling_method', 'linear')
        
        normalized_slope = slope_to_use / sensitivity
        normalized_slope = np.clip(normalized_slope, -1.0, 1.0)
        
        if scaling_method == 'linear':
            if normalized_slope >= 0:
                long_exit = base_long_exit + normalized_slope * (max_long_exit_uptrend - base_long_exit)
                short_exit = base_short_exit + normalized_slope * (max_short_exit_uptrend - base_short_exit)
            else:
                long_exit = base_long_exit + abs(normalized_slope) * (max_long_exit_downtrend - base_long_exit)
                short_exit = base_short_exit + abs(normalized_slope) * (max_short_exit_downtrend - base_short_exit)
        
        elif scaling_method == 'exponential':
            exp_factor = np.exp(abs(normalized_slope)) - 1
            if normalized_slope >= 0:
                long_exit = base_long_exit + exp_factor * (max_long_exit_uptrend - base_long_exit) / (np.e - 1)
                short_exit = base_short_exit + exp_factor * (max_short_exit_uptrend - base_short_exit) / (np.e - 1)
            else:
                long_exit = base_long_exit + exp_factor * (max_long_exit_downtrend - base_long_exit) / (np.e - 1)
                short_exit = base_short_exit + exp_factor * (max_short_exit_downtrend - base_short_exit) / (np.e - 1)
        
        elif scaling_method == 'logarithmic':
            log_factor = np.log1p(abs(normalized_slope)) / np.log(2)
            if normalized_slope >= 0:
                long_exit = base_long_exit + log_factor * (max_long_exit_uptrend - base_long_exit)
                short_exit = base_short_exit + log_factor * (max_short_exit_uptrend - base_short_exit)
            else:
                long_exit = base_long_exit + log_factor * (max_long_exit_downtrend - base_long_exit)
                short_exit = base_short_exit + log_factor * (max_short_exit_downtrend - base_short_exit)
        
        else:
            long_exit = base_long_exit
            short_exit = base_short_exit
        
        return long_exit, short_exit
    
    def calculate_slope_based_asymmetric_offset(self, slope: float = None) -> float:
        slope_offset_config = self.base_params.get('slope_asymmetric_offset', {})
        
        if not slope_offset_config.get('enabled', False):
            return 0.0
        
        slope_to_use = slope if slope is not None else self.current_slope
        slope_config = self.adaptive_factors.get('slope', {})
        sensitivity = slope_config.get('sensitivity', 0.04)
        
        base_offset = slope_offset_config.get('base_offset', 0.0)
        max_offset_uptrend = slope_offset_config.get('max_offset_uptrend', 1.8)
        max_offset_downtrend = slope_offset_config.get('max_offset_downtrend', -1.8)
        scaling_method = slope_offset_config.get('scaling_method', 'linear')
        
        normalized_slope = slope_to_use / sensitivity
        normalized_slope = np.clip(normalized_slope, -1.0, 1.0)
        
        # Calculate offset based on scaling method
        if scaling_method == 'linear':
            if normalized_slope >= 0:
                offset = base_offset + normalized_slope * (max_offset_uptrend - base_offset)
            else:
                offset = base_offset + abs(normalized_slope) * (max_offset_downtrend - base_offset)
        
        elif scaling_method == 'exponential':
            exp_factor = np.exp(abs(normalized_slope)) - 1
            if normalized_slope >= 0:
                offset = base_offset + exp_factor * (max_offset_uptrend - base_offset) / (np.e - 1)
            else:
                offset = base_offset + exp_factor * (max_offset_downtrend - base_offset) / (np.e - 1)
        
        elif scaling_method == 'logarithmic':
            log_factor = np.log1p(abs(normalized_slope)) / np.log(2)
            if normalized_slope >= 0:
                offset = base_offset + log_factor * (max_offset_uptrend - base_offset)
            else:
                offset = base_offset + log_factor * (max_offset_downtrend - base_offset)
        
        else:
            offset = base_offset
        
        return offset
    
    def calculate_atr_factor(self) -> float:
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return 1.0
            
        atr_config = self.adaptive_factors['atr']
        
        if self.atr_calculator is None or len(self.atr_calculator.atr_history) < 20:
            return 1.0
        
        if self.atr_monitor and len(self.atr_monitor.values) >= 200:
            current_atr = self.atr_calculator.current_atr
            normalized_atr = self._calculate_percentile_based_factor(
                current_atr, self.atr_monitor, is_absolute=False
            )
            scale_factor = atr_config['min'] + normalized_atr * (atr_config['max'] - atr_config['min'])
            return scale_factor
        
        return 1.0
    
    def get_adaptive_exit_thresholds(self, entry_combined_factor: float = None, slope: float = None) -> tuple:
        slope_exit_config = self.base_params.get('slope_exit_scaling', {})
        
        if slope_exit_config.get('enabled', False):
            return self.calculate_slope_based_exit_thresholds(slope)
        
        adaptive_exit_config = self.base_params.get('adaptive_exit', {})
        
        if not adaptive_exit_config.get('enabled', False):
            long_exit = self.base_params.get('kalman_zscore_exit_long', 5.0)
            short_exit = self.base_params.get('kalman_zscore_exit_short', -5.0)
            return long_exit, short_exit
        
        extension_threshold = adaptive_exit_config.get('extension_threshold', 1.3)
        long_base = adaptive_exit_config.get('long_base_exit', -0.01)
        long_max = adaptive_exit_config.get('long_max_extension', 1.0)
        short_base = adaptive_exit_config.get('short_base_exit', -0.01)
        short_max = adaptive_exit_config.get('short_max_extension', -1.0)
        
        if entry_combined_factor is None or entry_combined_factor < extension_threshold:
            return long_base, short_base
        
        extension_factor = min((entry_combined_factor - 1.0) / (extension_threshold - 1.0), 1.0)
        long_exit = long_base + extension_factor * (long_max - long_base)
        short_exit = short_base + extension_factor * (short_max - short_base)
        
        return long_exit, short_exit
    
    def get_adaptive_parameters(self, slope: float = None) -> tuple:
        slope_to_use = slope if slope is not None else self.current_slope
        
        slope_factor = self.calculate_slope_factor(slope_to_use)
        atr_factor = self.calculate_atr_factor()
        
        # Use robust combination instead of simple multiplication
        combined_factor = self._robust_factor_combination(slope_factor, atr_factor)
        
        adaptive_params = {}
        
        elastic_base = self.base_params['elastic_entry']
        adaptive_params['elastic_entry'] = {
            'zscore_long_threshold': elastic_base['zscore_long_threshold'] * combined_factor,
            'zscore_short_threshold': elastic_base['zscore_short_threshold'] * combined_factor,
            'recovery_delta': elastic_base['recovery_delta'] * combined_factor,
            'long_min_distance_from_kalman': elastic_base['long_min_distance_from_kalman'] * combined_factor,
            'short_min_distance_from_kalman': elastic_base['short_min_distance_from_kalman'] * combined_factor,
            'additional_zscore_min_gain': elastic_base['additional_zscore_min_gain'] * combined_factor,
            'recovery_delta_reentry': elastic_base['recovery_delta_reentry'] * combined_factor,
            'allow_multiple_recoveries': elastic_base['allow_multiple_recoveries'],
            'recovery_cooldown_bars': elastic_base['recovery_cooldown_bars'],
            'stacking_bar_cooldown': elastic_base['stacking_bar_cooldown'],
            'alllow_stacking': elastic_base.get('alllow_stacking', True),
            'max_long_stacked_positions': elastic_base.get('max_long_stacked_positions', 3),
            'max_short_stacked_positions': elastic_base.get('max_short_stacked_positions', 3),
        }
        
        adaptive_exit_config = self.base_params.get('adaptive_exit', {})
        if adaptive_exit_config.get('enabled', False):
            adaptive_params['adaptive_exit'] = adaptive_exit_config
        
        long_exit, short_exit = self.get_adaptive_exit_thresholds(combined_factor, slope_to_use)
        adaptive_params['kalman_zscore_exit_long'] = long_exit
        adaptive_params['kalman_zscore_exit_short'] = short_exit
        
        adaptive_params['long_risk_factor'], adaptive_params['short_risk_factor'] = self.calculate_slope_based_risk_factors(slope_to_use)
        
        vwap_base = self.base_params.get('vwap', {})
        anchor_method_from_config = vwap_base.get('anchor_method', 'kalman_cross')
        
        adaptive_params['vwap'] = {
            'anchor_method': anchor_method_from_config,
            'vwap_require_trade_for_reset': vwap_base.get('vwap_require_trade_for_reset', True),
            'vwap_min_bars_for_zscore': vwap_base.get('vwap_min_bars_for_zscore', 20),
            'vwap_reset_grace_period': vwap_base.get('vwap_reset_grace_period', 40),
            'rolling_window_bars': vwap_base.get('rolling_window_bars', 288),
        }
        
        # LTF Kalman parameters (fast, responsive)
        adaptive_params['ltf_kalman_process_var'] = self.base_params['ltf_kalman_process_var']
        adaptive_params['ltf_kalman_measurement_var'] = self.base_params['ltf_kalman_measurement_var']
        adaptive_params['ltf_kalman_zscore_window'] = self.base_params['ltf_kalman_zscore_window']
        
        # HTF Kalman parameters (slow, stable)
        adaptive_params['htf_kalman_process_var'] = self.base_params['htf_kalman_process_var']
        adaptive_params['htf_kalman_measurement_var'] = self.base_params['htf_kalman_measurement_var']
        adaptive_params['htf_kalman_zscore_window'] = self.base_params['htf_kalman_zscore_window']
        
        return adaptive_params, slope_factor, atr_factor, combined_factor
    
    def get_trend_factor(self, slope: float = None) -> float:
        slope_to_use = slope if slope is not None else self.current_slope
        
        if slope_to_use is None:
            return 0.0
            
        slope_config = self.adaptive_factors.get('slope', {})
        sensitivity = slope_config.get('sensitivity', 0.1)  # Angepasst an echte Slope-Range
        
        # Trend-Faktor zwischen -1 und +1, basierend auf echten Slope-Werten
        normalized_slope = slope_to_use / sensitivity
        
        trend_factor = max(-1.0, min(1.0, normalized_slope))
        
        return trend_factor
    
    def get_volatility_factor(self) -> float:
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return 0.5
        
        if self.atr_calculator is None or len(self.atr_calculator.atr_history) < 20:
            return 0.5
        
        atr_history = list(self.atr_calculator.atr_history)
        atr_mean = np.mean(atr_history)
        atr_std = np.std(atr_history)
        
        if atr_std == 0:
            return 0.5
        
        current_atr = self.atr_calculator.current_atr
        atr_zscore = (current_atr - atr_mean) / atr_std
        
        volatility_strength = 1 / (1 + np.exp(-abs(atr_zscore)))
        
        return volatility_strength
    
    def get_linear_adjustment(self, base_value: float, trend_sensitivity: float = 0.3, vol_sensitivity: float = 0.4) -> float:
        trend_factor = self.get_trend_factor()
        volatility_factor = self.get_volatility_factor()
        
        trend_adjustment = base_value * trend_factor * trend_sensitivity
        
        vol_adjustment = base_value * (volatility_factor - 0.5) * vol_sensitivity
        
        return base_value + trend_adjustment + vol_adjustment
    
    def get_asymmetric_offset(self, base_mean: float = None) -> float:
        # Check if slope-based asymmetric offset is enabled
        slope_offset_config = self.base_params.get('slope_asymmetric_offset', {})
        if slope_offset_config.get('enabled', False):
            return self.calculate_slope_based_asymmetric_offset()
        
        # Fallback to old method if slope-based offset is disabled
        offset_config = self.adaptive_factors.get('asymmetric_offset', {})
        if not offset_config.get('enabled', False):
            return 0.0
        
        trend_factor = self.get_trend_factor()
        trend_strength = abs(trend_factor)
        
        max_offset_zscore = offset_config.get('max_offset_pct', 0.5)
        min_strength = offset_config.get('min_trend_strength', 0.1)
        strength_threshold = offset_config.get('strength_threshold', 0.5)
        
        if trend_strength < min_strength:
            return 0.0
        
        # Z-Score Offset berechnen
        if trend_strength >= strength_threshold:
            zscore_offset_magnitude = max_offset_zscore
        else:
            normalized_strength = (trend_strength - min_strength) / (strength_threshold - min_strength)
            zscore_offset_magnitude = max_offset_zscore * normalized_strength
        
        # Finaler Z-Score Offset: Trend-Richtung * Magnitude
        zscore_offset = np.sign(trend_factor) * zscore_offset_magnitude
        
        return zscore_offset
    
    def get_debug_info(self) -> dict:
        debug_info = {
            'kalman_enabled': self.adaptive_factors.get('kalman', {}).get('enabled', False),
            'atr_enabled': self.adaptive_factors.get('atr', {}).get('enabled', False),
            'slope_enabled': self.adaptive_factors.get('slope', {}).get('enabled', False),
            'slope_monitor_enabled': self.adaptive_factors.get('distribution_monitor', {}).get('slope_distribution', {}).get('enabled', False),
            'atr_monitor_enabled': self.adaptive_factors.get('distribution_monitor', {}).get('atr_distribution', {}).get('enabled', False),
            'current_atr_percentile': self.current_atr_percentile,
            'current_slope': self.current_slope,
            'current_kalman_mean': self.current_kalman_mean,
            'kalman_initialized': self.kalman.initialized if self.kalman else False,
        }
        
        if self.atr_calculator:
            debug_info['atr_history_length'] = len(self.atr_calculator.atr_history)
            debug_info['tr_history_length'] = len(self.atr_calculator.tr_history)
            debug_info['current_atr'] = self.atr_calculator.current_atr
        
        if self.slope_monitor is not None:
            debug_info['slope_monitor_samples'] = self.slope_monitor.total_count
        
        if self.atr_monitor is not None:
            debug_info['atr_monitor_samples'] = self.atr_monitor.total_count
            
        return debug_info
    
    def print_slope_distribution(self):
        if self.slope_monitor is not None:
            self.slope_monitor.print_distribution()
        else:
            print("Slope monitor is disabled.")
    
    def print_atr_distribution(self):
        if self.atr_monitor is not None:
            self.atr_monitor.print_distribution()
        else:
            print("ATR monitor is disabled.")
    
    def get_current_scaling_info(self) -> dict:
        info = {
            'slope_scaling': 'waiting_for_data',
            'atr_scaling': 'waiting_for_data',
            'slope_samples': 0,
            'atr_samples': 0,
            'percentile_scaling_active': False
        }
        
        if self.slope_monitor and len(self.slope_monitor.values) >= 200:
            info['slope_scaling'] = 'dynamic_percentile'
            info['slope_samples'] = len(self.slope_monitor.values)
            
            percentiles = self.slope_monitor._calculate_weighted_percentiles([5, 95])
            if percentiles[5] is not None and percentiles[95] is not None:
                info['slope_p5'] = abs(percentiles[5])
                info['slope_p95'] = abs(percentiles[95])
                info['slope_range'] = abs(percentiles[95]) - abs(percentiles[5])
        
        if self.atr_monitor and len(self.atr_monitor.values) >= 200:
            info['atr_scaling'] = 'dynamic_percentile'
            info['atr_samples'] = len(self.atr_monitor.values)
            
            percentiles = self.atr_monitor._calculate_weighted_percentiles([5, 95])
            if percentiles[5] is not None and percentiles[95] is not None:
                info['atr_p5'] = percentiles[5]
                info['atr_p95'] = percentiles[95]
                info['atr_range'] = percentiles[95] - percentiles[5]
        
        info['percentile_scaling_active'] = (
            info['slope_scaling'] == 'dynamic_percentile' or 
            info['atr_scaling'] == 'dynamic_percentile'
        )
        
        return info
    
    def print_scaling_status(self):
        info = self.get_current_scaling_info()
        
        print(f"\n{'='*60}")
        print("ADAPTIVE SCALING STATUS")
        print(f"{'='*60}")
        
        print(f"SLOPE SCALING: {info['slope_scaling'].upper()}")
        if info['slope_scaling'] == 'dynamic_percentile':
            print(f"  Samples: {info['slope_samples']}")
            if 'slope_p5' in info:
                print(f"  5th Percentile (abs):  {info['slope_p5']:.6f}")
                print(f"  95th Percentile (abs): {info['slope_p95']:.6f}")
                print(f"  Dynamic Range:         {info['slope_range']:.6f}")
            print(f"  Current Slope: {self.current_slope:.6f} (abs: {abs(self.current_slope):.6f})")
            
            if hasattr(self, 'slope_monitor') and self.slope_monitor:
                current_factor = self._calculate_percentile_based_factor(
                    self.current_slope, self.slope_monitor, is_absolute=True
                )
                print(f"  Normalized (0-1): {current_factor:.3f}")
        else:
            print(f"  Waiting for 200+ samples (current: {info['slope_samples']})")
            print(f"  Current slope: {self.current_slope:.6f}")
        
        print()
        
        print(f"ATR SCALING: {info['atr_scaling'].upper()}")
        if info['atr_scaling'] == 'dynamic_percentile':
            print(f"  Samples: {info['atr_samples']}")
            if 'atr_p5' in info:
                print(f"  5th Percentile:  {info['atr_p5']:.6f}")
                print(f"  95th Percentile: {info['atr_p95']:.6f}")
                print(f"  Dynamic Range:   {info['atr_range']:.6f}")
            if self.atr_calculator and self.atr_calculator.current_atr:
                print(f"  Current ATR: {self.atr_calculator.current_atr:.6f}")
                
                if hasattr(self, 'atr_monitor') and self.atr_monitor:
                    current_factor = self._calculate_percentile_based_factor(
                        self.atr_calculator.current_atr, self.atr_monitor, is_absolute=False
                    )
                    print(f"  Normalized (0-1): {current_factor:.3f}")
        else:
            print(f"  Waiting for 200+ samples (current: {info['atr_samples']})")
            if self.atr_calculator and self.atr_calculator.current_atr:
                print(f"  Current ATR: {self.atr_calculator.current_atr:.6f}")
        
        print(f"\nPercentile Scaling Active: {info['percentile_scaling_active']}")
        
        if self.current_slope is not None:
            slope_factor = self.calculate_slope_factor(self.current_slope)
            atr_factor = self.calculate_atr_factor()
            combined = self._robust_factor_combination(slope_factor, atr_factor)
            
            print("\nCURRENT FACTORS:")
            print(f"  Slope Factor:    {slope_factor:.3f}")
            print(f"  ATR Factor:      {atr_factor:.3f}")
            print(f"  Combined Factor: {combined:.3f}")
        
        print(f"{'='*60}\n")
    
    def log_trade_state(self, trade_type: str, price: float, zscore: float, entry_reason: str, 
                       stack_info: str, regime: int, adaptive_params: dict, 
                       long_positions: int, short_positions: int, allow_stacking: bool):
        
        # Get the actual calculated factors (same as used in strategy)
        _, slope_factor, atr_factor, combined_factor = self.get_adaptive_parameters()
        
        # Create slim log message matching the adaptive factors format
        message = f"{trade_type.upper()} ${price:.2f} | ZScore: {zscore:.3f} | Adaptive factors: slope={slope_factor:.3f}, atr={atr_factor:.3f}, combined={combined_factor:.3f}"
        
        # Note: LogColor.MAGENTA is typically purple in most terminals
        # This will be called from strategy context, so we'll return the message
        # and let the strategy log it with proper color
        return message
