import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import requests
from typing import List, Optional

# API URLs
BASE_URL = "https://data.binance.vision/data/spot/daily/trades"
FUTURES_BASE_URL = "https://data.binance.vision/data/futures/um/daily/trades"

# Config
SYMBOL = "BTCUSDT"
START_DATE = "2024-01-01"
END_DATE = "2024-01-31"
MARKET_TYPE = "spot"

# Paths
DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "raw_tick_data"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data"

def create_directories():
    """Create required directories"""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Directories created:")
    print(f"  Download: {DOWNLOAD_DIR}")
    print(f"  Processed: {PROCESSED_DIR}")

def get_date_range(start_date: str, end_date: str) -> List[str]:
    """Generate list of dates between start and end"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates

def build_download_url(symbol: str, date: str, market_type: str = "spot") -> str:
    """Build download URL for tick data"""
    base_url = FUTURES_BASE_URL if market_type == "futures" else BASE_URL
    filename = f"{symbol}-trades-{date}.zip"
    return f"{base_url}/{symbol}/{filename}"

def download_tick_file(url: str, local_path: Path) -> bool:
    """Download tick file"""
    try:
        print(f"Downloading: {url}")
        response = requests.get(url, stream=True, timeout=60)
        if response.status_code == 200:
            with open(local_path, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            print(f"  ✅ Saved: {local_path.name}")
            return True
        else:
            print(f"  ❌ Error {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Download error: {e}")
        return False

def extract_zip_file(zip_path: Path, extract_dir: Path) -> Optional[Path]:
    """Extract ZIP and return CSV path"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        for file in extract_dir.glob("*.csv"):
            return file
        print(f"  ❌ No CSV found in {zip_path.name}")
        return None
    except Exception as e:
        print(f"  ❌ Extract error: {e}")
        return None

def process_tick_csv(csv_path: Path, symbol: str, date: str) -> Optional[pd.DataFrame]:
    """Process tick CSV to structured DataFrame"""
    try:
        print(f"  Processing: {csv_path.name}")
        
        df = pd.read_csv(
            csv_path,
            names=['trade_id', 'price', 'quantity', 'base_quantity', 'timestamp', 'is_buyer_maker'],
            dtype={
                'trade_id': 'int64', 'price': 'float64', 'quantity': 'float64', 
                'base_quantity': 'float64', 'timestamp': 'int64', 'is_buyer_maker': 'bool'
            }
        )
        
        if df.empty:
            print(f"  ❌ Empty CSV")
            return None
        
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['symbol'] = symbol
        df['date'] = date
        df['side'] = df['is_buyer_maker'].map({True: 'SELL', False: 'BUY'})
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        print(f"  ✅ {len(df):,} ticks processed")
        return df
        
    except Exception as e:
        print(f"  ❌ CSV processing error: {e}")
        return None

def save_combined_tick_data(all_dataframes: List[pd.DataFrame], symbol: str, start_date: str, end_date: str) -> bool:
    """Save all tick data as one combined Parquet file"""
    try:
        if not all_dataframes:
            print("  ❌ No data to save")
            return False
        
        print(f"📦 Combining {len(all_dataframes)} daily files...")
        
        combined_df = pd.concat(all_dataframes, ignore_index=True)
        combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
        
        columns_order = ['datetime', 'timestamp', 'symbol', 'trade_id', 'price', 'quantity', 'side', 'is_buyer_maker']
        df_output = combined_df[columns_order].copy()
        
        date_range = f"{start_date}_to_{end_date}"
        output_file = PROCESSED_DIR / f"processed_tick_data_{symbol}_{date_range}.parquet"
        
        df_output.to_parquet(output_file, engine='pyarrow', compression='snappy', index=False)
        
        file_size = output_file.stat().st_size / (1024 * 1024)
        print(f"  ✅ Combined file saved: {output_file.name}")
        print(f"  📊 {len(df_output):,} ticks ({file_size:.1f} MB)")
        
        # Metadata for catalog
        metadata = {
            'symbol': symbol, 'start_date': start_date, 'end_date': end_date,
            'market_type': MARKET_TYPE, 'total_ticks': len(df_output), 'date_range': date_range,
            'file_size_mb': round(file_size, 2), 'data_type': 'tick_data',
            'created_at': datetime.now().isoformat(), 'columns': list(df_output.columns),
            'time_range': {
                'start': df_output['datetime'].min().isoformat(),
                'end': df_output['datetime'].max().isoformat()
            }
        }
        
        metadata_file = PROCESSED_DIR / f"processed_tick_data_{symbol}_{date_range}_metadata.json"
        import json
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"  ✅ Metadata saved: {metadata_file.name}")
        return True
        
    except Exception as e:
        print(f"  ❌ Save error: {e}")
        return False

def cleanup_temp_files(temp_dir: Path):
    """Clean up temp files"""
    try:
        for file in temp_dir.glob("*"):
            if file.is_file():
                file.unlink()
        print(f"  🧹 Temp files cleaned")
    except Exception as e:
        print(f"  ⚠️ Cleanup warning: {e}")

def download_and_process_ticks():
    """Main function: Download and process all tick data"""
    
    print("🚀 BINANCE TICK DATA DOWNLOAD & PROCESSING")
    print("=" * 50)
    print(f"Symbol: {SYMBOL} | Period: {START_DATE} to {END_DATE} | Market: {MARKET_TYPE}")
    print("=" * 50)
    
    create_directories()
    dates = get_date_range(START_DATE, END_DATE)
    temp_dir = DOWNLOAD_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    total_files = len(dates)
    success_count = 0
    failed_count = 0
    total_ticks = 0
    all_dataframes = []
    
    print(f"\n📅 Processing {total_files} days...")
    
    for i, date in enumerate(dates, 1):
        print(f"\n[{i}/{total_files}] {date}")
        
        url = build_download_url(SYMBOL, date, MARKET_TYPE)
        zip_file = temp_dir / f"{SYMBOL}-trades-{date}.zip"
        
        if download_tick_file(url, zip_file):
            csv_file = extract_zip_file(zip_file, temp_dir)
            if csv_file:
                df = process_tick_csv(csv_file, SYMBOL, date)
                if df is not None:
                    all_dataframes.append(df)
                    success_count += 1
                    total_ticks += len(df)
                    print(f"  ✅ {len(df):,} ticks added to collection")
                else:
                    failed_count += 1
                
                if csv_file.exists():
                    csv_file.unlink()
            else:
                failed_count += 1
            
            if zip_file.exists():
                zip_file.unlink()
        else:
            failed_count += 1
    
    cleanup_temp_files(temp_dir)
    if temp_dir.exists():
        temp_dir.rmdir()
    
    print(f"\n💾 Saving combined tick data...")
    combined_success = save_combined_tick_data(all_dataframes, SYMBOL, START_DATE, END_DATE)
    
    print("\n" + "=" * 50)
    print("📊 DOWNLOAD SUMMARY")
    print("=" * 50)
    print(f"✅ Success: {success_count}/{total_files} days")
    print(f"❌ Failed: {failed_count}/{total_files} days")
    print(f"📈 Total ticks: {total_ticks:,}")
    
    if success_count > 0:
        avg_ticks = total_ticks // success_count
        print(f"📊 Average: {avg_ticks:,} ticks/day")
    
    if combined_success:
        date_range = f"{START_DATE}_to_{END_DATE}"
        print(f"✅ Combined file: processed_tick_data_{SYMBOL}_{date_range}.parquet")
    
    print(f"💾 Output: {PROCESSED_DIR}")
    print("\n🎯 Tick download completed!")

if __name__ == "__main__":
    download_and_process_ticks()
