from pathlib import Path
from datetime import datetime, timedelta
import csv
import json
import time
import os
import sys

# Add binance_downloads to path for third-party downloaders
sys.path.insert(0, str(Path(__file__).parent.parent / "binance_downloads"))

from bybit_main_download import BybitDataOrchestrator
from bybit_new_future_list_download import BybitLinearPerpetualFuturesDiscovery
from fear_and_greed_download import FearAndGreedDownloader


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
FUTURES_CSV = BASE_DATA_DIR / "project_future_scraper" / "new_bybit_linear_perpetual_futures.csv"

# CSV output subdirectory
CSV_OUTPUT_SUBDIR = "csv_data_all"
os.environ["CSV_OUTPUT_SUBDIR"] = CSV_OUTPUT_SUBDIR

# Discovery settings
RUN_DISCOVERY = True
DISCOVERY_WINDOW_START = "2025-01-01"
DISCOVERY_WINDOW_END = "2025-10-18"
DISCOVERY_ONLY_USDT = True

# Iteration settings
RANGE_DAYS = 28  # How many days to download after listing date
MAX_SYMBOLS = None  # Limit number of symbols (None = all)
SLEEP_SECONDS = 2  # Delay between symbols (rate limiting)

# Downloader toggles
RUN_LUNAR = False
RUN_VENUE = True
RUN_BYBIT = True
RUN_FNG = False

# Configuration for each downloader
FNG_INSTRUMENT_ID = "FNG-INDEX.BYBIT"
LUNAR_BUCKET = "hour"
BYBIT_DATATYPE = "bar"  # or "tick"
BYBIT_INTERVAL = "15m"
SAVE_AS_CSV = True
SAVE_IN_CATALOG = True
DOWNLOAD_IF_MISSING = True


# ============================================================================
# GLOBAL STATE
# ============================================================================

_fng_done = False
_fng_result = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _separator(title: str) -> str:
    line = "-" * 22
    return f"\n{line} {title.upper()} {line}"


def run_discovery_if_needed():
    if not RUN_DISCOVERY:
        print("[INFO] Discovery disabled, skipping...")
        return
    
    print(_separator("DISCOVERY START"))
    print(f"[INFO] Window: {DISCOVERY_WINDOW_START} to {DISCOVERY_WINDOW_END}")
    
    try:
        discovery = BybitLinearPerpetualFuturesDiscovery(
            start_date=DISCOVERY_WINDOW_START,
            end_date=DISCOVERY_WINDOW_END,
            only_usdt=DISCOVERY_ONLY_USDT,
        )
        results = discovery.run()
        print(f"[SUCCESS] Discovery found {len(results)} new futures")
    except Exception as e:
        print(f"[ERROR] Discovery failed: {e}")
        raise
    
    print(_separator("DISCOVERY DONE"))


def run_fng_once():
    global _fng_done, _fng_result
    
    if _fng_done or not RUN_FNG:
        return
    
    print(_separator(f"FEAR & GREED {DISCOVERY_WINDOW_START} -> {DISCOVERY_WINDOW_END}"))
    
    try:
        downloader = FearAndGreedDownloader(
            start_date=DISCOVERY_WINDOW_START,
            end_date=DISCOVERY_WINDOW_END,
            base_data_dir=str(BASE_DATA_DIR),
            instrument_id_str=FNG_INSTRUMENT_ID,
            limit=0,
            save_as_csv=SAVE_AS_CSV,
            save_in_catalog=SAVE_IN_CATALOG,
            download_if_missing=True,
            remove_processed=True,
            csv_output_subdir=CSV_OUTPUT_SUBDIR,
        )
        _fng_result = downloader.run()
        print(f"[SUCCESS] Fear & Greed: {_fng_result.get('records', 0)} records")
    except Exception as e:
        _fng_result = {"error": str(e)}
        print(f"[ERROR] Fear & Greed download failed: {e}")
    
    _fng_done = True
    print(_separator("FEAR & GREED DONE"))


