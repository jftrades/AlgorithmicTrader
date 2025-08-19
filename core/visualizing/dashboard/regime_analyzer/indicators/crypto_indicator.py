from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from .base_indicator import BaseIndicator

class CryptoIndicator(BaseIndicator):
    """Crypto-specific indicators for cryptocurrency market analysis.
    
    Includes: Fear & Greed Index, Bitcoin Dominance, DeFi TVL, etc.
    """
    
    def __init__(self, indicator_type: str, **params):
        super().__init__(f"crypto_{indicator_type}", "crypto")
        self.indicator_type = indicator_type
        self.params = params
        
        # Define available crypto indicators
        self.available_indicators = {
            'fear_greed': self._calculate_fear_greed,
            'btc_dominance': self._calculate_btc_dominance,
            'total_market_cap': self._calculate_total_market_cap,
            'defi_tvl': self._calculate_defi_tvl,
            'stablecoin_supply': self._calculate_stablecoin_supply,
            'exchange_flows': self._calculate_exchange_flows,
            'mining_difficulty': self._calculate_mining_difficulty,
            'network_hash_rate': self._calculate_network_hash_rate,
            'active_addresses': self._calculate_active_addresses,
            'transaction_fees': self._calculate_transaction_fees
        }
        
        if indicator_type not in self.available_indicators:
            raise ValueError(f"Unsupported crypto indicator type: {indicator_type}")
    
    def calculate(self, price_data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Calculate the specified crypto indicator."""
        # Note: Crypto indicators often don't need price_data, they fetch external data
        
        # Merge kwargs with instance params
        calc_params = {**self.params, **kwargs}
        
        # Calculate the indicator
        calculator = self.available_indicators[self.indicator_type]
        result = calculator(price_data, **calc_params)
        
        return self.standardize_output(result)
    
    def get_required_columns(self) -> List[str]:
        """Return required columns - many crypto indicators are external."""
        requirements = {
            'fear_greed': [],  # External API
            'btc_dominance': [],  # External API
            'total_market_cap': [],  # External API
            'defi_tvl': [],  # External API
            'stablecoin_supply': [],  # External API
            'exchange_flows': [],  # External API (placeholder)
            'mining_difficulty': [],  # External API (placeholder)
            'network_hash_rate': [],  # External API (placeholder)
            'active_addresses': [],  # External API (placeholder)
            'transaction_fees': []  # External API (placeholder)
        }
        return requirements.get(self.indicator_type, [])
    
    def get_parameters(self) -> Dict:
        """Return default parameters for each indicator."""
        defaults = {
            'fear_greed': {'days': 30},
            'btc_dominance': {'days': 30},
            'total_market_cap': {'days': 30},
            'defi_tvl': {'protocol': 'total'},
            'stablecoin_supply': {'stablecoin': 'total'},
            'exchange_flows': {'exchange': 'binance'},
            'mining_difficulty': {'blockchain': 'bitcoin'},
            'network_hash_rate': {'blockchain': 'bitcoin'},
            'active_addresses': {'blockchain': 'bitcoin'},
            'transaction_fees': {'blockchain': 'bitcoin'}
        }
        return defaults.get(self.indicator_type, {})
    
    def _calculate_fear_greed(self, data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
        """Calculate Crypto Fear & Greed Index.
        
        Uses Alternative.me API to fetch Fear & Greed Index data.
        """
        try:
            # Alternative.me Fear & Greed Index API
            url = f"https://api.alternative.me/fng/?limit={days}&format=json"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                fng_data = response.json()
                
                records = []
                for item in fng_data['data']:
                    records.append({
                        'timestamp': pd.to_datetime(int(item['timestamp']), unit='s'),
                        'value': float(item['value']),
                        'classification': item['value_classification']
                    })
                
                result = pd.DataFrame(records)
                result = result.sort_values('timestamp')
                
                # Add additional metrics
                result['value_normalized'] = result['value'] / 100  # 0-1 scale
                result['fear_extreme'] = (result['value'] < 25).astype(int)
                result['greed_extreme'] = (result['value'] > 75).astype(int)
                
                return result
            else:
                print(f"[CRYPTO] Fear & Greed API error: {response.status_code}")
                return self._generate_fallback_data(data, 'fear_greed')
                
        except Exception as e:
            print(f"[CRYPTO] Fear & Greed calculation error: {e}")
            return self._generate_fallback_data(data, 'fear_greed')
    
    def _calculate_btc_dominance(self, data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
        """Calculate Bitcoin Dominance.
        
        Uses CoinGecko API to fetch Bitcoin dominance data.
        """
        try:
            # CoinGecko API for Bitcoin dominance
            url = f"https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                global_data = response.json()
                btc_dominance = global_data['data']['market_cap_percentage']['btc']
                
                # Create time series data (simplified - in reality would need historical API)
                result = pd.DataFrame({
                    'timestamp': pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D'),
                    'value': [btc_dominance] * days,  # Simplified - would need historical data
                })
                
                # Add trend analysis
                result['dominance_normalized'] = result['value'] / 100
                result['high_dominance'] = (result['value'] > 50).astype(int)
                
                return result
            else:
                print(f"[CRYPTO] BTC Dominance API error: {response.status_code}")
                return self._generate_fallback_data(data, 'btc_dominance')
                
        except Exception as e:
            print(f"[CRYPTO] BTC Dominance calculation error: {e}")
            return self._generate_fallback_data(data, 'btc_dominance')
    
    def _calculate_total_market_cap(self, data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
        """Calculate Total Crypto Market Cap."""
        try:
            # CoinGecko API for total market cap
            url = f"https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                global_data = response.json()
                total_mcap = global_data['data']['total_market_cap']['usd']
                
                result = pd.DataFrame({
                    'timestamp': pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D'),
                    'value': [total_mcap] * days,  # Simplified
                })
                
                # Normalize to trillions
                result['value_trillions'] = result['value'] / 1e12
                
                return result
            else:
                return self._generate_fallback_data(data, 'total_market_cap')
                
        except Exception as e:
            print(f"[CRYPTO] Total Market Cap calculation error: {e}")
            return self._generate_fallback_data(data, 'total_market_cap')
    
    def _calculate_defi_tvl(self, data: pd.DataFrame, protocol: str = 'total') -> pd.DataFrame:
        """Calculate DeFi Total Value Locked (TVL)."""
        # Placeholder implementation - would integrate with DeFiLlama API
        return self._generate_fallback_data(data, 'defi_tvl')
    
    def _calculate_stablecoin_supply(self, data: pd.DataFrame, stablecoin: str = 'total') -> pd.DataFrame:
        """Calculate Stablecoin Supply metrics."""
        # Placeholder implementation - would integrate with on-chain data
        return self._generate_fallback_data(data, 'stablecoin_supply')
    
    def _calculate_exchange_flows(self, data: pd.DataFrame, exchange: str = 'binance') -> pd.DataFrame:
        """Calculate Exchange Inflows/Outflows."""
        # Placeholder implementation - would integrate with exchange APIs
        return self._generate_fallback_data(data, 'exchange_flows')
    
    def _calculate_mining_difficulty(self, data: pd.DataFrame, blockchain: str = 'bitcoin') -> pd.DataFrame:
        """Calculate Mining Difficulty."""
        # Placeholder implementation - would integrate with blockchain APIs
        return self._generate_fallback_data(data, 'mining_difficulty')
    
    def _calculate_network_hash_rate(self, data: pd.DataFrame, blockchain: str = 'bitcoin') -> pd.DataFrame:
        """Calculate Network Hash Rate."""
        # Placeholder implementation - would integrate with blockchain APIs
        return self._generate_fallback_data(data, 'network_hash_rate')
    
    def _calculate_active_addresses(self, data: pd.DataFrame, blockchain: str = 'bitcoin') -> pd.DataFrame:
        """Calculate Active Addresses."""
        # Placeholder implementation - would integrate with blockchain APIs
        return self._generate_fallback_data(data, 'active_addresses')
    
    def _calculate_transaction_fees(self, data: pd.DataFrame, blockchain: str = 'bitcoin') -> pd.DataFrame:
        """Calculate Transaction Fees."""
        # Placeholder implementation - would integrate with blockchain APIs
        return self._generate_fallback_data(data, 'transaction_fees')
    
    def _generate_fallback_data(self, data: pd.DataFrame, indicator_type: str) -> pd.DataFrame:
        """Generate fallback synthetic data when APIs are unavailable."""
        if data is not None and len(data) > 0:
            timestamps = data.get('timestamp', data.index) if hasattr(data, 'get') else pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D')
        else:
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D')
        
        # Generate synthetic data based on indicator type
        fallback_generators = {
            'fear_greed': lambda: np.random.normal(50, 20, len(timestamps)).clip(0, 100),
            'btc_dominance': lambda: np.random.normal(45, 5, len(timestamps)).clip(30, 70),
            'total_market_cap': lambda: np.random.normal(1.5e12, 2e11, len(timestamps)),
            'defi_tvl': lambda: np.random.normal(50e9, 10e9, len(timestamps)),
            'stablecoin_supply': lambda: np.random.normal(100e9, 10e9, len(timestamps))
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
        """Get list of all available crypto indicators."""
        return {
            'fear_greed': {'name': 'Fear & Greed Index', 'params': {'days': 30}},
            'btc_dominance': {'name': 'Bitcoin Dominance', 'params': {'days': 30}},
            'total_market_cap': {'name': 'Total Market Cap', 'params': {'days': 30}},
            'defi_tvl': {'name': 'DeFi TVL', 'params': {'protocol': 'total'}},
            'stablecoin_supply': {'name': 'Stablecoin Supply', 'params': {'stablecoin': 'total'}},
            'exchange_flows': {'name': 'Exchange Flows', 'params': {'exchange': 'binance'}},
            'mining_difficulty': {'name': 'Mining Difficulty', 'params': {'blockchain': 'bitcoin'}},
            'network_hash_rate': {'name': 'Network Hash Rate', 'params': {'blockchain': 'bitcoin'}},
            'active_addresses': {'name': 'Active Addresses', 'params': {'blockchain': 'bitcoin'}},
            'transaction_fees': {'name': 'Transaction Fees', 'params': {'blockchain': 'bitcoin'}}
        }
