from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import numpy as np
from pathlib import Path
from .base_indicator import BaseIndicator
from .general_indicator import GeneralIndicator
from .chart_based_indicator import ChartBasedIndicator
from .crypto_indicator import CryptoIndicator
from .index_indicator import IndexIndicator

class IndicatorManager:
    """Orchestrates indicator loading and calculation based on analysis type.
    
    Manages the combination of:
    - CSV-based indicators from backtest runs
    - Calculated indicators (RSI, MACD, etc.)
    - External indicators (Fear & Greed, VIX, etc.)
    """
    
    def __init__(self, results_root: Path):
        self.results_root = Path(results_root)
        self.csv_indicators = {}
        self.calculated_indicators = {}
        self.external_indicators = {}
        self.price_data = None
        
    def load_csv_indicators(self, run_id: str) -> bool:
        """Load CSV-based indicators from backtest run."""
        print(f"[INDICATOR_MGR] Loading CSV indicators for run: {run_id}")
        
        try:
            indicators_path = self.results_root / run_id / "general" / "indicators"
            
            if not indicators_path.exists():
                print(f"[INDICATOR_MGR] Indicators path does not exist: {indicators_path}")
                return False
            
            self.csv_indicators = {}
            csv_files = list(indicators_path.glob("*.csv"))
            print(f"[INDICATOR_MGR] Found {len(csv_files)} CSV indicator files")
            
            for csv_file in csv_files:
                if not csv_file.name.startswith('total'):
                    indicator_name = csv_file.stem
                    try:
                        df = pd.read_csv(csv_file)
                        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
                        df = df.sort_values('timestamp')
                        
                        # Store with metadata
                        self.csv_indicators[f"csv_{indicator_name}"] = {
                            'data': df[['timestamp', 'value']].rename(columns={'value': indicator_name}),
                            'source': 'csv',
                            'category': 'backtest',
                            'name': indicator_name
                        }
                        
                        print(f"[INDICATOR_MGR] Loaded CSV indicator: {indicator_name} ({len(df)} points)")
                        
                    except Exception as e:
                        print(f"[INDICATOR_MGR] Error loading CSV indicator {indicator_name}: {e}")
                        continue
            
            print(f"[INDICATOR_MGR] Total CSV indicators loaded: {len(self.csv_indicators)}")
            return True
            
        except Exception as e:
            print(f"[INDICATOR_MGR] Error loading CSV indicators: {e}")
            return False
    
    def load_price_data(self, run_id: str) -> bool:
        """Load price data for calculated indicators from actual instrument bars."""
        print(f"[INDICATOR_MGR] Loading real OHLC price data for run: {run_id}")
        
        try:
            run_path = self.results_root / run_id
            
            # Find all instrument directories (not 'general')
            instrument_dirs = [item for item in run_path.iterdir() if item.is_dir() and item.name != 'general']
            
            if not instrument_dirs:
                print(f"[INDICATOR_MGR] No instrument directories found, using synthetic data")
                self.price_data = self._generate_synthetic_price_data()
                return True
            
            # Try to load bars from first instrument found
            for instrument_dir in instrument_dirs:
                print(f"[INDICATOR_MGR] Checking instrument: {instrument_dir.name}")
                
                # Look for bar files (bars-5M.csv, bars-15M.csv, etc.)
                bar_files = list(instrument_dir.glob("bars-*.csv"))
                
                if bar_files:
                    # Use the first bar file found (could be enhanced to select specific timeframe)
                    bar_file = bar_files[0]
                    timeframe = bar_file.stem.replace('bars-', '')  # Extract timeframe
                    
                    print(f"[INDICATOR_MGR] Loading bars from: {bar_file.name} (timeframe: {timeframe})")
                    
                    try:
                        bars_df = pd.read_csv(bar_file)
                        print(f"[INDICATOR_MGR] Raw bars data shape: {bars_df.shape}")
                        print(f"[INDICATOR_MGR] Raw bars columns: {bars_df.columns.tolist()}")
                        
                        # Convert timestamp and ensure OHLC format
                        if 'timestamp' in bars_df.columns:
                            bars_df['timestamp'] = pd.to_datetime(bars_df['timestamp'], unit='ns')  # FIX: Convert from ns
                        else:
                            print(f"[INDICATOR_MGR] No timestamp column found in {bar_file.name}")
                            continue
                        
                        bars_df = bars_df.sort_values('timestamp')
                        
                        # Ensure we have OHLC columns (volume not required, will be generated)
                        required_cols = ['open', 'high', 'low', 'close']
                        if all(col in bars_df.columns for col in required_cols):
                            # NEW: Add synthetic volume if missing
                            if 'volume' not in bars_df.columns:
                                print(f"[INDICATOR_MGR] Volume column missing, generating synthetic volume")
                                # Generate realistic volume based on price volatility
                                price_range = bars_df['high'] - bars_df['low']
                                avg_price = (bars_df['high'] + bars_df['low'] + bars_df['close']) / 3
                                volatility = price_range / avg_price
                                
                                # Base volume with volatility adjustment
                                base_volume = 1000000  # 1M base volume
                                volume_multiplier = 1 + (volatility * 2)  # Higher volatility = higher volume
                                
                                # Add some randomness
                                np.random.seed(42)  # Reproducible
                                random_factor = np.random.lognormal(0, 0.3, len(bars_df))
                                
                                bars_df['volume'] = (base_volume * volume_multiplier * random_factor).astype(int)
                            
                            self.price_data = bars_df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
                            
                            # Add metadata
                            self.price_data_metadata = {
                                'instrument': instrument_dir.name,
                                'timeframe': timeframe,
                                'source_file': str(bar_file),
                                'data_points': len(self.price_data),
                                'synthetic_volume': 'volume' not in bars_df.columns
                            }
                            
                            print(f"[INDICATOR_MGR] Successfully loaded {len(self.price_data)} bars")
                            print(f"[INDICATOR_MGR] Instrument: {instrument_dir.name}, Timeframe: {timeframe}")
                            print(f"[INDICATOR_MGR] Date range: {self.price_data['timestamp'].min()} to {self.price_data['timestamp'].max()}")
                            print(f"[INDICATOR_MGR] Price range: {self.price_data['close'].min():.2f} - {self.price_data['close'].max():.2f}")
                            print(f"[INDICATOR_MGR] Volume range: {self.price_data['volume'].min():,} - {self.price_data['volume'].max():,}")
                            
                            return True
                        else:
                            missing = [col for col in required_cols if col not in bars_df.columns]
                            print(f"[INDICATOR_MGR] Missing OHLC columns in {bar_file.name}: {missing}")
                            continue
                            
                    except Exception as e:
                        print(f"[INDICATOR_MGR] Error loading bars from {bar_file}: {e}")
                        continue
                else:
                    print(f"[INDICATOR_MGR] No bar files found in {instrument_dir.name}")
            
            # Fallback to synthetic data if no real data found
            print(f"[INDICATOR_MGR] No valid bar data found, generating synthetic data")
            self.price_data = self._generate_synthetic_price_data()
            self.price_data_metadata = {
                'instrument': 'SYNTHETIC',
                'timeframe': '1D',
                'source_file': 'generated',
                'data_points': len(self.price_data),
                'synthetic_volume': True
            }
            return True
            
        except Exception as e:
            print(f"[INDICATOR_MGR] Error loading price data: {e}")
            self.price_data = self._generate_synthetic_price_data()
            self.price_data_metadata = {
                'instrument': 'SYNTHETIC',
                'timeframe': '1D',
                'source_file': 'generated',
                'data_points': len(self.price_data),
                'synthetic_volume': True
            }
            return True

    def get_available_instruments_and_timeframes(self, run_id: str) -> Dict[str, List[str]]:
        """Get available instruments and their timeframes."""
        print(f"[INDICATOR_MGR] Scanning available instruments and timeframes for run: {run_id}")
        
        instruments_timeframes = {}
        
        try:
            run_path = self.results_root / run_id
            
            # Find all instrument directories
            instrument_dirs = [item for item in run_path.iterdir() if item.is_dir() and item.name != 'general']
            
            for instrument_dir in instrument_dirs:
                instrument_name = instrument_dir.name
                
                # Find all bar files
                bar_files = list(instrument_dir.glob("bars-*.csv"))
                
                timeframes = []
                for bar_file in bar_files:
                    timeframe = bar_file.stem.replace('bars-', '')
                    timeframes.append(timeframe)
                
                if timeframes:
                    instruments_timeframes[instrument_name] = sorted(timeframes)
                    print(f"[INDICATOR_MGR] Found {instrument_name}: {timeframes}")
                else:
                    print(f"[INDICATOR_MGR] No bar files in {instrument_name}")
                    
        except Exception as e:
            print(f"[INDICATOR_MGR] Error scanning instruments: {e}")
        
        print(f"[INDICATOR_MGR] Available instruments and timeframes: {instruments_timeframes}")
        return instruments_timeframes

    def load_specific_price_data(self, run_id: str, instrument: str, timeframe: str) -> bool:
        """Load price data for specific instrument and timeframe."""
        print(f"[INDICATOR_MGR] Loading specific price data: {instrument} - {timeframe}")
        
        try:
            bar_file = self.results_root / run_id / instrument / f"bars-{timeframe}.csv"
            
            if not bar_file.exists():
                print(f"[INDICATOR_MGR] Bar file not found: {bar_file}")
                return False
            
            bars_df = pd.read_csv(bar_file)
            print(f"[INDICATOR_MGR] Loaded {len(bars_df)} bars from {bar_file.name}")
            print(f"[INDICATOR_MGR] Raw bars columns: {bars_df.columns.tolist()}")
            
            # Process timestamp (from nanoseconds to datetime)
            bars_df['timestamp'] = pd.to_datetime(bars_df['timestamp'], unit='ns')
            bars_df = bars_df.sort_values('timestamp')
            
            # Validate OHLC columns (volume not required)
            required_cols = ['open', 'high', 'low', 'close']
            if not all(col in bars_df.columns for col in required_cols):
                missing = [col for col in required_cols if col not in bars_df.columns]
                print(f"[INDICATOR_MGR] Missing columns: {missing}")
                return False
            
            # NEW: Add synthetic volume if missing (for chart indicators that need it)
            if 'volume' not in bars_df.columns:
                print(f"[INDICATOR_MGR] Volume column missing, generating synthetic volume")
                # Generate realistic volume based on price volatility
                price_range = bars_df['high'] - bars_df['low']
                avg_price = (bars_df['high'] + bars_df['low'] + bars_df['close']) / 3
                volatility = price_range / avg_price
                
                # Base volume with volatility adjustment
                base_volume = 1000000  # 1M base volume
                volume_multiplier = 1 + (volatility * 2)  # Higher volatility = higher volume
                
                # Add some randomness
                np.random.seed(42)  # Reproducible
                random_factor = np.random.lognormal(0, 0.3, len(bars_df))
                
                bars_df['volume'] = (base_volume * volume_multiplier * random_factor).astype(int)
                print(f"[INDICATOR_MGR] Generated volume range: {bars_df['volume'].min():,} - {bars_df['volume'].max():,}")
            
            # Store price data with all required columns
            self.price_data = bars_df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
            self.price_data_metadata = {
                'instrument': instrument,
                'timeframe': timeframe,
                'source_file': str(bar_file),
                'data_points': len(self.price_data),
                'synthetic_volume': 'volume' not in bars_df.columns  # Track if volume is synthetic
            }
            
            print(f"[INDICATOR_MGR] Successfully loaded {instrument} {timeframe}: {len(self.price_data)} bars")
            print(f"[INDICATOR_MGR] Date range: {self.price_data['timestamp'].min()} to {self.price_data['timestamp'].max()}")
            print(f"[INDICATOR_MGR] Price range: {self.price_data['close'].min():.2f} - {self.price_data['close'].max():.2f}")
            
            return True
            
        except Exception as e:
            print(f"[INDICATOR_MGR] Error loading specific price data: {e}")
            import traceback
            print(f"[INDICATOR_MGR] Traceback: {traceback.format_exc()}")
            return False

    def calculate_general_indicators(self, indicator_list: List[str] = None) -> bool:
        """Calculate general financial indicators."""
        if self.price_data is None:
            print(f"[INDICATOR_MGR] No price data available for general indicators")
            return False
        
        if indicator_list is None:
            indicator_list = ['rsi', 'macd', 'bollinger', 'sma_20', 'ema_50', 'atr']
        
        print(f"[INDICATOR_MGR] Calculating general indicators: {indicator_list}")
        
        for indicator_name in indicator_list:
            try:
                # Parse indicator name and parameters
                if '_' in indicator_name:
                    base_name, param = indicator_name.split('_', 1)
                    if param.isdigit():
                        params = {'period': int(param)}
                    else:
                        params = {}
                else:
                    base_name = indicator_name
                    params = {}
                
                # Create and calculate indicator
                indicator = GeneralIndicator(base_name, **params)
                result = indicator.calculate(self.price_data)
                
                self.calculated_indicators[f"general_{indicator_name}"] = {
                    'data': result,
                    'source': 'calculated',
                    'category': 'general',
                    'name': indicator_name,
                    'indicator_obj': indicator
                }
                
                print(f"[INDICATOR_MGR] Calculated general indicator: {indicator_name}")
                
            except Exception as e:
                print(f"[INDICATOR_MGR] Error calculating general indicator {indicator_name}: {e}")
                continue
        
        return True
    
    def calculate_chart_indicators(self, indicator_list: List[str] = None) -> bool:
        """Calculate chart-based indicators."""
        if self.price_data is None:
            print(f"[INDICATOR_MGR] No price data available for chart indicators")
            return False
        
        if indicator_list is None:
            indicator_list = ['volume_sma', 'price_volatility', 'candle_body_ratio']
        
        print(f"[INDICATOR_MGR] Calculating chart indicators: {indicator_list}")
        
        for indicator_name in indicator_list:
            try:
                indicator = ChartBasedIndicator(indicator_name)
                result = indicator.calculate(self.price_data)
                
                self.calculated_indicators[f"chart_{indicator_name}"] = {
                    'data': result,
                    'source': 'calculated',
                    'category': 'chart_based',
                    'name': indicator_name,
                    'indicator_obj': indicator
                }
                
                print(f"[INDICATOR_MGR] Calculated chart indicator: {indicator_name}")
                
            except Exception as e:
                print(f"[INDICATOR_MGR] Error calculating chart indicator {indicator_name}: {e}")
                continue
        
        return True
    
    def load_crypto_indicators(self, indicator_list: List[str] = None) -> bool:
        """Load crypto-specific external indicators."""
        if indicator_list is None:
            indicator_list = ['fear_greed', 'btc_dominance']
        
        print(f"[INDICATOR_MGR] Loading crypto indicators: {indicator_list}")
        
        for indicator_name in indicator_list:
            try:
                indicator = CryptoIndicator(indicator_name)
                result = indicator.calculate(None)  # Crypto indicators don't need price data
                
                self.external_indicators[f"crypto_{indicator_name}"] = {
                    'data': result,
                    'source': 'external',
                    'category': 'crypto',
                    'name': indicator_name,
                    'indicator_obj': indicator
                }
                
                print(f"[INDICATOR_MGR] Loaded crypto indicator: {indicator_name}")
                
            except Exception as e:
                print(f"[INDICATOR_MGR] Error loading crypto indicator {indicator_name}: {e}")
                continue
        
        return True
    
    def load_index_indicators(self, indicator_list: List[str] = None) -> bool:
        """Load index/stock market indicators."""
        if indicator_list is None:
            indicator_list = ['vix', 'bond_yield_10y', 'put_call_ratio']
        
        print(f"[INDICATOR_MGR] Loading index indicators: {indicator_list}")
        
        for indicator_name in indicator_list:
            try:
                indicator = IndexIndicator(indicator_name)
                result = indicator.calculate(None)  # Index indicators don't need price data
                
                self.external_indicators[f"index_{indicator_name}"] = {
                    'data': result,
                    'source': 'external',
                    'category': 'index',
                    'name': indicator_name,
                    'indicator_obj': indicator
                }
                
                print(f"[INDICATOR_MGR] Loaded index indicator: {indicator_name}")
                
            except Exception as e:
                print(f"[INDICATOR_MGR] Error loading index indicator {indicator_name}: {e}")
                continue
        
        return True
    
    def get_indicators_for_analysis_type(self, analysis_type: str) -> Dict[str, pd.DataFrame]:
        """Get combined indicators based on analysis type."""
        print(f"[INDICATOR_MGR] Getting indicators for analysis type: {analysis_type}")
        
        combined_indicators = {}
        
        # Always include CSV indicators from backtest
        for key, indicator_info in self.csv_indicators.items():
            name = indicator_info['name']
            combined_indicators[name] = indicator_info['data']
        
        # Always include general indicators
        for key, indicator_info in self.calculated_indicators.items():
            if indicator_info['category'] == 'general':
                name = indicator_info['name']
                combined_indicators[f"general_{name}"] = indicator_info['data']
        
        # Always include chart-based indicators
        for key, indicator_info in self.calculated_indicators.items():
            if indicator_info['category'] == 'chart_based':
                name = indicator_info['name']
                combined_indicators[f"chart_{name}"] = indicator_info['data']
        
        # Add analysis-type specific external indicators
        for key, indicator_info in self.external_indicators.items():
            indicator_category = indicator_info['category']
            
            if analysis_type == 'crypto' and indicator_category == 'crypto':
                name = indicator_info['name']
                combined_indicators[f"crypto_{name}"] = indicator_info['data']
            elif analysis_type == 'index' and indicator_category == 'index':
                name = indicator_info['name']
                combined_indicators[f"index_{name}"] = indicator_info['data']
        
        print(f"[INDICATOR_MGR] Combined {len(combined_indicators)} indicators for {analysis_type} analysis")
        print(f"[INDICATOR_MGR] Available indicators: {list(combined_indicators.keys())}")
        
        return combined_indicators
    
    def load_all_for_analysis_type(self, run_id: str, analysis_type: str) -> Dict[str, pd.DataFrame]:
        """Load all indicators for a specific analysis type."""
        print(f"[INDICATOR_MGR] Loading all indicators for {analysis_type} analysis of run {run_id}")
        
        # Load CSV indicators from backtest
        self.load_csv_indicators(run_id)
        
        # Load price data
        self.load_price_data(run_id)
        
        # Calculate general indicators
        self.calculate_general_indicators()
        
        # Calculate chart-based indicators
        self.calculate_chart_indicators()
        
        # Load external indicators based on analysis type
        if analysis_type == 'crypto':
            self.load_crypto_indicators()
        elif analysis_type == 'index':
            self.load_index_indicators()
        
        # Return combined indicators
        return self.get_indicators_for_analysis_type(analysis_type)
    
    def get_available_indicators_info(self, analysis_type: str) -> Dict[str, Dict]:
        """Get information about available indicators for analysis type."""
        info = {}
        
        # Add info from loaded indicators
        for key, indicator_info in {**self.csv_indicators, **self.calculated_indicators, **self.external_indicators}.items():
            category = indicator_info['category']
            name = indicator_info['name']
            
            # Include based on analysis type
            include = False
            if category in ['backtest', 'general', 'chart_based']:
                include = True
            elif analysis_type == 'crypto' and category == 'crypto':
                include = True
            elif analysis_type == 'index' and category == 'index':
                include = True
            
            if include:
                info[name] = {
                    'category': category,
                    'source': indicator_info['source'],
                    'data_points': len(indicator_info['data']) if 'data' in indicator_info else 0
                }
        
        return info
    
    def _generate_synthetic_price_data(self, days: int = 252) -> pd.DataFrame:
        """Generate synthetic OHLCV data for testing."""
        print(f"[INDICATOR_MGR] Generating synthetic price data for {days} days")
        
        timestamps = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
        
        # Generate realistic price movement
        np.random.seed(42)  # For reproducible synthetic data
        returns = np.random.normal(0.0005, 0.02, days)  # Daily returns with slight upward drift
        prices = 100 * np.cumprod(1 + returns)  # Start at $100
        
        # Generate OHLCV data
        data = []
        for i, (timestamp, close_price) in enumerate(zip(timestamps, prices)):
            # Generate realistic OHLC
            open_price = close_price * (1 + np.random.normal(0, 0.005))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.01)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.01)))
            volume = int(np.random.lognormal(15, 0.5))  # Realistic volume
            
            data.append({
                'timestamp': timestamp,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
        
        return pd.DataFrame(data)
    
    def get_indicator_statistics(self) -> Dict:
        """Get statistics about loaded indicators including price data info."""
        stats = {
            'csv_indicators': len(self.csv_indicators),
            'calculated_indicators': len(self.calculated_indicators),
            'external_indicators': len(self.external_indicators),
            'total_indicators': len(self.csv_indicators) + len(self.calculated_indicators) + len(self.external_indicators),
            'has_price_data': self.price_data is not None,
            'price_data_points': len(self.price_data) if self.price_data is not None else 0
        }
        
        # Add price data metadata if available
        if hasattr(self, 'price_data_metadata'):
            stats.update(self.price_data_metadata)
        
        return stats
