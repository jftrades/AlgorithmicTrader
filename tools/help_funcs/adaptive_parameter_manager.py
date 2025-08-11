import numpy as np
from collections import deque
from tools.indicators.kalman_filter_2D import KalmanFilter1D, KalmanFilterRegression


class AdaptiveParameterManager:
    def __init__(self, base_params: dict, adaptive_factors: dict):
        self.base_params = base_params
        self.adaptive_factors = adaptive_factors
        
        # Initialize ATR tracking
        if self.adaptive_factors.get('atr', {}).get('enabled', False):
            atr_config = self.adaptive_factors['atr']
            self.atr_kalman = KalmanFilter1D(
                process_var=atr_config['smoothing_kalman_process_var'],
                measurement_var=atr_config['smoothing_kalman_measurement_var'],
                window=atr_config['window']
            )
            self.atr_history = deque(maxlen=atr_config['window'])
            self.current_atr_percentile = 0.5
            self.atr_historical = deque(maxlen=100)  # Longer history for percentile calculation
        else:
            self.atr_kalman = None
            self.atr_history = None
            self.current_atr_percentile = 0.5
            self.atr_historical = None
            
        if self.adaptive_factors.get('slope', {}).get('enabled', False):
            slope_config = self.adaptive_factors['slope']
            self.slope_kalman = KalmanFilterRegression(
                process_var=slope_config.get('kalman_process_var', 0.000000001),  # Legacy default
                measurement_var=slope_config.get('kalman_measurement_var', 0.001),  # Legacy default
                window=slope_config.get('kalman_window', 10)  # Legacy default
            )
            self.current_slope = 0.0
            self.current_kalman_mean = None  # Keep track of mean too for compatibility
        else:
            self.slope_kalman = None
            self.current_slope = 0.0
            self.current_kalman_mean = None
    
    def update_slope(self, price: float):
        if self.slope_kalman is not None:
            mean, slope = self.slope_kalman.update(price)
            if mean is not None:
                self.current_kalman_mean = mean
            if slope is not None:
                self.current_slope = slope
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
            
            # Smooth ATR with Kalman
            if self.atr_kalman.is_initialized():
                smoothed_atr = self.atr_kalman.update(current_atr)
            else:
                smoothed_atr = self.atr_kalman.update(current_atr)
                if smoothed_atr is None:
                    return
            
            # Store for historical percentile calculation
            self.atr_historical.append(smoothed_atr)
            
            # Calculate percentile based on historical data
            if len(self.atr_historical) > 10:
                atr_values = list(self.atr_historical)
                atr_values.sort()
                
                # Find percentile rank of current smoothed ATR
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
        
        # Normalize slope to 0-1 range based on sensitivity
        # Map slope from [-sensitivity, +sensitivity] to [0, 1]
        normalized_slope = (slope + sensitivity) / (2 * sensitivity)
        normalized_slope = max(0.0, min(1.0, normalized_slope))
        
        # Scale between min and max
        scale_factor = slope_config['min'] + normalized_slope * (slope_config['max'] - slope_config['min'])
        return scale_factor
    
    def calculate_atr_factor(self) -> float:
        """Calculate scaling factor based on ATR percentile"""
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return 1.0
            
        atr_config = self.adaptive_factors['atr']
        
        # Scale ATR percentile between min and max
        scale_factor = atr_config['min'] + self.current_atr_percentile * (atr_config['max'] - atr_config['min'])
        return scale_factor
    
    def get_adaptive_parameters(self, slope: float = None) -> tuple:
        """Get scaled parameters based on current market conditions"""
        # Use internal slope if none provided
        slope_to_use = slope if slope is not None else self.current_slope
        
        slope_factor = self.calculate_slope_factor(slope_to_use)
        atr_factor = self.calculate_atr_factor()
        
        # Combine factors multiplicatively
        combined_factor = slope_factor * atr_factor
        
        # Scale base parameters
        adaptive_params = {}
        
        # Scale elastic entry parameters
        elastic_base = self.base_params['elastic_entry']
        adaptive_params['elastic_entry'] = {
            'zscore_long_threshold': elastic_base['zscore_long_threshold'] * combined_factor,
            'base_zscore_short_threshold': elastic_base['base_zscore_short_threshold'] * combined_factor,
            'recovery_delta': elastic_base['recovery_delta'] * combined_factor,
            'additional_zscore_min_gain': elastic_base['additional_zscore_min_gain'] * combined_factor,
            'recovery_delta_reentry': elastic_base['recovery_delta_reentry'] * combined_factor,
            # Keep non-scalable parameters as-is
            'allow_multiple_recoveries': elastic_base['allow_multiple_recoveries'],
            'recovery_cooldown_bars': elastic_base['recovery_cooldown_bars'],
            'stacking_bar_cooldown': elastic_base['stacking_bar_cooldown'],
            'alllow_stacking': elastic_base.get('alllow_stacking', True),
            'max_stacked_positions': elastic_base.get('max_stacked_positions', 3),
        }
        
        # Scale exit parameters
        adaptive_params['kalman_exit_long'] = self.base_params['kalman_exit_long'] * combined_factor
        adaptive_params['kalman_exit_short'] = self.base_params['kalman_exit_short'] * combined_factor
        
        # Scale risk factors
        adaptive_params['long_risk_factor'] = self.base_params['long_risk_factor'] * combined_factor
        adaptive_params['short_risk_factor'] = self.base_params['short_risk_factor'] * combined_factor
        
        # Scale VWAP parameters
        vwap_base = self.base_params.get('vwap', {})
        adaptive_params['vwap'] = {
            'vwap_anchor_on_kalman_cross': vwap_base.get('vwap_anchor_on_kalman_cross', True),
            'vwap_require_trade_for_reset': vwap_base.get('vwap_require_trade_for_reset', True),
            'vwap_min_bars_for_zscore': vwap_base.get('vwap_min_bars_for_zscore', 15),
            'vwap_reset_grace_period': vwap_base.get('vwap_reset_grace_period', 40),
        }
        
        # Scale exit Kalman parameters
        adaptive_params['kalman_exit_process_var'] = self.base_params['kalman_exit_process_var']
        adaptive_params['kalman_exit_measurement_var'] = self.base_params['kalman_exit_measurement_var']
        adaptive_params['kalman_exit_zscore_window'] = self.base_params['kalman_exit_zscore_window']
        
        return adaptive_params, slope_factor, atr_factor, combined_factor
    
    def get_trend_factor(self, slope: float = None) -> float:
        """Get a single trend factor from -1 to +1 based on slope direction and strength"""
        # Use internal slope if none provided
        slope_to_use = slope if slope is not None else self.current_slope
        
        if slope_to_use is None:
            return 0.0
            
        slope_config = self.adaptive_factors.get('slope', {})
        sensitivity = slope_config.get('sensitivity', 10)
        
        # Normalize slope to -1 to +1 range
        # Positive slope = trending up, negative slope = trending down
        normalized_slope = slope_to_use / (sensitivity / 100)  # Convert sensitivity to decimal
        
        # Clamp to reasonable range
        trend_factor = max(-1.0, min(1.0, normalized_slope))
        
        return trend_factor
    
    def get_volatility_factor(self) -> float:
        """Get volatility factor from 0 to 1 based on ATR percentile"""
        if not self.adaptive_factors.get('atr', {}).get('enabled', False):
            return 0.5  # Neutral volatility when ATR disabled
            
        # ATR percentile already ranges from 0 to 1
        return self.current_atr_percentile
    
    def get_market_state(self, slope: float = None) -> dict:
        """Get current market state with clear factors for linear parameter adjustment"""
        # Use internal slope if none provided
        slope_to_use = slope if slope is not None else self.current_slope
        
        trend_factor = self.get_trend_factor(slope_to_use)
        volatility_factor = self.get_volatility_factor()
        
        # Determine market characteristics
        is_trending_up = trend_factor > 0.2
        is_trending_down = trend_factor < -0.2
        is_sideways = abs(trend_factor) <= 0.2
        is_high_volatility = volatility_factor > 0.7
        is_low_volatility = volatility_factor < 0.3
        
        return {
            'trend_factor': trend_factor,           # -1 (strong down) to +1 (strong up)
            'volatility_factor': volatility_factor, # 0 (low vol) to 1 (high vol)
            'is_trending_up': is_trending_up,
            'is_trending_down': is_trending_down,
            'is_sideways': is_sideways,
            'is_high_volatility': is_high_volatility,
            'is_low_volatility': is_low_volatility,
            'trend_strength': abs(trend_factor),    # 0 to 1
            'raw_slope': slope_to_use
        }
    
    def should_trade_in_current_state(self, slope: float = None) -> bool:
        """Simple check if we should trade - can be customized"""
        # Use internal slope if none provided
        slope_to_use = slope if slope is not None else self.current_slope
        market_state = self.get_market_state(slope_to_use)
        
        # Trade unless trend is extremely strong (adjust threshold as needed)
        return market_state['trend_strength'] < 0.8
    
    def get_linear_adjustment(self, base_value: float, trend_factor: float, volatility_factor: float, 
                            trend_sensitivity: float = 0.5, vol_sensitivity: float = 0.3) -> float:
        """
        Linearly adjust a parameter based on trend and volatility
        
        Args:
            base_value: The base parameter value
            trend_factor: -1 to +1 (from get_trend_factor)
            volatility_factor: 0 to 1 (from get_volatility_factor)
            trend_sensitivity: How much trend affects the parameter (0-1)
            vol_sensitivity: How much volatility affects the parameter (0-1)
        
        Returns:
            Adjusted parameter value
        """
        # Trend adjustment: negative trend = tighter params, positive trend = looser params
        trend_adjustment = base_value * trend_factor * trend_sensitivity
        
        # Volatility adjustment: high vol = wider params, low vol = tighter params
        vol_adjustment = base_value * (volatility_factor - 0.5) * vol_sensitivity
        
        return base_value + trend_adjustment + vol_adjustment
    
    def get_debug_info(self) -> dict:
        """Get debug information about current adaptive state"""
        return {
            'atr_enabled': self.adaptive_factors.get('atr', {}).get('enabled', False),
            'slope_enabled': self.adaptive_factors.get('slope', {}).get('enabled', False),
            'current_atr_percentile': self.current_atr_percentile,
            'current_slope': self.current_slope,
            'atr_history_length': len(self.atr_history) if self.atr_history else 0,
            'atr_historical_length': len(self.atr_historical) if self.atr_historical else 0,
            'slope_kalman_initialized': self.slope_kalman.initialized if self.slope_kalman else False,
        }
