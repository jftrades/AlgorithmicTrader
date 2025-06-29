from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')

# Config
SYMBOL = "BTCUSDT"
START_DATE = "2024-01-01"
END_DATE = "2024-01-31"

# Paths
INPUT_DIR = Path(__file__).resolve().parent.parent.parent / "DATA_STORAGE" / "processed_tick_data"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "DATA_STORAGE" / "transformed_tick_data"

# Timeframes
TIMEFRAMES = {
    '1s': '1S', '5s': '5S', '1m': '1min', '5m': '5min', 
    '15m': '15min', '1h': '1H', '4h': '4H', '1d': '1D'
}

def create_directories():
    """Create output directories"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for subdir in ["bars", "volume_bars", "tick_bars", "analytics"]:
        (OUTPUT_DIR / subdir).mkdir(exist_ok=True)
    print(f"Output directories created: {OUTPUT_DIR}")

def get_combined_tick_file(symbol: str, start_date: str, end_date: str) -> Optional[Path]:
    """Find combined tick parquet file"""
    date_range = f"{start_date}_to_{end_date}"
    file_path = INPUT_DIR / f"processed_tick_data_{symbol}_{date_range}.parquet"
    if file_path.exists():
        return file_path
    else:
        print(f"❌ Combined tick file not found: {file_path}")
        return None

def load_combined_tick_data(file_path: Path) -> pd.DataFrame:
    """Load combined tick file"""
    print(f"📖 Loading combined tick file: {file_path.name}")
    try:
        df = pd.read_parquet(file_path)
        print(f"✅ {len(df):,} ticks loaded")
        print(f"📊 Period: {df['datetime'].min()} to {df['datetime'].max()}")
        print(f"🎯 Symbol: {df['symbol'].iloc[0]}")
        return df
    except Exception as e:
        print(f"❌ Load error: {e}")
        raise

def create_time_bars(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Create time-based OHLCV bars from tick data"""
    print(f"📊 Creating {timeframe} time bars...")
    
    df_indexed = df.set_index('datetime')
    
    # OHLCV aggregation
    bars = df_indexed['price'].resample(timeframe).agg([
        ('open', 'first'), ('high', 'max'), ('low', 'min'), ('close', 'last')
    ]).dropna()
    
    # Volume metrics
    volume = df_indexed['quantity'].resample(timeframe).sum()
    volume_quote = (df_indexed['price'] * df_indexed['quantity']).resample(timeframe).sum()
    trade_count = df_indexed['trade_id'].resample(timeframe).count()
    
    buy_mask = df_indexed['side'] == 'BUY'
    buy_volume = df_indexed[buy_mask]['quantity'].resample(timeframe).sum()
    sell_volume = df_indexed[~buy_mask]['quantity'].resample(timeframe).sum()
    
    bars['volume'] = volume
    bars['volume_quote'] = volume_quote
    bars['trade_count'] = trade_count
    bars['buy_volume'] = buy_volume.fillna(0)
    bars['sell_volume'] = sell_volume.fillna(0)
    bars['volume_imbalance'] = (bars['buy_volume'] - bars['sell_volume']) / bars['volume']
    bars['avg_trade_size'] = bars['volume'] / bars['trade_count']
    bars['vwap'] = bars['volume_quote'] / bars['volume']
    
    bars = bars.reset_index()
    bars['symbol'] = df['symbol'].iloc[0]
    bars['timeframe'] = timeframe
    
    print(f"  ✅ {len(bars)} bars created")
    return bars

