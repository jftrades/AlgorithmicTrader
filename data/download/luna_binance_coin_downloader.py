# Step 1: Read the data from the C:\Users\Ferdi\Desktop\projectx\AlgorithmicTrader\data\DATA_STORAGE\project_future_scraper perpet futures 
# Step 2: use the ts and coin data and fill them up to then also download the lunar crush data for the coins
# Step 3 : Save the lunar crush data in the DATA_STORAGE/lunar_crush folder

from data.download.download_logic_crypto import find_csv_file
from pathlib import Path
from datetime import datetime, timedelta
import csv
import pandas as pd
import requests
from dotenv import load_dotenv
import os
import time

load_dotenv()

FILTER_START_DATE = "2024-09-20"  
FILTER_END_DATE = "2024-09-30" 


class LunaDataCoinDownloader:
    def __init__(self, symbol, listing_date, base_data_dir, interval):
        self.symbol = symbol
        self.start_date = listing_date
        self.end_date = listing_date + timedelta(days=14)
        self.base_data_dir = Path(base_data_dir)
        self.interval = interval
        self.api_key = os.getenv("LUNARCRUSH_API_KEY")
        
        self.storage_path = self.base_data_dir / "data_catalog_wrangled" / "data" / "SM_metrics"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        
    def run(self):
        if not self.api_key:
            return
        if self.end_date <= self.start_date:
            return
        
        print(f"[INFO] {self.symbol}: Downloading LunarCrush data from {self.start_date} to {self.end_date}...")

        coin_symbol = self.symbol[:-4].lower() if self.symbol.endswith('USDT') else self.symbol.lower()

        df = self.download_lunarcrush_data(coin_symbol)
        if df is not None and not df.empty:
            self.save_data_files(df, coin_symbol)
            print(f"[INFO] {self.symbol}: Successfully saved {len(df)} data points")
        else:
            print(f"[SKIP] {self.symbol}: No data available on LunarCrush")
    
    def download_lunarcrush_data(self, coin_symbol):
        start_timestamp = int(self.start_date.timestamp())
        end_timestamp = int(self.end_date.timestamp())
        
        url = f"https://lunarcrush.com/api4/public/coins/{coin_symbol}/time-series/v2"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {
            "bucket": "hour",
            "start": start_timestamp,
            "end": end_timestamp
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                records = []
                
                for point in data.get('data', []):
                    records.append({
                        'timestamp': point.get('time'),
                        'datetime': datetime.fromtimestamp(point.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                        'contributors_active': point.get('contributors_active', 0),
                        'contributors_created': point.get('contributors_created', 0),
                        'interactions': point.get('interactions', 0),
                        'posts_active': point.get('posts_active', 0),
                        'posts_created': point.get('posts_created', 0),
                        'sentiment': point.get('sentiment', 0),
                    })
                
                return pd.DataFrame(records) if records else None
            else:
                print(f"[ERROR] {self.symbol}: API returned {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[ERROR] {self.symbol}: Download failed - {e}")
            return None
        
    def save_data_files(self, df, coin_symbol):
        start_str = self.start_date.strftime("%Y-%m-%d")
        end_str = self.end_date.strftime("%Y-%m-%d")
        
        filename_base = f"{coin_symbol}_{start_str}_to_{end_str}"
        
        csv_file = self.storage_path / f"{filename_base}.csv"
        df.to_csv(csv_file, index=False)
        
        parquet_file = self.storage_path / f"{filename_base}.parquet"
        df.to_parquet(parquet_file, index=False)
        csv_file.unlink()

        
        print(f"[INFO] {self.symbol}: Saved to {csv_file} and {parquet_file}")

            
if __name__ == "__main__":
    base_data_dir = str(Path(__file__).resolve().parents[1] / "DATA_STORAGE")
    csv_path = Path(__file__).parent.parent / "DATA_STORAGE" / "project_future_scraper" / "new_binance_perpetual_futures.csv"
    
    RATE_LIMIT_DELAY = 5
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        futures_list = list(reader)

    # Filter by date range if configured
    if FILTER_START_DATE or FILTER_END_DATE:
        filtered_list = []
        for row in futures_list:
            listing_date = datetime.strptime(row["onboardDate"], "%Y-%m-%d %H:%M:%S")
            
            # Check if within date range
            if FILTER_START_DATE:
                filter_start = datetime.strptime(FILTER_START_DATE, "%Y-%m-%d")
                if listing_date < filter_start:
                    continue
                    
            if FILTER_END_DATE:
                filter_end = datetime.strptime(FILTER_END_DATE, "%Y-%m-%d")
                if listing_date > filter_end:
                    continue
                    
            filtered_list.append(row)
        
        futures_list = filtered_list
    
    for i, row in enumerate(futures_list, 1):
        symbol = row["symbol"]
        listing_date = datetime.strptime(row["onboardDate"], "%Y-%m-%d %H:%M:%S")
        
        print(f"\n[{i}/{len(futures_list)}] Processing {symbol}...")
        
        downloader = LunaDataCoinDownloader(
            symbol=symbol,
            listing_date=listing_date,
            base_data_dir=base_data_dir,
            interval="1h"  # LunarCrush uses hourly data
        )
        downloader.run()
        
        if i < len(futures_list):
                print(f"⏱️  Waiting {RATE_LIMIT_DELAY}s for rate limit...")
                time.sleep(RATE_LIMIT_DELAY)
            
