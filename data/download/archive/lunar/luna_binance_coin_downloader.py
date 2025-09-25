# Step 1: Read the data from the C:\Users\Ferdi\Desktop\projectx\AlgorithmicTrader\data\DATA_STORAGE\project_future_scraper perpet futures 
# Step 2: use the ts and coin data and fill them up to then also download the lunar crush data for the coins
# Step 3 : Save the lunar crush data in the DATA_STORAGE/lunar_crush folder

from data.download.custom_data_nautilius.load_lunar_to_catalog import load_lunar_csv_to_catalog
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
        
        self.temp_path = self.base_data_dir / "temp_lunar"
        self.temp_path.mkdir(parents=True, exist_ok=True)
        
        self.catalog_path = str(self.base_data_dir / "data_catalog_wrangled")

    def run(self):
        if not self.api_key:
            print(f"[ERROR] {self.symbol}: No API key found")
            return
        if self.end_date <= self.start_date:
            print(f"[ERROR] {self.symbol}: Invalid date range")
            return
        
        print(f"[INFO] {self.symbol}: Downloading LunarCrush data from {self.start_date} to {self.end_date}...")

        coin_symbol = self.symbol[:-4].lower() if self.symbol.endswith('USDT') else self.symbol.lower()

        df = self.download_lunarcrush_data(coin_symbol)
        if df is not None and not df.empty:
            self.save_to_catalog(df, coin_symbol)
            print(f"[INFO] {self.symbol}: Successfully saved {len(df)} data points")
        else:
            print(f"[SKIP] {self.symbol}: No data available on LunarCrush")
    
    def download_lunarcrush_data(self, coin_symbol):
        start_timestamp = int(self.start_date.timestamp())
        end_timestamp = int(self.end_date.timestamp())
        
        url = f"https://lunarcrush.com/api4/public/coins/{coin_symbol}/time-series/v2"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"bucket": "hour", "start": start_timestamp, "end": end_timestamp}
        
        try:
            response = requests.get(url, headers=headers, params=params)         
            time.sleep(1)  # Reduced sleep time

            if response.status_code == 200:
                data = response.json()
                records = []
                
                for point in data.get("data", []):
                    records.append({
                        "timestamp": point.get("time", 0),
                        "datetime": datetime.fromtimestamp(point.get("time", 0)).strftime('%Y-%m-%d %H:%M:%S'),
                        "contributors_active": point.get("contributors_active", 0),
                        "contributors_created": point.get("contributors_created", 0),
                        "interactions": point.get("interactions", 0),
                        "posts_active": point.get("posts_active", 0),
                        "posts_created": point.get("posts_created", 0),
                        "sentiment": point.get("sentiment", 0.0),
                        "spam": point.get("spam", 0),
                        "alt_rank": point.get("alt_rank", 0),
                        "circulating_supply": point.get("circulating_supply", 0.0),
                        "close": point.get("close", 0.0),
                        "galaxy_score": point.get("galaxy_score", 0.0),
                        "high": point.get("high", 0.0),
                        "low": point.get("low", 0.0),
                        "market_cap": point.get("market_cap", 0.0),
                        "market_dominance": point.get("market_dominance", 0.0),
                        "open": point.get("open", 0.0),
                        "social_dominance": point.get("social_dominance", 0.0),
                        "volume_24h": point.get("volume_24h", 0.0),
                    })
                
                return pd.DataFrame(records) if records else None
            else:
                print(f"[ERROR] {self.symbol}: API returned {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[ERROR] {self.symbol}: Download failed - {e}")
            return None
        
    def save_to_catalog(self, df, coin_symbol):
        filename = f"{coin_symbol}_{self.start_date.strftime('%Y%m%d')}_to_{self.end_date.strftime('%Y%m%d')}.csv"
        temp_csv = self.temp_path / filename
        
        df.to_csv(temp_csv, index=False)
        
        instrument_symbol = f"{coin_symbol.upper()}USDT-PERP"
        load_lunar_csv_to_catalog(
            csv_path=str(temp_csv),
            catalog_path=self.catalog_path,
            instrument_str=instrument_symbol
        )
        
        temp_csv.unlink()


def parse_listing_date(date_str):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Date {date_str} is not in a recognized format")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2] / "DATA_STORAGE"
    coins_file = base_dir / "project_future_scraper" / "new_binance_perpetual_futures.csv"
    
    if not coins_file.exists():
        print(f"[ERROR] Coins file not found: {coins_file}")
        exit(1)
    
    with open(coins_file, "r") as f:
        futures_list = list(csv.DictReader(f))
    
    filtered_futures = []
    for row in futures_list:
        try:
            # Fixed: Use "onboardDate" instead of "listing_date"
            listing_date_datetime = parse_listing_date(row["onboardDate"])

            if FILTER_START_DATE and listing_date_datetime < datetime.strptime(FILTER_START_DATE, "%Y-%m-%d"):
                continue
            if FILTER_END_DATE and listing_date_datetime > datetime.strptime(FILTER_END_DATE, "%Y-%m-%d"):
                continue

            row["listing_date_datetime"] = listing_date_datetime
            filtered_futures.append(row)
            
        except ValueError as e:
            print(f"[ERROR] {e}")
            continue
    
    print(f"[INFO] Processing {len(filtered_futures)} futures contracts...")
    
    for i, row in enumerate(filtered_futures, 1):
        print(f"\n[{i}/{len(filtered_futures)}] Processing {row['symbol']}...")
        
        downloader = LunaDataCoinDownloader(
            symbol=row["symbol"],
            listing_date=row["listing_date_datetime"],
            base_data_dir=str(base_dir),
            interval="1h"
        )
        downloader.run()
        
        if i < len(filtered_futures):
            print("⏱️  Waiting 5s for rate limit...")
            time.sleep(5)
    
    print("\n[INFO] All futures processed!")