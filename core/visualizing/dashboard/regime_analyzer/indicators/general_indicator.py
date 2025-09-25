from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from .base_indicator import BaseIndicator

class GeneralIndicator(BaseIndicator):
    """General financial indicators that work for both crypto and traditional markets.
    
    Includes: RSI, MACD, Bollinger Bands, Moving Averages, ATR, etc.
    """
    
    def __init__(self, indicator_type: str, **params):
        super().__init__(f"general_{indicator_type}", "general")
        self.indicator_type = indicator_type
        self.params = params
        
        # Define available indicators
        self.available_indicators = {
            'rsi': self._calculate_rsi,
            'macd': self._calculate_macd,
            'bollinger': self._calculate_bollinger,
            'sma': self._calculate_sma,
            'ema': self._calculate_ema,
            'atr': self._calculate_atr,
            'stochastic': self._calculate_stochastic,
            'williams_r': self._calculate_williams_r,
            'cci': self._calculate_cci,
            'roc': self._calculate_roc
        }
        
        if indicator_type not in self.available_indicators:
            raise ValueError(f"Unsupported indicator type: {indicator_type}")
    
    def calculate(self, price_data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Calculate the specified general indicator."""
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
            'rsi': ['close'],
            'macd': ['close'],
            'bollinger': ['close'],
            'sma': ['close'],
            'ema': ['close'],
            'atr': ['high', 'low', 'close'],
            'stochastic': ['high', 'low', 'close'],
            'williams_r': ['high', 'low', 'close'],
            'cci': ['high', 'low', 'close'],
            'roc': ['close']
        }
        return requirements.get(self.indicator_type, ['close'])
    
    def get_parameters(self) -> Dict:
        """Return default parameters for each indicator."""
        defaults = {
            'rsi': {'period': 14},
            'macd': {'fast': 12, 'slow': 26, 'signal': 9},
            'bollinger': {'period': 20, 'std_dev': 2},
            'sma': {'period': 20},
            'ema': {'period': 20},
            'atr': {'period': 14},
            'stochastic': {'k_period': 14, 'd_period': 3},
            'williams_r': {'period': 14},
            'cci': {'period': 20},
            'roc': {'period': 10}
        }
        return defaults.get(self.indicator_type, {})
    
    def _calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Relative Strength Index."""
        close = data['close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': rsi
        })
        return result.dropna()
    
    def _calculate_macd(self, data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        close = data['close']
        ema_fast = close.ewm(span=fast).mean()
        ema_slow = close.ewm(span=slow).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        
        # Return MACD line as main value, but store all components
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': macd_line,
            'signal': signal_line,
            'histogram': histogram
        })
        return result.dropna()
    
    def _calculate_bollinger(self, data: pd.DataFrame, period: int = 20, std_dev: float = 2) -> pd.DataFrame:
        """Calculate Bollinger Bands."""
        close = data['close']
        sma = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        bb_width = (upper_band - lower_band) / sma
        bb_position = (close - lower_band) / (upper_band - lower_band)
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': bb_position,  # Position within bands as main value
            'upper_band': upper_band,
            'lower_band': lower_band,
            'middle_band': sma,
            'bb_width': bb_width
        })
        return result.dropna()
    
    def _calculate_sma(self, data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Calculate Simple Moving Average."""
        close = data['close']
        sma = close.rolling(window=period).mean()
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': sma
        })
        return result.dropna()
    
    def _calculate_ema(self, data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Calculate Exponential Moving Average."""
        close = data['close']
        ema = close.ewm(span=period).mean()
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': ema
        })
        return result.dropna()
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Average True Range."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        true_range = pd.DataFrame([tr1, tr2, tr3]).max()
        atr = true_range.rolling(window=period).mean()
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': atr
        })
        return result.dropna()
    
    def _calculate_stochastic(self, data: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
        """Calculate Stochastic Oscillator."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        k_percent = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d_percent = k_percent.rolling(window=d_period).mean()
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': k_percent,
            'd_percent': d_percent
        })
        return result.dropna()
    
    def _calculate_williams_r(self, data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Williams %R."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        
        williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': williams_r
        })
        return result.dropna()
    
    def _calculate_cci(self, data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Calculate Commodity Channel Index."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(window=period).mean()
        mean_deviation = typical_price.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        
        cci = (typical_price - sma_tp) / (0.015 * mean_deviation)
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': cci
        })
        return result.dropna()
    
    def _calculate_roc(self, data: pd.DataFrame, period: int = 10) -> pd.DataFrame:
        """Calculate Rate of Change."""
        close = data['close']
        roc = ((close - close.shift(period)) / close.shift(period)) * 100
        
        result = pd.DataFrame({
            'timestamp': data.get('timestamp', data.index),
            'value': roc
        })
        return result.dropna()

    @classmethod
    def get_available_indicators(cls) -> Dict[str, Dict]:
        """Get list of all available general indicators with their parameters."""
        return {
            'rsi': {'name': 'Relative Strength Index', 'params': {'period': 14}},
            'macd': {'name': 'MACD', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
            'bollinger': {'name': 'Bollinger Bands', 'params': {'period': 20, 'std_dev': 2}},
            'sma': {'name': 'Simple Moving Average', 'params': {'period': 20}},
            'ema': {'name': 'Exponential Moving Average', 'params': {'period': 20}},
            'atr': {'name': 'Average True Range', 'params': {'period': 14}},
            'stochastic': {'name': 'Stochastic Oscillator', 'params': {'k_period': 14, 'd_period': 3}},
            'williams_r': {'name': 'Williams %R', 'params': {'period': 14}},
            'cci': {'name': 'Commodity Channel Index', 'params': {'period': 20}},
            'roc': {'name': 'Rate of Change', 'params': {'period': 10}}
        }
