import csv
import requests
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any


# ============================================================================
# BYBIT API CONFIGURATION
# ============================================================================

BYBIT_API_BASE = "https://api.bybit.com/v5/market"
BYBIT_INSTRUMENTS_URL = f"{BYBIT_API_BASE}/instruments-info"
BYBIT_RATE_LIMIT_DELAY = 0.05  # 50ms between requests

DEFAULT_OUTPUT_SUBDIR = "project_future_scraper"
DEFAULT_OUTPUT_FILENAME = "new_bybit_linear_perpetual_futures.csv"


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
# MAIN DISCOVERY CLASS
# ============================================================================

class BybitLinearPerpetualFuturesDiscovery:
    def __init__(
        self,
        start_date: str,  # Window start YYYY-MM-DD
        end_date: str,    # Window end YYYY-MM-DD (inclusive)
        only_usdt: bool = True,
        output_subdir: str = DEFAULT_OUTPUT_SUBDIR,
        output_filename: str = DEFAULT_OUTPUT_FILENAME,
    ):
        self.start_dt = self._parse_date(start_date)
        self.end_dt = self._parse_date(end_date)
        
        if self.end_dt < self.start_dt:
            raise ValueError("end_date must be >= start_date")
        
        self.only_usdt = only_usdt
        self.output_subdir = output_subdir
        self.output_filename = output_filename
        
        # Convert dates to timestamps
        self.start_ts = int(datetime.combine(self.start_dt, datetime.min.time()).timestamp() * 1000)
        self.end_ts = int(datetime.combine(self.end_dt, datetime.max.time()).timestamp() * 1000)
        
        print(f"[INFO] Discovery window: {start_date} to {end_date}")
        print(f"[INFO] Timestamp range: {self.start_ts} to {self.end_ts}")

    @staticmethod
    def _parse_date(s: str):
        return datetime.strptime(s, "%Y-%m-%d").date()

    def _fetch_all_instruments(self) -> List[Dict[str, Any]]:
        print("[INFO] Fetching instruments from Bybit...")
        
        params = {
            "category": "linear",
            "limit": 1000,  # Max per request
        }
        
        all_instruments = []
        cursor = None
        page = 0
        
        while True:
            page += 1
            if cursor:
                params["cursor"] = cursor
            
            try:
                data = make_bybit_api_request(BYBIT_INSTRUMENTS_URL, params)
            except Exception as e:
                print(f"[ERROR] Failed to fetch instruments: {e}")
                break
            
            result = data.get("result", {})
            instruments = result.get("list", [])
            
            if not instruments:
                break
            
            all_instruments.extend(instruments)
            print(f"[INFO] Page {page}: {len(instruments)} instruments (total: {len(all_instruments)})")
            
            cursor = result.get("nextPageCursor")
            if not cursor:
                break
        
        print(f"[INFO] Total instruments fetched: {len(all_instruments)}")
        return all_instruments

    def discover(self) -> List[Dict[str, str]]:
        instruments = self._fetch_all_instruments()
        new_futures: List[Dict[str, str]] = []
        
        for inst in instruments:
            # Check if it's a perpetual contract
            contract_type = inst.get("contractType", "")
            if contract_type != "LinearPerpetual":
                continue
            
            # Get launch time
            launch_time_str = inst.get("launchTime")
            if not launch_time_str:
                continue
            
            try:
                # Bybit launchTime is milliseconds timestamp as string
                launch_ms = int(launch_time_str)
            except (ValueError, TypeError):
                continue
            
            # Check if within date range
            if not (self.start_ts <= launch_ms <= self.end_ts):
                continue
            
            symbol = inst.get("symbol", "")
            
            # Filter USDT only if requested
            if self.only_usdt and not symbol.endswith("USDT"):
                continue
            
            # Format launch time
            launch_dt = datetime.fromtimestamp(launch_ms / 1000, tz=timezone.utc)
            
            new_futures.append({
                "symbol": symbol,
                "launchTime": launch_dt.strftime("%Y-%m-%d %H:%M:%S"),
            })
        
        # Sort by launch time
        new_futures.sort(key=lambda x: x["launchTime"])
        
        print(f"\n[INFO] Found {len(new_futures)} new futures in date range")
        print("[INFO] Last 10 entries (filtered within window):")
        for fut in new_futures[-10:]:
            print(f"  {fut['symbol']}: {fut['launchTime']}")
        
        return new_futures

    def save(self, rows: List[Dict[str, str]], data_root: Path) -> Path:
        target_dir = data_root / self.output_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / self.output_filename
        
        with open(target_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "launchTime"])
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"\n[INFO] Saved {len(rows)} entries to: {target_path}")
        return target_path

    def run(self) -> List[Dict[str, str]]:
        rows = self.discover()
        data_root = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
        self.save(rows, data_root)
        return rows


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("BYBIT LINEAR PERPETUAL FUTURES DISCOVERY")
    print("="*60)
    
    # Example: Discover futures launched in January 2024
    discovery = BybitLinearPerpetualFuturesDiscovery(
        start_date="2024-01-01",
        end_date="2024-01-31",
        only_usdt=True,
    )
    
    try:
        results = discovery.run()
        print(f"\n[SUCCESS] Discovery complete: {len(results)} futures found")
    except Exception as e:
        print(f"\n[ERROR] Discovery failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("="*60)
    print("FINISHED")
    print("="*60)