def create_volume_bars(df: pd.DataFrame, volume_threshold: float) -> pd.DataFrame:
    """Create volume-based bars (constant volume per bar)"""
    print(f"📊 Creating volume bars (threshold: {volume_threshold:,.0f})...")
    
    bars = []
    current_volume = 0
    current_bar_ticks = []
    
    for _, tick in df.iterrows():
        current_bar_ticks.append(tick)
        current_volume += tick['quantity']
        
        if current_volume >= volume_threshold:
            bar_df = pd.DataFrame(current_bar_ticks)
            
            bar = {
                'datetime': bar_df['datetime'].iloc[-1],
                'open': bar_df['price'].iloc[0], 'high': bar_df['price'].max(),
                'low': bar_df['price'].min(), 'close': bar_df['price'].iloc[-1],
                'volume': bar_df['quantity'].sum(),
                'volume_quote': (bar_df['price'] * bar_df['quantity']).sum(),
                'trade_count': len(bar_df),
                'buy_volume': bar_df[bar_df['side'] == 'BUY']['quantity'].sum(),
                'sell_volume': bar_df[bar_df['side'] == 'SELL']['quantity'].sum(),
                'duration_seconds': (bar_df['datetime'].iloc[-1] - bar_df['datetime'].iloc[0]).total_seconds(),
                'symbol': tick['symbol']
            }
            
            bars.append(bar)
            current_volume = 0
            current_bar_ticks = []
    
    if bars:
        bars_df = pd.DataFrame(bars)
        bars_df['volume_imbalance'] = (bars_df['buy_volume'] - bars_df['sell_volume']) / bars_df['volume']
        bars_df['avg_trade_size'] = bars_df['volume'] / bars_df['trade_count']
        bars_df['vwap'] = bars_df['volume_quote'] / bars_df['volume']
        bars_df['bar_type'] = 'volume'
        
        print(f"  ✅ {len(bars_df)} volume bars created")
        return bars_df
    else:
        print("  ❌ No volume bars created")
        return pd.DataFrame()

def create_tick_bars(df: pd.DataFrame, tick_threshold: int) -> pd.DataFrame:
    """Create tick-based bars (constant number of ticks per bar)"""
    print(f"📊 Creating tick bars (threshold: {tick_threshold} ticks)...")
    
    bars = []
    
    for i in range(0, len(df), tick_threshold):
        chunk = df.iloc[i:i+tick_threshold]
        
        if len(chunk) == 0:
            continue
        
        bar = {
            'datetime': chunk['datetime'].iloc[-1],
            'open': chunk['price'].iloc[0], 'high': chunk['price'].max(),
            'low': chunk['price'].min(), 'close': chunk['price'].iloc[-1],
            'volume': chunk['quantity'].sum(),
            'volume_quote': (chunk['price'] * chunk['quantity']).sum(),
            'trade_count': len(chunk),
            'buy_volume': chunk[chunk['side'] == 'BUY']['quantity'].sum(),
            'sell_volume': chunk[chunk['side'] == 'SELL']['quantity'].sum(),
            'duration_seconds': (chunk['datetime'].iloc[-1] - chunk['datetime'].iloc[0]).total_seconds(),
            'symbol': chunk['symbol'].iloc[0]
        }
        
        bars.append(bar)
    
    if bars:
        bars_df = pd.DataFrame(bars)
        bars_df['volume_imbalance'] = (bars_df['buy_volume'] - bars_df['sell_volume']) / bars_df['volume']
        bars_df['avg_trade_size'] = bars_df['volume'] / bars_df['trade_count']
        bars_df['vwap'] = bars_df['volume_quote'] / bars_df['volume']
        bars_df['bar_type'] = 'tick'
        
        print(f"  ✅ {len(bars_df)} tick bars created")
        return bars_df
    else:
        print("  ❌ No tick bars created")
        return pd.DataFrame()

