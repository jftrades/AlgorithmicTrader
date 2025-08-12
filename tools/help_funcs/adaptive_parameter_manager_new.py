import numpy as np
from collections import deque
from tools.indicators.kalman_filter_2D import KalmanFilterRegression
from tools.help_funcs.slope_distrubition_monitor import SlopeDistributionMonitor


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
    def __init__(self, base_params: dict, adaptive_factors: dict):
        self.base_params = base_params
        self.adaptive_factors = adaptive_factors
        
        # Kalman Filter for slope calculation
        if self.adaptive_factors.get('kalman', {}).get('enabled', False):
            kalman_config = self.adaptive_factors['kalman']
            self.kalman = KalmanFilterRegression(
                process_var=kalman_config.get('process_var', 0.000000001),
                measurement_var=kalman_config.get('measurement_var', 0.001),
                window=10
            )
            self.current_slope = 0.0
            self.current_kalman_mean = None
        else:
            self.kalman = None
            self.current_slope = 0.0
            self.current_kalman_mean = None
        
        # Robust ATR Calculator
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
        
        # Slope Distribution Monitor
        if self.adaptive_factors.get('slope_monitor', {}).get('enabled', False):
            monitor_config = self.adaptive_factors['slope_monitor']
            self.slope_monitor = SlopeDistributionMonitor(
                bin_size=monitor_config.get('bin_size', 0.001)
            )
        else:
            self.slope_monitor = None
    
    def update_slope(self, price: float):
        if self.kalman is not None:
            mean, slope = self.kalman.update(price)
            if mean is not None:
                self.current_kalman_mean = mean
            if slope is not None:
                self.current_slope = slope
                if self.slope_monitor is not None:
                    self.slope_monitor.add_slope(slope)
            return mean, slope
        return None, None
    
    def update_market_data(self, price: float, high: float, low: float, prev_close: float = None):
        self.update_slope(price)
        self.update_atr(high, low, prev_close)
    
    def update_atr(self, high: float, low: float, prev_close: float = None):
        """Update ATR with robust calculation"""
        if self.atr_calculator is not None:
            current_atr, percentile = self.atr_calculator.update(high, low, prev_close)
            self.current_atr_percentile = percentile
            return current_atr, percentile
        return None, self.current_atr_percentile
    
    def _robust_factor_combination(self, slope_factor: float, atr_factor: float) -> float:
        """Robust combination of factors with log-space calculation and clipping"""
        # Configuration for robust combination
        combination_config = self.adaptive_factors.get('combination', {})
        use_log_space = combination_config.get('use_log_space', True)
        min_combined = combination_config.get('min_combined_factor', 0.3)
        max_combined = combination_config.get('max_combined_factor', 3.0)
        
        if use_log_space:
            # Log-space combination for better handling of extreme values
            log_slope = np.log(max(0.01, slope_factor))
            log_atr = np.log(max(0.01, atr_factor))
            log_combined = log_slope + log_atr
            combined_factor = np.exp(log_combined)
        else:
            combined_factor = slope_factor * atr_factor
        
        # Robust clipping to prevent extreme leverage
        combined_factor = np.clip(combined_factor, min_combined, max_combined)
        
        return combined_factor
    
    def calculate_slope_factor(self, slope: float) -> float:
        if not self.adaptive_factors.get('slope', {}).get('enabled', False):
            return 1.0
            
        slope_config = self.adaptive_factors['slope']
        sensitivity = slope_config['sensitivity']
        
        normalized_slope = (slope + sensitivity) / (2 * sensitivity)
        normalized_slope = max(0.0, min(1.0, normalized_slope))
        
        scale_factor = slope_config['min'] + normalized_slope * (slope_config['max'] - slope_config['min'])
        return scale_factor
    
    def calculate_atr_factor(self) -> float:
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return 1.0
            
        atr_config = self.adaptive_factors['atr']
        
        scale_factor = atr_config['min'] + self.current_atr_percentile * (atr_config['max'] - atr_config['min'])
        return scale_factor
    
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
            'base_zscore_short_threshold': elastic_base['base_zscore_short_threshold'] * combined_factor,
            'recovery_delta': elastic_base['recovery_delta'] * combined_factor,
            'additional_zscore_min_gain': elastic_base['additional_zscore_min_gain'] * combined_factor,
            'recovery_delta_reentry': elastic_base['recovery_delta_reentry'] * combined_factor,
            'allow_multiple_recoveries': elastic_base['allow_multiple_recoveries'],
            'recovery_cooldown_bars': elastic_base['recovery_cooldown_bars'],
            'stacking_bar_cooldown': elastic_base['stacking_bar_cooldown'],
            'alllow_stacking': elastic_base.get('alllow_stacking', True),
            'max_stacked_positions': elastic_base.get('max_stacked_positions', 3),
        }
        
        adaptive_params['kalman_exit_long'] = self.base_params['kalman_exit_long'] * combined_factor
        adaptive_params['kalman_exit_short'] = self.base_params['kalman_exit_short'] * combined_factor
        adaptive_params['long_risk_factor'] = self.base_params['long_risk_factor'] * combined_factor
        adaptive_params['short_risk_factor'] = self.base_params['short_risk_factor'] * combined_factor
        
        vwap_base = self.base_params.get('vwap', {})
        adaptive_params['vwap'] = {
            'vwap_anchor_on_kalman_cross': vwap_base.get('vwap_anchor_on_kalman_cross', True),
            'vwap_require_trade_for_reset': vwap_base.get('vwap_require_trade_for_reset', True),
            'vwap_min_bars_for_zscore': vwap_base.get('vwap_min_bars_for_zscore', 15),
            'vwap_reset_grace_period': vwap_base.get('vwap_reset_grace_period', 40),
        }
        
        adaptive_params['kalman_exit_process_var'] = self.base_params['kalman_exit_process_var']
        adaptive_params['kalman_exit_measurement_var'] = self.base_params['kalman_exit_measurement_var']
        adaptive_params['kalman_exit_zscore_window'] = self.base_params['kalman_exit_zscore_window']
        
        return adaptive_params, slope_factor, atr_factor, combined_factor
    
    def get_trend_factor(self, slope: float = None) -> float:
        slope_to_use = slope if slope is not None else self.current_slope
        
        if slope_to_use is None:
            return 0.0
            
        slope_config = self.adaptive_factors.get('slope', {})
        sensitivity = slope_config.get('sensitivity', 10)
        
        normalized_slope = slope_to_use / sensitivity
        
        trend_factor = max(-1.0, min(1.0, normalized_slope))
        
        return trend_factor
    
    def get_volatility_factor(self) -> float:
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return 0.5
            
        return self.current_atr_percentile
    
    def get_linear_adjustment(self, base_value: float, trend_sensitivity: float = 0.3, vol_sensitivity: float = 0.4) -> float:
        trend_factor = self.get_trend_factor()
        volatility_factor = self.get_volatility_factor()
        
        trend_adjustment = base_value * trend_factor * trend_sensitivity
        
        vol_adjustment = base_value * (volatility_factor - 0.5) * vol_sensitivity
        
        return base_value + trend_adjustment + vol_adjustment
    
    def get_debug_info(self) -> dict:
        debug_info = {
            'kalman_enabled': self.adaptive_factors.get('kalman', {}).get('enabled', False),
            'atr_enabled': self.adaptive_factors.get('atr', {}).get('enabled', False),
            'slope_enabled': self.adaptive_factors.get('slope', {}).get('enabled', False),
            'slope_monitor_enabled': self.adaptive_factors.get('slope_monitor', {}).get('enabled', False),
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
            
        return debug_info
    
    def print_slope_distribution(self):
        if self.slope_monitor is not None:
            self.slope_monitor.print_distribution()
        else:
            print("Slope monitor is disabled.")
    
    def log_trade_state(self, trade_type: str, price: float, zscore: float, entry_reason: str, 
                       stack_info: str, regime: int, adaptive_params: dict, 
                       long_positions: int, short_positions: int, allow_stacking: bool):
        """Comprehensive trade logging with all relevant parameters"""
        
        # Get current factors
        trend_factor = self.get_trend_factor()
        vol_factor = self.get_volatility_factor()
        _, slope_factor, atr_factor, combined_factor = self.get_adaptive_parameters()
        
        # Get thresholds from adaptive params
        elastic_base = adaptive_params['elastic_entry']
        long_threshold = elastic_base['zscore_long_threshold']
        short_threshold = elastic_base['base_zscore_short_threshold']
        recovery_delta = elastic_base['recovery_delta']
        
        print(f"\n=== {trade_type.upper()} TRADE: {stack_info} ===")
        print(f"Price: ${price:.2f} | ZScore: {zscore:.3f} | Reason: {entry_reason} | VIX Regime: {regime}")
        print(f"Slope: {self.current_slope:.6f} | Trend Factor: {trend_factor:.3f} | Vol Factor: {vol_factor:.3f}")
        print(f"Factors - Slope: {slope_factor:.3f} | ATR: {atr_factor:.3f} | Combined: {combined_factor:.3f}")
        print(f"Thresholds - Long: {long_threshold:.2f} | Short: {short_threshold:.2f} | Recovery: {recovery_delta:.2f}")
        print(f"Position State - Long: {long_positions} | Short: {short_positions} | Stacking: {allow_stacking}")
        
        if self.slope_monitor and self.slope_monitor.slope_values:
            recent = self.slope_monitor.slope_values[-3:]
            print(f"Recent Slopes: {[f'{s:.4f}' for s in recent]}")
        
        # Show ATR info if available
        if self.atr_calculator:
            print(f"ATR Info - Current: {self.atr_calculator.current_atr:.4f} | Percentile: {self.current_atr_percentile:.3f}")
        
        print("="*70)
