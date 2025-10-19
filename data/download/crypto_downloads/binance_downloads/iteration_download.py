from pathlib import Path
from datetime import datetime, timedelta
import csv
import json
import time
import os  # NEU

from main_download import CryptoDataOrchestrator
from new_future_list_download import BinancePerpetualFuturesDiscovery  # NEU
from fear_and_greed_download import FearAndGreedDownloader  # NEU

# ========================
# Konfiguration
# ========================
BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE" 
FUTURES_CSV = BASE_DATA_DIR / "project_future_scraper" / "new_binance_perpetual_futures.csv"

# NEU: Konfigurierbarer Zielordner (statt fest 'csv_data')
CSV_OUTPUT_SUBDIR = "csv_data_all"  # bei Bedarf z.B. "csv_data_alt" setzen
os.environ["CSV_OUTPUT_SUBDIR"] = CSV_OUTPUT_SUBDIR  # für Downloader verfügbar

RUN_DISCOVERY = True                 # NEU: führe Discovery vor Iteration aus
DISCOVERY_WINDOW_START = "2024-01-01"
DISCOVERY_WINDOW_END = "2025-10-07"
DISCOVERY_ONLY_USDT = True

RANGE_DAYS = 28
MAX_SYMBOLS = None
SLEEP_SECONDS = 1

RUN_LUNAR = False
RUN_VENUE = True
RUN_BINANCE = True

RUN_FNG = False  # NEU
FNG_INSTRUMENT_ID = "FNG-INDEX.BINANCE"  # NEU

LUNAR_BUCKET = "hour"
BINANCE_DATATYPE = "bar"
BINANCE_INTERVAL = "15m"
SAVE_AS_CSV = True
SAVE_IN_CATALOG = True
DOWNLOAD_IF_MISSING = True
# Entfernt: RUN_NEW_FUTURES und Fenster in Orchestrator
# ========================

# NEU: Ergebnis Cache
_fng_done = False
_fng_result = None

# NEU: Helper für formatierte Trenner
def _sep(title: str) -> str:
    line = "-" * 22
    return f"\n{line} {title.upper()} {line}"

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

def run_fng_once():
    global _fng_done, _fng_result
    if _fng_done or not RUN_FNG:
        return
    print(_sep(f"FEAR & GREED WINDOW {DISCOVERY_WINDOW_START} -> {DISCOVERY_WINDOW_END}"))
    try:
        dl = FearAndGreedDownloader(
            start_date=DISCOVERY_WINDOW_START,
            end_date=DISCOVERY_WINDOW_END,
            base_data_dir=str(BASE_DATA_DIR),
            instrument_id_str=FNG_INSTRUMENT_ID,
            limit=0,
            save_as_csv=SAVE_AS_CSV,
            save_in_catalog=SAVE_IN_CATALOG,
            download_if_missing=True,
            remove_processed=True,
            csv_output_subdir=CSV_OUTPUT_SUBDIR,  # NEU
        )
        _fng_result = dl.run()
        print(f"[OK] Fear & Greed geladen: records={_fng_result.get('records')}")
    except Exception as e:
        _fng_result = {"error": str(e)}
        print(f"[ERROR] Fear & Greed Download: {e}")
    _fng_done = True

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
    run_fng_once()  # NEU: vor Symbolen
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
        print(_sep(f"SYMBOL {idx}/{total}: {symbol}  RANGE {start_date} -> {end_date}"))
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
            run_fng=False,                    # NEU: pro Symbol deaktiviert
            fng_instrument_id=FNG_INSTRUMENT_ID,
            csv_output_subdir=CSV_OUTPUT_SUBDIR,  # NEU
        )
        # NEU: Statt orch.run() modulare Ausführung mit sichtbaren Sektionen
        results = {}
        if RUN_LUNAR:
            print(_sep("LUNAR START"))
            results["lunar"] = orch.run_lunar_metrics()
            print(_sep("LUNAR DONE"))
        if RUN_VENUE:
            print(_sep("VENUE METRICS START"))
            results["venue_metrics"] = orch.run_venue_metrics()
            print(_sep("VENUE METRICS DONE"))
        if RUN_BINANCE:
            print(_sep(f"BINANCE {BINANCE_DATATYPE.upper()} START"))
            results["binance_data"] = orch.run_binance_data()
            print(_sep(f"BINANCE {BINANCE_DATATYPE.upper()} DONE"))
        summary = {
            "input": {
                "symbol_input": orch.symbol,
                "normalized_base": orch.base_symbol,
                "normalized_perp": orch.perp_symbol,
                "start": orch.start,
                "end": orch.end,
            },
            "results": results,
        }
        # NEU: Fear & Greed global anhängen
        if _fng_result and "fear_greed_global" not in summary:
            summary["fear_greed_global"] = _fng_result
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
