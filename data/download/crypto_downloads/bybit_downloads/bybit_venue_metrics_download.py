from pathlib import Path
from datetime import datetime, date, timedelta
import pandas as pd
import os
import time
import requests
from typing import List, Dict, Any

from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_iso8601
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from data.download.crypto_downloads.custom_class.bybit_metrics_data import BybitMetricsData


# ============================================================================
# BYBIT API CONFIGURATION
# ============================================================================

BYBIT_API_BASE = "https://api.bybit.com/v5/market"
BYBIT_RATE_LIMIT_DELAY = 0.05  # 50ms between requests (20 req/sec)

BYBIT_ENDPOINTS = {
    "open_interest": f"{BYBIT_API_BASE}/open-interest",
    "account_ratio": f"{BYBIT_API_BASE}/account-ratio",  # Try account-ratio instead
    "funding_history": f"{BYBIT_API_BASE}/funding/history",
}

# Bybit interval codes (for time-series data)
BYBIT_INTERVALS = {
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def make_bybit_api_request(
    url: str,
    params: Dict[str, Any],
    max_retries: int = 3,
    delay: float = BYBIT_RATE_LIMIT_DELAY
) -> Dict[str, Any]:
    time.sleep(delay)
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Bybit V5 API uses retCode (not retMsg)
            if data.get("retCode") != 0:
                error_msg = data.get("retMsg", "Unknown error")
                raise ValueError(f"Bybit API error: {error_msg}")
                
            return data
            
        except (requests.exceptions.RequestException, ValueError) as e:
            if attempt == max_retries - 1:
                raise
            print(f"[WARN] Request failed (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(delay * (2 ** attempt))  # Exponential backoff
    
    raise RuntimeError("Should never reach here")


# ============================================================================
# MAIN DOWNLOADER CLASS
# ============================================================================

class BybitVenueMetricsDownloader:
    def __init__(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        base_data_dir: str,
        interval: str = "1h",  # Bybit supports 5min, 15min, 30min, 1h, 4h, 1d
        save_as_csv: bool = True,
        save_in_catalog: bool = True,
        csv_output_subdir: str | None = None,
    ):
        self.symbol = symbol  # e.g., SOLUSDT-LINEAR
        self.base_symbol = symbol.replace("-LINEAR", "")
        self.start_date_dt = self._to_date(start_date)
        self.end_date_dt = self._to_date(end_date)
        self.start_date = self.start_date_dt.isoformat()
        self.end_date = self.end_date_dt.isoformat()
        self.interval = interval
        self.base_data_dir = Path(base_data_dir)
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.csv_output_subdir = csv_output_subdir

        self.cache_dir = self.base_data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.processed_dir = self.cache_dir / f"processed_metrics_data_{self.start_date}_to_{self.end_date}" / "csv"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        self.catalog_path = self.base_data_dir / "data_catalog_wrangled"

    @staticmethod
    def _to_date(d):
        """Convert string or date to date object."""
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").date()
        raise TypeError("start_date/end_date must be str YYYY-MM-DD or datetime.date")

    def _download_open_interest(self) -> pd.DataFrame:
        print(f"[INFO] Downloading open interest for {self.base_symbol}...")
        
        start_ms = int(datetime.combine(self.start_date_dt, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(self.end_date_dt, datetime.max.time()).timestamp() * 1000)
        
        params = {
            "category": "linear",
            "symbol": self.base_symbol,
            "intervalTime": self.interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 200,  # Max per request
        }
        
        all_records = []
        cursor = None
        
        while True:
            if cursor:
                params["cursor"] = cursor
            
            try:
                data = make_bybit_api_request(BYBIT_ENDPOINTS["open_interest"], params)
            except Exception as e:
                print(f"[ERROR] Failed to download open interest: {e}")
                break
            
            result = data.get("result", {})
            records = result.get("list", [])
            
            if not records:
                break
            
            all_records.extend(records)
            print(f"[INFO] Downloaded {len(records)} open interest records (total: {len(all_records)})")
            
            cursor = result.get("nextPageCursor")
            if not cursor:
                break
        
        if not all_records:
            return pd.DataFrame(columns=["timestamp", "openInterest", "openInterestValue"])
        
        # Bybit format: [{"openInterest": "1234.56", "timestamp": "1704067200000"}]
        # Note: openInterestValue may not be present in all responses
        df = pd.DataFrame(all_records)
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("int64")
        df["openInterest"] = pd.to_numeric(df["openInterest"], errors="coerce")
        
        # Handle missing openInterestValue field
        if "openInterestValue" in df.columns:
            df["openInterestValue"] = pd.to_numeric(df["openInterestValue"], errors="coerce")
        else:
            df["openInterestValue"] = 0.0
            print("[WARN] openInterestValue not in API response, setting to 0")
        
        df = df.sort_values("timestamp")
        
        return df[["timestamp", "openInterest", "openInterestValue"]]

    def _download_account_ratio(self) -> pd.DataFrame:
        print(f"[INFO] Downloading account ratio for {self.base_symbol}...")
        
        start_ms = int(datetime.combine(self.start_date_dt, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(self.end_date_dt, datetime.max.time()).timestamp() * 1000)
        
        params = {
            "category": "linear",
            "symbol": self.base_symbol,
            "period": self.interval,
            "startTime": start_ms,  # Add start time
            "endTime": end_ms,      # Add end time
            "limit": 500,  # Max per request
        }
        
        all_records = []
        
        try:
            data = make_bybit_api_request(BYBIT_ENDPOINTS["account_ratio"], params)
        except Exception as e:
            print(f"[ERROR] Failed to download account ratio: {e}")
            return pd.DataFrame(columns=["timestamp", "longAccount", "shortAccount", "longShortRatio"])
        
        result = data.get("result", {})
        records = result.get("list", [])
        
        if not records:
            return pd.DataFrame(columns=["timestamp", "longAccount", "shortAccount", "longShortRatio"])
        
        all_records.extend(records)
        print(f"[INFO] Downloaded {len(records)} account ratio records")
        
        # Bybit format: [{"symbol": "BTCUSDT", "buyRatio": "0.52", "sellRatio": "0.48", "timestamp": "1704067200000"}]
        df = pd.DataFrame(all_records)
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("int64")
        
        # Handle missing ratio fields
        if "buyRatio" in df.columns:
            df["longAccount"] = pd.to_numeric(df["buyRatio"], errors="coerce")
        else:
            df["longAccount"] = 0.0
            print("[WARN] buyRatio not in API response")
            
        if "sellRatio" in df.columns:
            df["shortAccount"] = pd.to_numeric(df["sellRatio"], errors="coerce")
        else:
            df["shortAccount"] = 0.0
            print("[WARN] sellRatio not in API response")
            
        df["longShortRatio"] = df["longAccount"] / (df["shortAccount"] + 1e-10)  # Avoid division by zero
        
        # Filter to date range
        df = df[(df["timestamp"] >= start_ms) & (df["timestamp"] <= end_ms)]
        df = df.sort_values("timestamp")
        
        return df[["timestamp", "longAccount", "shortAccount", "longShortRatio"]]

    def _download_funding_history(self) -> pd.DataFrame:
        """
        Download funding rate history from Bybit.
        
        API: /v5/market/funding/history
        Parameters: category=linear, symbol, startTime, endTime
        
        Returns:
            DataFrame with columns: timestamp, fundingRate
        """
        print(f"[INFO] Downloading funding rate history for {self.base_symbol}...")
        
        start_ms = int(datetime.combine(self.start_date_dt, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(self.end_date_dt, datetime.max.time()).timestamp() * 1000)
        
        params = {
            "category": "linear",
            "symbol": self.base_symbol,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 200,  # Max per request
        }
        
        all_records = []
        
        try:
            data = make_bybit_api_request(BYBIT_ENDPOINTS["funding_history"], params)
        except Exception as e:
            print(f"[ERROR] Failed to download funding history: {e}")
            return pd.DataFrame(columns=["timestamp", "fundingRate"])
        
        result = data.get("result", {})
        records = result.get("list", [])
        
        if not records:
            return pd.DataFrame(columns=["timestamp", "fundingRate"])
        
        all_records.extend(records)
        print(f"[INFO] Downloaded {len(records)} funding rate records")
        
        # Bybit format: [{"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingRateTimestamp": "1704067200000"}]
        df = pd.DataFrame(all_records)
        df["timestamp"] = pd.to_numeric(df["fundingRateTimestamp"], errors="coerce").astype("int64")
        df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
        df = df.sort_values("timestamp")
        
        return df[["timestamp", "fundingRate"]]

    def _merge_metrics(
        self, 
        oi_df: pd.DataFrame, 
        ratio_df: pd.DataFrame, 
        funding_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Merge all metrics DataFrames on timestamp using outer join.
        
        Args:
            oi_df: Open interest DataFrame
            ratio_df: Account ratio DataFrame
            funding_df: Funding rate DataFrame
            
        Returns:
            Merged DataFrame with all metrics
        """
        print("[INFO] Merging metrics data...")
        
        # Start with open interest as base
        merged = oi_df.copy()
        
        # Merge account ratio
        if not ratio_df.empty:
            merged = pd.merge(merged, ratio_df, on="timestamp", how="outer")
        else:
            merged["longAccount"] = 0.0
            merged["shortAccount"] = 0.0
            merged["longShortRatio"] = 0.0
        
        # Merge funding rate
        if not funding_df.empty:
            merged = pd.merge(merged, funding_df, on="timestamp", how="outer")
        else:
            merged["fundingRate"] = 0.0
        
        # Sort by timestamp and forward-fill missing values
        merged = merged.sort_values("timestamp")
        merged = merged.ffill().fillna(0)  # Use ffill() instead of fillna(method="ffill")
        
        return merged

    def run(self) -> Dict[str, Any]:
        """
        Execute the full metrics download pipeline.
        
        Returns:
            Dict with download statistics
        """
        print(f"[INFO] Starting Bybit metrics download for {self.symbol}")
        print(f"[INFO] Date range: {self.start_date} to {self.end_date}")
        print(f"[INFO] Interval: {self.interval}")
        
        # Download all metrics
        oi_df = self._download_open_interest()
        ratio_df = self._download_account_ratio()
        funding_df = self._download_funding_history()
        
        # Merge into single DataFrame
        merged_df = self._merge_metrics(oi_df, ratio_df, funding_df)
        
        if merged_df.empty:
            print("[WARN] No metrics data downloaded")
            return {
                "records": 0,
                "catalog_written": False,
                "csv_written": False,
            }
        
        print(f"[INFO] Total merged records: {len(merged_df)}")
        
        # Create NautilusTrader BybitMetricsData objects
        instrument_id = InstrumentId(Symbol(self.symbol), Venue("BYBIT"))
        records = []
        csv_rows = []
        
        for _, row in merged_df.iterrows():
            ts_event = int(row["timestamp"]) * 1_000_000  # ms to ns
            
            # Create BybitMetricsData with available Bybit metrics
            md = BybitMetricsData(
                instrument_id=instrument_id,
                ts_event=ts_event,
                ts_init=ts_event,
                open_interest=float(row.get("openInterest", 0)),
                funding_rate=float(row.get("fundingRate", 0)),
                long_short_ratio=float(row.get("longShortRatio", 0)),
            )
            records.append(md)
            
            if self.save_as_csv:
                csv_rows.append({
                    "timestamp_nano": ts_event,
                    "timestamp_iso": unix_nanos_to_iso8601(ts_event),
                    "symbol": self.symbol,
                    "open_interest": row.get("openInterest", 0),
                    "funding_rate": row.get("fundingRate", 0),
                    "long_short_ratio": row.get("longShortRatio", 0),
                })
        
        # Save to catalog
        if self.save_in_catalog:
            self.catalog_path.mkdir(parents=True, exist_ok=True)
            catalog = ParquetDataCatalog(str(self.catalog_path))
            catalog.write_data(records)
            print(f"[INFO] Saved {len(records)} metrics to catalog")
        
        # Save to CSV
        if self.save_as_csv:
            subdir = self.csv_output_subdir or os.getenv("CSV_OUTPUT_SUBDIR") or "csv_data"
            out_dir = self.base_data_dir / subdir / self.symbol
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "METRICS.csv"
            pd.DataFrame(csv_rows).to_csv(out_path, index=False)
            print(f"[INFO] Saved CSV to {out_path}")
        
        return {
            "symbol": self.symbol,
            "records": len(records),
            "catalog_written": self.save_in_catalog,
            "csv_written": self.save_as_csv,
            "date_range": f"{self.start_date} to {self.end_date}",
        }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
    
    downloader = BybitVenueMetricsDownloader(
        symbol="BTCUSDT-LINEAR",  # Changed from -PERP to -LINEAR for Bybit
        start_date="2022-01-01",
        end_date="2025-10-18",
        base_data_dir=str(base_dir),
        interval="15min",
        save_as_csv=True,
        save_in_catalog=True,
    )
    
    info = downloader.run()
    print("\n" + "="*60)
    print("DOWNLOAD COMPLETE")
    print("="*60)
    for key, value in info.items():
        print(f"{key}: {value}")