def parse_launch_time(ts: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unknown date format: {ts}")


def load_futures_list(csv_path: Path) -> list:
    if not csv_path.exists():
        raise FileNotFoundError(f"Futures CSV not found: {csv_path}")
    
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ============================================================================
# MAIN ITERATION LOGIC
# ============================================================================

def iterate_symbols():
    # Step 1: Discovery
    run_discovery_if_needed()
    
    # Step 2: Load futures list
    print(f"\n[INFO] Loading futures list from: {FUTURES_CSV}")
    rows = load_futures_list(FUTURES_CSV)
    
    # Step 3: Fear & Greed (once for all symbols)
    run_fng_once()
    
    # Step 4: Iterate symbols
    summaries = []
    total = len(rows) if MAX_SYMBOLS is None else min(MAX_SYMBOLS, len(rows))
    
    print(f"\n[INFO] Starting iteration over {total} symbols (of {len(rows)} listed)")
    print("="*80)
    
    for idx, row in enumerate(rows, 1):
        if MAX_SYMBOLS and idx > MAX_SYMBOLS:
            break
        
        symbol = row["symbol"]
        
        # Parse launch time
        try:
            launch_dt = parse_launch_time(row["launchTime"])
        except Exception as e:
            print(f"[SKIP] {symbol}: Failed to parse launch time - {e}")
            continue
        
        # Calculate date range
        start_date = launch_dt.date()
        end_date = start_date + timedelta(days=RANGE_DAYS - 1)
        
        print(_separator(f"SYMBOL {idx}/{total}: {symbol}"))
        print(f"[INFO] Launch: {launch_dt}")
        print(f"[INFO] Range: {start_date} to {end_date} ({RANGE_DAYS} days)")
        
        # Create orchestrator
        orchestrator = BybitDataOrchestrator(
            symbol=symbol,  # Will be normalized to -LINEAR format
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            base_data_dir=str(BASE_DATA_DIR),
            run_lunar=RUN_LUNAR,
            run_venue=RUN_VENUE,
            run_bybit=RUN_BYBIT,
            lunar_bucket=LUNAR_BUCKET,
            bybit_datatype=BYBIT_DATATYPE,
            bybit_interval=BYBIT_INTERVAL,
            save_as_csv=SAVE_AS_CSV,
            save_in_catalog=SAVE_IN_CATALOG,
            download_if_missing=DOWNLOAD_IF_MISSING,
            run_fng=False,  # Already done once globally
            fng_instrument_id=FNG_INSTRUMENT_ID,
            csv_output_subdir=CSV_OUTPUT_SUBDIR,
        )
        
        # Run downloaders with visible sections
        results = {}
        
        if RUN_LUNAR:
            print(_separator("LUNAR START"))
            results["lunar"] = orchestrator.run_lunar_metrics()
            print(_separator("LUNAR DONE"))
        
        if RUN_VENUE:
            print(_separator("VENUE METRICS START"))
            results["venue_metrics"] = orchestrator.run_venue_metrics()
            print(_separator("VENUE METRICS DONE"))
        
        if RUN_BYBIT:
            print(_separator(f"BYBIT {BYBIT_DATATYPE.upper()} START"))
            results["bybit_data"] = orchestrator.run_bybit_data()
            print(_separator(f"BYBIT {BYBIT_DATATYPE.upper()} DONE"))
        
        # Create summary
        summary = {
            "input": {
                "symbol_input": orchestrator.symbol,
                "normalized_base": orchestrator.base_symbol,
                "normalized_linear": orchestrator.linear_symbol,
                "launch_time": row["launchTime"],
                "start": orchestrator.start,
                "end": orchestrator.end,
            },
            "results": results,
        }
        
        # Add global Fear & Greed result
        if _fng_result and "fear_greed_global" not in summary:
            summary["fear_greed_global"] = _fng_result
        
        summaries.append(summary)
        
        # Save progress after each symbol
        output_json = BASE_DATA_DIR / "bybit_iteration_results.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(summaries, f, indent=2)
        
        print(f"\n[SUCCESS] {symbol} completed")
        print(f"[INFO] Progress saved to: {output_json}")
        
        # Rate limiting
        if idx < total:
            print(f"[INFO] Sleeping {SLEEP_SECONDS}s before next symbol...")
            time.sleep(SLEEP_SECONDS)
    
    print("\n" + "="*80)
    print(f"[INFO] Iteration complete: {len(summaries)} symbols processed")
    print("="*80)
    
    return summaries


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("="*80)
    print("BYBIT ITERATION DOWNLOADER")
    print("="*80)
    print(f"Configuration:")
    print(f"  Base Dir: {BASE_DATA_DIR}")
    print(f"  Futures CSV: {FUTURES_CSV}")
    print(f"  Discovery: {RUN_DISCOVERY}")
    print(f"  Window: {DISCOVERY_WINDOW_START} to {DISCOVERY_WINDOW_END}")
    print(f"  Range per Symbol: {RANGE_DAYS} days")
    print(f"  Max Symbols: {MAX_SYMBOLS or 'All'}")
    print(f"  Downloaders: Lunar={RUN_LUNAR}, Venue={RUN_VENUE}, "
          f"Bybit={RUN_BYBIT}, FnG={RUN_FNG}")
    print("="*80)
    
    try:
        results = iterate_symbols()
        print(f"\n[SUCCESS] All done! Processed {len(results)} symbols")
    except Exception as e:
        print(f"\n[ERROR] Iteration failed: {e}")
        import traceback
        traceback.print_exc()
