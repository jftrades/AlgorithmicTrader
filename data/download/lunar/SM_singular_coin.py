import requests
import pandas as pd
from datetime import datetime, date
from dotenv import load_dotenv
from pathlib import Path
import os
import shutil

load_dotenv()

# Configuration
FILTER_START_DATE = "2024-09-20"  
FILTER_END_DATE = "2024-09-30"
SYMBOL = "SOL" 

class LunarCrushDownloader:
    BASE_URL = "https://lunarcrush.com/api4/public/coins"

    def __init__(self, symbol, start_date, end_date, base_data_dir):
        load_dotenv()
        self.api_key = os.getenv("LUNARCRUSH_API_KEY")
        if not self.api_key:
            raise ValueError("[ERROR] No LUNARCRUSH_API_KEY found in .env file")

        self.symbol = symbol.upper()
        self.start_date_dt = self._to_date(start_date)
        self.end_date_dt = self._to_date(end_date)

        self.start_date_str = self.start_date_dt.isoformat()
        self.end_date_str = self.end_date_dt.isoformat()

        self.base_data_dir = Path(base_data_dir)
        self.temp_raw_download_dir = self.base_data_dir / "temp_lunarcrush_downloads"
        self.processed_dir = (
            self.base_data_dir
            / f"processed_lunarcrush_{self.start_date_str}_to_{self.end_date_str}"
            / "csv"
        )

        self.temp_raw_download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _to_date(self, d):
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").date()
        raise TypeError("[ERROR] Date must be string 'YYYY-MM-DD' or datetime.date object")

    def run(self):
        start_timestamp = int(datetime.combine(self.start_date_dt, datetime.min.time()).timestamp())
        end_timestamp = int(datetime.combine(self.end_date_dt, datetime.max.time()).timestamp())

        url = f"{self.BASE_URL}/{self.symbol}/time-series/v2"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {
            "bucket": "hour",
            "start": start_timestamp,
            "end": end_timestamp,
        }

        print(f"[INFO] {self.symbol}: Downloading LunarCrush data from {self.start_date_str} to {self.end_date_str}")
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                print(f"[ERROR] {self.symbol}: API returned {response.status_code} - {response.text}")
                return

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

            if not records:
                print(f"[SKIP] {self.symbol}: No data available on LunarCrush")
                return

            df = pd.DataFrame(records)

            # Save temporary file
            temp_path = (
                self.temp_raw_download_dir
                / f"{self.symbol}_lunarcrush_{self.start_date_str}_to_{self.end_date_str}.csv"
            )
            df.to_csv(temp_path, index=False)

            # Save final file
            combined_path = (
                self.processed_dir
                / f"{self.symbol}_LUNARCRUSH_{self.start_date_str}_to_{self.end_date_str}.csv"
            )
            df.to_csv(combined_path, index=False)
            print(f"[INFO] {self.symbol}: Successfully saved {len(df)} data points to {combined_path}")

            shutil.rmtree(self.temp_raw_download_dir, ignore_errors=True)

        except Exception as e:
            print(f"[ERROR] {self.symbol}: Download failed - {e}")
            return


if __name__ == "__main__":
    start_date = FILTER_START_DATE or "2025-09-01"
    end_date = FILTER_END_DATE or "2025-09-02"
    symbol = SYMBOL

    base_data_dir = str(Path(__file__).resolve().parents[2] / "DATA_STORAGE")

    print(f"[INFO] Starting LunarCrush download for {symbol}")
    print(f"[INFO] Date range: {start_date} to {end_date}")
    
    downloader = LunarCrushDownloader(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_data_dir=base_data_dir,
    )
    downloader.run()
    
    print("[INFO] Download process completed")