def calculate_tick_analytics(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate extended tick analytics"""
    print("📊 Calculating tick analytics...")
    
    df['minute'] = df['datetime'].dt.floor('min')
    
    analytics = df.groupby('minute').agg({
        'price': ['first', 'last', 'min', 'max', 'std', 'count'],
        'quantity': ['sum', 'mean', 'std'],
        'trade_id': 'count'
    }).reset_index()
    
    analytics.columns = [
        'datetime', 'price_open', 'price_close', 'price_min', 'price_max', 
        'price_std', 'price_count', 'volume_sum', 'volume_mean', 'volume_std', 'trade_count'
    ]
    
    # Price movements
    analytics['price_change'] = analytics['price_close'] - analytics['price_open']
    analytics['price_change_pct'] = (analytics['price_change'] / analytics['price_open']) * 100
    analytics['price_range'] = analytics['price_max'] - analytics['price_min']
    analytics['price_range_pct'] = (analytics['price_range'] / analytics['price_open']) * 100
    
    # Volume analysis
    minute_buy_vol = df[df['side'] == 'BUY'].groupby('minute')['quantity'].sum()
    minute_sell_vol = df[df['side'] == 'SELL'].groupby('minute')['quantity'].sum()
    
    analytics = analytics.set_index('datetime')
    analytics['buy_volume'] = minute_buy_vol.reindex(analytics.index, fill_value=0)
    analytics['sell_volume'] = minute_sell_vol.reindex(analytics.index, fill_value=0)
    analytics['volume_imbalance'] = (analytics['buy_volume'] - analytics['sell_volume']) / analytics['volume_sum']
    analytics = analytics.reset_index()
    
    # Market microstructure
    analytics['trades_per_second'] = analytics['trade_count'] / 60
    analytics['avg_trade_size'] = analytics['volume_sum'] / analytics['trade_count']
    analytics['volatility_proxy'] = analytics['price_std'] / analytics['price_open'] * 100
    analytics['symbol'] = df['symbol'].iloc[0]
    
    print(f"  ✅ Analytics for {len(analytics)} minutes calculated")
    return analytics

def save_transformed_data(data: pd.DataFrame, output_type: str, timeframe: str = None, 
                         symbol: str = SYMBOL, date_range: str = None):
    """Save transformed data as Parquet with tick-data catalog recognition"""
    if data.empty:
        print(f"  ⚠️ No data to save for {output_type}")
        return
    
    if date_range is None:
        date_range = f"{START_DATE}_to_{END_DATE}"
    
    filename = f"tick_{symbol}_{output_type}_{timeframe}_{date_range}.parquet" if timeframe else f"tick_{symbol}_{output_type}_{date_range}.parquet"
    output_path = OUTPUT_DIR / output_type / filename
    
    try:
        # Add metadata for tick-data recognition
        data_with_meta = data.copy()
        data_with_meta.attrs.update({
            'data_type': 'tick_data', 'source': 'binance', 'symbol': symbol,
            'date_range': date_range, 'transformation_type': output_type
        })
        if timeframe:
            data_with_meta.attrs['timeframe'] = timeframe
        
        data_with_meta.to_parquet(output_path, engine='pyarrow', compression='snappy', index=False)
        
        file_size = output_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ Tick-data saved: {filename} ({file_size:.1f} MB, {len(data):,} rows)")
        
    except Exception as e:
        print(f"  ❌ Save error for {filename}: {e}")

def create_tick_data_catalog(symbol: str, date_range: str):
    """Create tick-data catalog with all available transformations"""
    print("📚 Creating tick-data catalog...")
    
    catalog = {
        'symbol': symbol, 'date_range': date_range, 'data_type': 'tick_data_catalog',
        'created_at': datetime.now().isoformat(), 'datasets': {}
    }
    
    for subdir in ["bars", "volume_bars", "tick_bars", "analytics"]:
        subdir_path = OUTPUT_DIR / subdir
        if subdir_path.exists():
            tick_files = list(subdir_path.glob(f"tick_{symbol}_*.parquet"))
            
            if tick_files:
                catalog['datasets'][subdir] = []
                
                for file in tick_files:
                    try:
                        df = pd.read_parquet(file, columns=[])
                        
                        file_info = {
                            'filename': file.name,
                            'size_mb': round(file.stat().st_size / (1024 * 1024), 2),
                            'path': str(file.relative_to(OUTPUT_DIR)),
                            'transformation_type': subdir
                        }
                        
                        if hasattr(df, 'attrs'):
                            file_info.update(df.attrs)
                        
                        catalog['datasets'][subdir].append(file_info)
                        
                    except Exception as e:
                        print(f"  ⚠️ Error reading {file.name}: {e}")
    
    catalog_path = OUTPUT_DIR / f"tick_data_catalog_{symbol}_{date_range}.json"
    import json
    with open(catalog_path, 'w') as f:
        json.dump(catalog, f, indent=2)
    
    total_datasets = sum(len(files) for files in catalog['datasets'].values())
    print(f"  ✅ Tick-data catalog saved: {catalog_path.name}")
    print(f"  📊 {total_datasets} tick datasets cataloged")
    return catalog


def transform_tick_data():
    """Hauptfunktion: Transformiert kombinierte Tick-Daten"""
    
    print("🔄 TICK-DATEN TRANSFORMATION")
    print("=" * 60)
    print(f"Symbol: {SYMBOL}")
    print(f"Zeitraum: {START_DATE} bis {END_DATE}")
    print(f"Input: {INPUT_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)
    
    # Setup
    create_directories()
    
    # Finde kombinierte Tick-Datei
    tick_file = get_combined_tick_file(SYMBOL, START_DATE, END_DATE)
    if not tick_file:
        print("❌ Keine kombinierte Tick-Datei gefunden!")
        print(f"   Erwartete Datei: processed_tick_data_{SYMBOL}_{START_DATE}_to_{END_DATE}.parquet")
        return
    
    print(f"📁 Kombinierte Tick-Datei gefunden: {tick_file.name}")
    
    # Lade alle Tick-Daten
    df_ticks = load_combined_tick_data(tick_file)
    
    date_range = f"{START_DATE}_to_{END_DATE}"
    
    print(f"\n🔄 Starte Tick-Transformationen...")
    
    # 1. Zeit-basierte Bars für verschiedene Timeframes
    print(f"\n📊 Zeit-basierte Tick-Bars:")
    for tf_name, tf_code in TIMEFRAMES.items():
        try:
            bars = create_time_bars(df_ticks, tf_code)
            save_transformed_data(bars, "bars", tf_code, SYMBOL, date_range)
        except Exception as e:
            print(f"  ❌ Fehler bei {tf_name}: {e}")
    
    # 2. Volume-basierte Bars
    print(f"\n📊 Volume-basierte Tick-Bars:")
    avg_volume_per_minute = df_ticks['quantity'].sum() / (len(df_ticks) / df_ticks.groupby(df_ticks['datetime'].dt.floor('min')).ngroups)
    volume_thresholds = [
        avg_volume_per_minute * 0.5,  # 30s equivalent
        avg_volume_per_minute,        # 1min equivalent  
        avg_volume_per_minute * 5,    # 5min equivalent
        avg_volume_per_minute * 15    # 15min equivalent
    ]
    
    for i, threshold in enumerate(volume_thresholds):
        try:
            vol_bars = create_volume_bars(df_ticks, threshold)
            if not vol_bars.empty:
                save_transformed_data(vol_bars, "volume_bars", f"vol{i+1}", SYMBOL, date_range)
        except Exception as e:
            print(f"  ❌ Fehler bei Volume-Bars {i+1}: {e}")
    
    # 3. Tick-basierte Bars
    print(f"\n📊 Count-basierte Tick-Bars:")
    avg_ticks_per_minute = len(df_ticks) / df_ticks.groupby(df_ticks['datetime'].dt.floor('min')).ngroups
    tick_thresholds = [
        int(avg_ticks_per_minute * 0.5),  # 30s equivalent
        int(avg_ticks_per_minute),        # 1min equivalent
        int(avg_ticks_per_minute * 5),    # 5min equivalent
        int(avg_ticks_per_minute * 15)    # 15min equivalent
    ]
    
    for i, threshold in enumerate(tick_thresholds):
        try:
            tick_bars = create_tick_bars(df_ticks, threshold)
            if not tick_bars.empty:
                save_transformed_data(tick_bars, "tick_bars", f"tick{i+1}", SYMBOL, date_range)
        except Exception as e:
            print(f"  ❌ Fehler bei Tick-Bars {i+1}: {e}")
    
    # 4. Analytics
    print(f"\n📊 Tick-Analytics:")
    try:
        analytics = calculate_tick_analytics(df_ticks)
        save_transformed_data(analytics, "analytics", None, SYMBOL, date_range)
    except Exception as e:
        print(f"  ❌ Fehler bei Analytics: {e}")
    
    # 5. Tick-Data-Katalog
    print(f"\n� Tick-Data-Katalog:")
    try:
        catalog = create_tick_data_catalog(SYMBOL, date_range)
    except Exception as e:
        print(f"  ❌ Fehler bei Tick-Data-Katalog: {e}")
    
    # Final Summary
    print("\n" + "=" * 60)
    print("📊 TICK-TRANSFORMATION SUMMARY")
    print("=" * 60)
    
    total_files = 0
    total_size = 0
    
    for subdir in ["bars", "volume_bars", "tick_bars", "analytics"]:
        subdir_path = OUTPUT_DIR / subdir
        if subdir_path.exists():
            tick_files = list(subdir_path.glob(f"tick_{SYMBOL}_*.parquet"))
            subdir_size = sum(f.stat().st_size for f in tick_files) / (1024 * 1024)
            print(f"📁 {subdir}: {len(tick_files)} Tick-Datasets ({subdir_size:.1f} MB)")
            total_files += len(tick_files)
            total_size += subdir_size
    
    print(f"\n✅ Gesamt: {total_files} Tick-Datasets ({total_size:.1f} MB)")
    print(f"💾 Ausgabe: {OUTPUT_DIR}")
    print(f"📚 Katalog: tick_data_catalog_{SYMBOL}_{date_range}.json")
    print("\n🎯 Tick-Transformation abgeschlossen!")

if __name__ == "__main__":
    transform_tick_data()
