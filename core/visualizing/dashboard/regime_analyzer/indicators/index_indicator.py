from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from .base_indicator import BaseIndicator

class IndexIndicator(BaseIndicator):
    """Index/Stock market specific indicators for traditional market analysis.
    
    Includes: VIX, Sector Rotation, Bond Yields, Economic Indicators, etc.
    """
    
    def __init__(self, indicator_type: str, **params):
        super().__init__(f"index_{indicator_type}", "index")
        self.indicator_type = indicator_type
        self.params = params
        
        # Define available index indicators
        self.available_indicators = {
            'vix': self._calculate_vix,
            'bond_yield_10y': self._calculate_bond_yield_10y,
            'dollar_index': self._calculate_dollar_index,
            'sector_rotation': self._calculate_sector_rotation,
            'economic_surprise': self._calculate_economic_surprise,
            'credit_spreads': self._calculate_credit_spreads,
            'put_call_ratio': self._calculate_put_call_ratio,
            'margin_debt': self._calculate_margin_debt,
            'insider_trading': self._calculate_insider_trading,
            'earnings_yield': self._calculate_earnings_yield
        }
        
        if indicator_type not in self.available_indicators:
            raise ValueError(f"Unsupported index indicator type: {indicator_type}")
    
    def calculate(self, price_data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Calculate the specified index indicator."""
        # Note: Index indicators often don't need price_data, they fetch external data
        
        # Merge kwargs with instance params
        calc_params = {**self.params, **kwargs}
        
        # Calculate the indicator
        calculator = self.available_indicators[self.indicator_type]
        result = calculator(price_data, **calc_params)
        
        return self.standardize_output(result)
    
    def get_required_columns(self) -> List[str]:
        """Return required columns - many index indicators are external."""
        requirements = {
            'vix': [],  # External API
            'bond_yield_10y': [],  # External API
            'dollar_index': [],  # External API
            'sector_rotation': ['close'],  # May need sector price data
            'economic_surprise': [],  # External API
            'credit_spreads': [],  # External API
            'put_call_ratio': [],  # External API
            'margin_debt': [],  # External API
            'insider_trading': [],  # External API
            'earnings_yield': []  # External API
        }
        return requirements.get(self.indicator_type, [])
    
    def get_parameters(self) -> Dict:
        """Return default parameters for each indicator."""
        defaults = {
            'vix': {'days': 30},
            'bond_yield_10y': {'days': 30},
            'dollar_index': {'days': 30},
            'sector_rotation': {'sectors': ['XLK', 'XLF', 'XLE', 'XLV', 'XLI']},
            'economic_surprise': {'country': 'US'},
            'credit_spreads': {'type': 'investment_grade'},
            'put_call_ratio': {'market': 'SPX'},
            'margin_debt': {'days': 30},
            'insider_trading': {'sentiment': 'net_buying'},
            'earnings_yield': {'index': 'SP500'}
        }
        return defaults.get(self.indicator_type, {})
    
    def _calculate_vix(self, data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
        """Calculate VIX (Volatility Index) - Fear Index for stocks."""
        try:
            # In real implementation, would use FRED API or Yahoo Finance
            # For now, generate realistic VIX-like synthetic data
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
            
            # VIX typically ranges 10-80, with mean around 20
            vix_values = np.random.lognormal(mean=3.0, sigma=0.3, size=days)
            vix_values = np.clip(vix_values, 10, 80)
            
            # Add some trending behavior
            trend = np.linspace(1.0, 0.95, days)  # Slight downward trend
            vix_values = vix_values * trend
            
            result = pd.DataFrame({
                'timestamp': timestamps,
                'value': vix_values
            })
            
            # Add additional VIX metrics
            result['vix_percentile'] = result['value'].rolling(window=min(252, days)).rank(pct=True)
            result['vix_fear_level'] = pd.cut(result['value'], 
                                            bins=[0, 12, 20, 30, 100], 
                                            labels=['Low', 'Normal', 'Elevated', 'High'])
            
            self.set_metadata(fallback_data=True, note="Using synthetic VIX data")
            return result
            
        except Exception as e:
            print(f"[INDEX] VIX calculation error: {e}")
            return self._generate_fallback_data(data, 'vix')
    
    def _calculate_bond_yield_10y(self, data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
        """Calculate 10-Year Treasury Bond Yield."""
        try:
            # Generate realistic 10Y yield data (typically 1-5%)
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
            
            base_yield = 3.5  # Current approximate 10Y yield
            yield_values = np.random.normal(base_yield, 0.1, days)
            yield_values = np.clip(yield_values, 1.0, 6.0)
            
            # Add gradual trend
            trend = np.linspace(0, 0.2, days)  # Slight upward trend
            yield_values = yield_values + trend
            
            result = pd.DataFrame({
                'timestamp': timestamps,
                'value': yield_values
            })
            
            # Add yield curve analysis
            result['yield_regime'] = pd.cut(result['value'],
                                          bins=[0, 2, 3, 4, 10],
                                          labels=['Low', 'Normal', 'Elevated', 'High'])
            
            self.set_metadata(fallback_data=True, note="Using synthetic 10Y yield data")
            return result
            
        except Exception as e:
            print(f"[INDEX] Bond yield calculation error: {e}")
            return self._generate_fallback_data(data, 'bond_yield_10y')
    
    def _calculate_dollar_index(self, data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
        """Calculate US Dollar Index (DXY)."""
        try:
            # DXY typically ranges 90-120
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
            
            base_dxy = 105.0
            dxy_values = np.random.normal(base_dxy, 1.5, days)
            dxy_values = np.clip(dxy_values, 85, 125)
            
            # Add some momentum
            momentum = np.cumsum(np.random.normal(0, 0.3, days))
            dxy_values = dxy_values + momentum * 0.5
            
            result = pd.DataFrame({
                'timestamp': timestamps,
                'value': dxy_values
            })
            
            # Add DXY strength levels
            result['dollar_strength'] = pd.cut(result['value'],
                                             bins=[0, 95, 105, 115, 200],
                                             labels=['Weak', 'Normal', 'Strong', 'Very Strong'])
            
            self.set_metadata(fallback_data=True, note="Using synthetic DXY data")
            return result
            
        except Exception as e:
            print(f"[INDEX] Dollar Index calculation error: {e}")
            return self._generate_fallback_data(data, 'dollar_index')
    
    def _calculate_sector_rotation(self, data: pd.DataFrame, sectors: List[str] = None) -> pd.DataFrame:
        """Calculate Sector Rotation Indicator."""
        if sectors is None:
            sectors = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI']  # Tech, Finance, Energy, Healthcare, Industrial
        
        try:
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D')
            
            # Generate relative strength for each sector
            sector_performance = {}
            for sector in sectors:
                perf = np.random.normal(0, 0.02, len(timestamps))  # Daily returns
                sector_performance[sector] = np.cumprod(1 + perf)
            
            # Calculate sector rotation momentum (which sectors are outperforming)
            rotation_scores = []
            for i in range(len(timestamps)):
                day_perfs = {sector: perf[i] for sector, perf in sector_performance.items()}
                # Score based on relative ranking
                sorted_sectors = sorted(day_perfs.items(), key=lambda x: x[1], reverse=True)
                rotation_score = (sorted_sectors[0][1] - sorted_sectors[-1][1])  # Spread between best and worst
                rotation_scores.append(rotation_score)
            
            result = pd.DataFrame({
                'timestamp': timestamps,
                'value': rotation_scores  # High value = strong sector rotation
            })
            
            # Add sector data
            for sector in sectors:
                result[f'{sector}_performance'] = sector_performance[sector]
            
            self.set_metadata(fallback_data=True, note="Using synthetic sector rotation data")
            return result
            
        except Exception as e:
            print(f"[INDEX] Sector rotation calculation error: {e}")
            return self._generate_fallback_data(data, 'sector_rotation')
    
    def _calculate_economic_surprise(self, data: pd.DataFrame, country: str = 'US') -> pd.DataFrame:
        """Calculate Economic Surprise Index."""
        return self._generate_fallback_data(data, 'economic_surprise')
    
    def _calculate_credit_spreads(self, data: pd.DataFrame, type: str = 'investment_grade') -> pd.DataFrame:
        """Calculate Credit Spreads."""
        return self._generate_fallback_data(data, 'credit_spreads')
    
    def _calculate_put_call_ratio(self, data: pd.DataFrame, market: str = 'SPX') -> pd.DataFrame:
        """Calculate Put/Call Ratio."""
        try:
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D')
            
            # Put/Call ratio typically 0.5-2.0, with 1.0 being neutral
            pc_ratio = np.random.lognormal(mean=-0.1, sigma=0.2, size=len(timestamps))
            pc_ratio = np.clip(pc_ratio, 0.3, 2.5)
            
            result = pd.DataFrame({
                'timestamp': timestamps,
                'value': pc_ratio
            })
            
            # Add sentiment levels
            result['sentiment'] = pd.cut(result['value'],
                                       bins=[0, 0.7, 1.3, 10],
                                       labels=['Bullish', 'Neutral', 'Bearish'])
            
            self.set_metadata(fallback_data=True, note="Using synthetic Put/Call ratio data")
            return result
            
        except Exception as e:
            return self._generate_fallback_data(data, 'put_call_ratio')
    
    def _calculate_margin_debt(self, data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
        """Calculate Margin Debt levels."""
        return self._generate_fallback_data(data, 'margin_debt')
    
    def _calculate_insider_trading(self, data: pd.DataFrame, sentiment: str = 'net_buying') -> pd.DataFrame:
        """Calculate Insider Trading sentiment."""
        return self._generate_fallback_data(data, 'insider_trading')
    
    def _calculate_earnings_yield(self, data: pd.DataFrame, index: str = 'SP500') -> pd.DataFrame:
        """Calculate Earnings Yield for index."""
        return self._generate_fallback_data(data, 'earnings_yield')
    
    def _generate_fallback_data(self, data: pd.DataFrame, indicator_type: str) -> pd.DataFrame:
        """Generate fallback synthetic data when APIs are unavailable."""
        if data is not None and len(data) > 0:
            timestamps = data.get('timestamp', data.index) if hasattr(data, 'get') else pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D')
        else:
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D')
        
        # Generate synthetic data based on indicator type
        fallback_generators = {
            'vix': lambda: np.random.lognormal(mean=3.0, sigma=0.3, size=len(timestamps)).clip(10, 80),
            'bond_yield_10y': lambda: np.random.normal(3.5, 0.2, len(timestamps)).clip(1, 6),
            'dollar_index': lambda: np.random.normal(105, 2, len(timestamps)).clip(90, 120),
            'sector_rotation': lambda: np.random.normal(0, 0.02, len(timestamps)),
            'economic_surprise': lambda: np.random.normal(0, 1, len(timestamps)).clip(-3, 3),
            'credit_spreads': lambda: np.random.normal(1.5, 0.3, len(timestamps)).clip(0.5, 5),
            'put_call_ratio': lambda: np.random.lognormal(mean=-0.1, sigma=0.2, size=len(timestamps)).clip(0.3, 2.5),
            'margin_debt': lambda: np.random.normal(800, 50, len(timestamps)).clip(600, 1000),
            'insider_trading': lambda: np.random.normal(0, 0.5, len(timestamps)).clip(-2, 2),
            'earnings_yield': lambda: np.random.normal(5.5, 0.5, len(timestamps)).clip(3, 8)
        }
        
        generator = fallback_generators.get(indicator_type, lambda: np.random.normal(0, 1, len(timestamps)))
        values = generator()
        
        result = pd.DataFrame({
            'timestamp': timestamps,
            'value': values
        })
        
        self.set_metadata(fallback_data=True, note=f"Using synthetic data for {indicator_type}")
        return result

    @classmethod
    def get_available_indicators(cls) -> Dict[str, Dict]:
        """Get list of all available index indicators."""
        return {
            'vix': {'name': 'VIX Volatility Index', 'params': {'days': 30}},
            'bond_yield_10y': {'name': '10-Year Treasury Yield', 'params': {'days': 30}},
            'dollar_index': {'name': 'US Dollar Index (DXY)', 'params': {'days': 30}},
            'sector_rotation': {'name': 'Sector Rotation', 'params': {'sectors': ['XLK', 'XLF', 'XLE', 'XLV', 'XLI']}},
            'economic_surprise': {'name': 'Economic Surprise Index', 'params': {'country': 'US'}},
            'credit_spreads': {'name': 'Credit Spreads', 'params': {'type': 'investment_grade'}},
            'put_call_ratio': {'name': 'Put/Call Ratio', 'params': {'market': 'SPX'}},
            'margin_debt': {'name': 'Margin Debt', 'params': {'days': 30}},
            'insider_trading': {'name': 'Insider Trading', 'params': {'sentiment': 'net_buying'}},
            'earnings_yield': {'name': 'Earnings Yield', 'params': {'index': 'SP500'}}
        }
