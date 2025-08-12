import numpy as np
from collections import deque
from tools.indicators.kalman_filter_2D import KalmanFilterRegression
from tools.help_funcs.slope_distrubition_monitor import SlopeDistributionMonitor


class AdaptiveParameterManager:
    def __init__(self, base_params: dict, adaptive_factors: dict):
        self.base_params = base_params
        self.adaptive_factors = adaptive_factors
        
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
        
        if self.adaptive_factors.get('atr', {}).get('enabled', False):
            atr_config = self.adaptive_factors['atr']
            self.atr_history = deque(maxlen=atr_config['window'])
            self.current_atr_percentile = 0.5
            self.atr_historical = deque(maxlen=100)
        else:
            self.atr_history = None
            self.current_atr_percentile = 0.5
            self.atr_historical = None
        
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
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return
            
        if prev_close is not None:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        else:
            tr = high - low
            
        self.atr_history.append(tr)
        
        if len(self.atr_history) >= self.adaptive_factors['atr']['window']:
            current_atr = np.mean(self.atr_history)
            
            if self.kalman is not None and self.kalman.initialized:
                smoothed_atr = current_atr
                for _ in range(5):
                    _, _ = self.kalman.update(smoothed_atr)
                    smoothed_atr = self.kalman.current_mean if hasattr(self.kalman, 'current_mean') else current_atr
            else:
                smoothed_atr = current_atr
            
            self.atr_historical.append(smoothed_atr)
            
            if len(self.atr_historical) > 10:
                atr_values = list(self.atr_historical)
                atr_values.sort()
                
                rank = 0
                for val in atr_values:
                    if smoothed_atr > val:
                        rank += 1
                
                self.current_atr_percentile = rank / len(atr_values)
                self.current_atr_percentile = max(0.05, min(0.95, self.current_atr_percentile))
    
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
        
        combined_factor = slope_factor * atr_factor
        
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
        
        normalized_slope = slope_to_use / (sensitivity / 100)
        
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
            'atr_history_length': len(self.atr_history) if self.atr_history else 0,
            'atr_historical_length': len(self.atr_historical) if self.atr_historical else 0,
            'kalman_initialized': self.kalman.initialized if self.kalman else False,
        }
        
        if self.slope_monitor is not None:
            debug_info['slope_monitor_samples'] = self.slope_monitor.total_count
            
        return debug_info
    
    def print_slope_distribution(self):
        if self.slope_monitor is not None:
            self.slope_monitor.print_distribution()
        else:
            print("Slope monitor is disabled.")
