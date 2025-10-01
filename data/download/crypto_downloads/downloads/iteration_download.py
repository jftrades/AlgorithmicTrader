from pathlib import Path
from datetime import datetime, timedelta
import csv
import json
import time

from main_download import CryptoDataOrchestrator
from new_future_list_download import BinancePerpetualFuturesDiscovery  # NEU

# ========================
# Konfiguration
# ========================
BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
FUTURES_CSV = BASE_DATA_DIR / "project_future_scraper" / "new_binance_perpetual_futures.csv"

RUN_DISCOVERY = True                
DISCOVERY_WINDOW_START = "2024-01-01"
DISCOVERY_WINDOW_END = "2024-01-30"
DISCOVERY_ONLY_USDT = True

RANGE_DAYS = 20
MAX_SYMBOLS = None
SLEEP_SECONDS = 2

RUN_LUNAR = True
RUN_VENUE = True
RUN_BINANCE = True

LUNAR_BUCKET = "hour"
BINANCE_DATATYPE = "bar"
BINANCE_INTERVAL = "15m"
SAVE_AS_CSV = True
SAVE_IN_CATALOG = True
DOWNLOAD_IF_MISSING = True
# Entfernt: RUN_NEW_FUTURES und Fenster in Orchestrator
# ========================

def run_discovery_if_needed():
    if not RUN_DISCOVERY:
        return
    print("[INFO] Starte Discovery vor Iteration ...")
    d = BinancePerpetualFuturesDiscovery(
        start_date=DISCOVERY_WINDOW_START,
        end_date=DISCOVERY_WINDOW_END,
        only_usdt=DISCOVERY_ONLY_USDT,
    )
    d.run()

def parse_onboard(ts: str):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unbekanntes Datumsformat: {ts}")

def load_futures(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"Futures CSV fehlt: {csv_path}")
    with open(csv_path, "r", newline="") as f:
        return list(csv.DictReader(f))

def iterate_symbols():
    run_discovery_if_needed()
    rows = load_futures(FUTURES_CSV)
    summaries = []
    total = len(rows) if MAX_SYMBOLS is None else min(MAX_SYMBOLS, len(rows))
    print(f"[INFO] Starte Iteration über {total} Symbole (von {len(rows)} gelistet).")
    for idx, row in enumerate(rows, 1):
        if MAX_SYMBOLS and idx > MAX_SYMBOLS:
            break
        symbol = row["symbol"]
        try:
            onboard_dt = parse_onboard(row["onboardDate"])
        except Exception as e:
            print(f"[SKIP] {symbol}: {e}")
            continue
        start_date = onboard_dt.date()
        end_date = start_date + timedelta(days=RANGE_DAYS - 1)
        print(f"\n[{idx}/{total}] {symbol} -> {start_date} bis {end_date}")
        orch = CryptoDataOrchestrator(
            symbol=symbol,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            base_data_dir=str(BASE_DATA_DIR),
            run_lunar=RUN_LUNAR,
            run_venue=RUN_VENUE,
            run_binance=RUN_BINANCE,
            lunar_bucket=LUNAR_BUCKET,
            binance_datatype=BINANCE_DATATYPE,
            binance_interval=BINANCE_INTERVAL,
            save_as_csv=SAVE_AS_CSV,
            save_in_catalog=SAVE_IN_CATALOG,
            download_if_missing=DOWNLOAD_IF_MISSING,
        )
        summary = orch.run()
        summaries.append(summary)
        out_json = BASE_DATA_DIR / "iteration_results.json"
        with open(out_json, "w", encoding="utf-8") as jf:
            json.dump(summaries, jf, indent=2)
        print(f"[OK] {symbol} abgeschlossen. Zwischenergebnis gespeichert.")
        if idx < total:
            time.sleep(SLEEP_SECONDS)
    print("\n[INFO] Iteration fertig.")
    return summaries

if __name__ == "__main__":
    iterate_symbols()
