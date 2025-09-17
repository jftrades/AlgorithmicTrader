"""
Discovery-Skript für neu gelistete Binance Perpetual Futures in einem gegebenen Zeitfenster (inklusive).
"""
from __future__ import annotations
# ...existing imports...
import csv
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

# ...existing constants...
DEFAULT_OUTPUT_SUBDIR = "project_future_scraper"
DEFAULT_OUTPUT_FILENAME = "new_binance_perpetual_futures.csv"
DEFAULT_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"


class BinancePerpetualFuturesDiscovery:
    def __init__(
        self,
        start_date: str,                 # neu: Fenster-Start YYYY-MM-DD
        end_date: str,                   # neu: Fenster-Ende YYYY-MM-DD
        only_usdt: bool = True,
        output_subdir: str = DEFAULT_OUTPUT_SUBDIR,
        output_filename: str = DEFAULT_OUTPUT_FILENAME,
        exchange_info_url: str = DEFAULT_EXCHANGE_INFO_URL,
    ):
        self.start_dt = self._parse_date(start_date)
        self.end_dt = self._parse_date(end_date)
        if self.end_dt < self.start_dt:
            raise ValueError("end_date < start_date")
        self.only_usdt = only_usdt
        self.output_subdir = output_subdir
        self.output_filename = output_filename
        self.exchange_info_url = exchange_info_url

    @staticmethod
    def _parse_date(s: str):
        return datetime.strptime(s, "%Y-%m-%d").date()

    def _fetch_exchange_info(self) -> Dict:
        resp = requests.get(self.exchange_info_url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def discover(self) -> List[Dict[str, str]]:
        data = self._fetch_exchange_info()
        new_futures: List[Dict[str, str]] = []
        for symbol_info in data.get("symbols", []):
            if symbol_info.get("contractType") != "PERPETUAL":
                continue
            onboard_ms = symbol_info.get("onboardDate")
            if onboard_ms is None:
                continue
            listing_dt = datetime.fromtimestamp(onboard_ms / 1000, tz=timezone.utc)
            listing_day = listing_dt.date()
            if self.start_dt <= listing_day <= self.end_dt:
                sym = symbol_info["symbol"]
                if self.only_usdt and not sym.endswith("USDT"):
                    continue
                new_futures.append({
                    "symbol": sym,
                    "onboardDate": listing_dt.strftime("%Y-%m-%d %H:%M:%S"),
                })
        print("[INFO] Letzte 10 (gefiltert im Fenster):")
        for fut in new_futures[-10:]:
            print(fut)
        return new_futures

    def save(self, rows: List[Dict[str, str]], data_root: Path) -> Path:
        target_dir = data_root / self.output_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / self.output_filename
        with open(target_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "onboardDate"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"[INFO] {len(rows)} Einträge gespeichert: {target_path}")
        return target_path

    def run(self) -> List[Dict[str, str]]:
        rows = self.discover()
        data_root = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
        self.save(rows, data_root)
        return rows


if __name__ == "__main__":
    print("[START] Discovery Fenster")
    # Beispiel: letztes Quartal
    discovery = BinancePerpetualFuturesDiscovery(
        start_date="2025-01-01",
        end_date="2025-01-10",
        only_usdt=True,
    )
    try:
        discovery.run()
    except Exception as e:
        print(f"[ERROR] {e}")
    print("[END] Fertig.")
