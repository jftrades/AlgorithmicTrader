from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from .base_indicator import BaseIndicator

class ChartBasedIndicator(BaseIndicator):
    """Chart-based indicators derived from price action and bar analysis.
    
    Includes: Volume indicators, volatility measures, price patterns, gaps, etc.
    """
    
    def __init__(self, indicator_type: str, **params):
        super().__init__(f"chart_{indicator_type}", "chart_based")
        self.indicator_type = indicator_type
        self.params = params
        
        # Define available chart-based indicators
        self.available_indicators = {
            'volume_sma': self._calculate_volume_sma,
            'volume_profile': self._calculate_volume_profile,
            'price_volatility': self._calculate_price_volatility,
            'daily_range': self._calculate_daily_range,
            'gap_analysis': self._calculate_gap_analysis,
            'candle_body_ratio': self._calculate_candle_body_ratio,
            'candle_wick_ratio': self._calculate_candle_wick_ratio,
            'price_momentum': self._calculate_price_momentum,
            'volume_momentum': self._calculate_volume_momentum,
            'price_acceleration': self._calculate_price_acceleration
        }
        
        if indicator_type not in self.available_indicators:
            raise ValueError(f"Unsupported chart indicator type: {indicator_type}")
    
    def calculate(self, price_data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Calculate the specified chart-based indicator."""
        self.validate_data(price_data)
        
        # Merge kwargs with instance params
        calc_params = {**self.params, **kwargs}
        
        # Calculate the indicator
        calculator = self.available_indicators[self.indicator_type]
        result = calculator(price_data, **calc_params)
        
        return self.standardize_output(result)
    
    def get_required_columns(self) -> List[str]:
        """Return required columns based on indicator type."""
        requirements = {
            'volume_sma': ['volume'],
            'volume_profile': ['volume', 'high', 'low', 'close'],
            'price_volatility': ['high', 'low', 'close'],
            'daily_range': ['high', 'low'],
            'gap_analysis': ['open', 'close'],
            'candle_body_ratio': ['open', 'close', 'high', 'low'],
            'candle_wick_ratio': ['open', 'close', 'high', 'low'],
            'price_momentum': ['close'],
            'volume_momentum': ['volume'],
            'price_acceleration': ['close']
        }
        return requirements.get(self.indicator_type, ['close'])
    
    def get_parameters(self) -> Dict:
        """Return default parameters for each indicator."""
        defaults = {
            'volume_sma': {'period': 20},
            'volume_profile': {'bins': 50},
            'price_volatility': {'period': 20},
            'daily_range': {'period': 10},
            'gap_analysis': {'threshold': 0.001},
            'candle_body_ratio': {},
            'candle_wick_ratio': {},
            'price_momentum': {'period': 10},
            'volume_momentum': {'period': 10},
            'price_acceleration': {'period': 5}
        }
        return defaults.get(self.indicator_type, {})
    
    def _calculate_volume_sma(self, data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Calculate Volume Simple Moving Average."""
        volume = data['volume']
        volume_sma = volume.rolling(window=period).mean()
        volume_ratio = volume / volume_sma
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': volume_ratio,
            'volume_sma': volume_sma
        })
        return result.dropna()
    
    def _calculate_volume_profile(self, data: pd.DataFrame, bins: int = 50) -> pd.DataFrame:
        """Calculate Volume Profile - volume at price levels."""
        high = data['high']
        low = data['low']
        close = data['close']
        volume = data['volume']
        
        # Create price bins
        price_min = low.min()
        price_max = high.max()
        price_bins = np.linspace(price_min, price_max, bins)
        
        # Calculate volume at each price level
        volume_profile = []
        for i, row in data.iterrows():
            # Distribute volume across price range for this candle
            candle_bins = np.linspace(row['low'], row['high'], max(2, int((row['high'] - row['low']) / (price_max - price_min) * bins)))
            vol_per_bin = row['volume'] / len(candle_bins) if len(candle_bins) > 0 else 0
            volume_profile.append(vol_per_bin)
        
        # Calculate volume-weighted average price position
        vwap_position = []
        for i, row in data.iterrows():
            typical_price = (row['high'] + row['low'] + row['close']) / 3
            position = (typical_price - price_min) / (price_max - price_min)
            vwap_position.append(position)
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': vwap_position  # Normalized VWAP position
        })
        return result
    
    def _calculate_price_volatility(self, data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Calculate Price Volatility (True Range based)."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        true_range = pd.DataFrame([tr1, tr2, tr3]).max()
        volatility = true_range.rolling(window=period).std()
        
        # Normalize by price
        normalized_volatility = volatility / close.rolling(window=period).mean()
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': normalized_volatility
        })
        return result.dropna()
    
    def _calculate_daily_range(self, data: pd.DataFrame, period: int = 10) -> pd.DataFrame:
        """Calculate Daily Range patterns."""
        high = data['high']
        low = data['low']
        
        daily_range = high - low
        avg_range = daily_range.rolling(window=period).mean()
        range_ratio = daily_range / avg_range
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': range_ratio
        })
        return result.dropna()
    
    def _calculate_gap_analysis(self, data: pd.DataFrame, threshold: float = 0.001) -> pd.DataFrame:
        """Calculate Gap Analysis (opening gaps)."""
        open_price = data['open']
        close_price = data['close']
        
        # Calculate gaps
        gaps = (open_price - close_price.shift()) / close_price.shift()
        gap_magnitude = abs(gaps)
        
        # Gap direction and significance
        gap_direction = np.sign(gaps)
        significant_gaps = (gap_magnitude > threshold).astype(int)
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': gaps,  # Raw gap size
            'gap_magnitude': gap_magnitude,
            'gap_direction': gap_direction,
            'significant_gap': significant_gaps
        })
        return result.dropna()
    
    def _calculate_candle_body_ratio(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Candle Body to Total Range Ratio."""
        open_price = data['open']
        close_price = data['close']
        high = data['high']
        low = data['low']
        
        body_size = abs(close_price - open_price)
        total_range = high - low
        
        body_ratio = body_size / total_range
        body_ratio = body_ratio.fillna(0)
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': body_ratio
        })
        return result
    
    def _calculate_candle_wick_ratio(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Upper and Lower Wick Ratios."""
        open_price = data['open']
        close_price = data['close']
        high = data['high']
        low = data['low']
        
        body_top = pd.DataFrame([open_price, close_price]).max()
        body_bottom = pd.DataFrame([open_price, close_price]).min()
        
        upper_wick = high - body_top
        lower_wick = body_bottom - low
        total_range = high - low
        
        upper_wick_ratio = upper_wick / total_range
        lower_wick_ratio = lower_wick / total_range
        
        # Combined wick dominance measure
        wick_dominance = (upper_wick_ratio + lower_wick_ratio)
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': wick_dominance,
            'upper_wick_ratio': upper_wick_ratio,
            'lower_wick_ratio': lower_wick_ratio
        })
        return result
    
    def _calculate_price_momentum(self, data: pd.DataFrame, period: int = 10) -> pd.DataFrame:
        """Calculate Price Momentum."""
        close = data['close']
        momentum = close / close.shift(period) - 1
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': momentum
        })
        return result.dropna()
    
    def _calculate_volume_momentum(self, data: pd.DataFrame, period: int = 10) -> pd.DataFrame:
        """Calculate Volume Momentum."""
        volume = data['volume']
        volume_momentum = volume / volume.shift(period) - 1
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': volume_momentum
        })
        return result.dropna()
    
    def _calculate_price_acceleration(self, data: pd.DataFrame, period: int = 5) -> pd.DataFrame:
        """Calculate Price Acceleration (second derivative of price)."""
        close = data['close']
        
        # First derivative (velocity)
        velocity = close.diff()
        
        # Second derivative (acceleration)
        acceleration = velocity.diff()
        
        # Smooth acceleration
        smoothed_acceleration = acceleration.rolling(window=period).mean()
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': smoothed_acceleration
        })
        return result.dropna()

    @classmethod
    def get_available_indicators(cls) -> Dict[str, Dict]:
        """Get list of all available chart-based indicators."""
        return {
            'volume_sma': {'name': 'Volume SMA Ratio', 'params': {'period': 20}},
            'volume_profile': {'name': 'Volume Profile Position', 'params': {'bins': 50}},
            'price_volatility': {'name': 'Price Volatility', 'params': {'period': 20}},
            'daily_range': {'name': 'Daily Range Ratio', 'params': {'period': 10}},
            'gap_analysis': {'name': 'Gap Analysis', 'params': {'threshold': 0.001}},
            'candle_body_ratio': {'name': 'Candle Body Ratio', 'params': {}},
            'candle_wick_ratio': {'name': 'Candle Wick Ratio', 'params': {}},
            'price_momentum': {'name': 'Price Momentum', 'params': {'period': 10}},
            'volume_momentum': {'name': 'Volume Momentum', 'params': {'period': 10}},
            'price_acceleration': {'name': 'Price Acceleration', 'params': {'period': 5}}
        }
