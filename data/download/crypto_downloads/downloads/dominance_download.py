import os
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv

from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_iso8601  # Konsistenz mit anderen CSVs

class LunarDominanceDownloader:
    BASE_URL = "https://lunarcrush.com/api4/public/coins"

    def __init__(
        self,
        start_date: str,
        end_date: str,
        base_data_dir: str,
        symbols: List[str] | None = None,
        bucket: str = "hour",
        save_as_csv: bool = True,
        csv_output_subdir: str | None = None,
        sleep_seconds: float = 0.3,
    ):
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        if self.end_date < self.start_date:
            raise ValueError("end_date < start_date")
        self.base_dir = Path(base_data_dir)
        self.symbols = [s.upper() for s in (symbols or ["BTC", "ETH", "SOL", "DOGE", "PEPE"])]
        self.bucket = bucket
        self.save_as_csv = save_as_csv
        self.csv_output_subdir = csv_output_subdir
        self.sleep_seconds = sleep_seconds

        load_dotenv()
        self.api_key = os.getenv("LUNARCRUSH_API_KEY")
        if not self.api_key:
            raise ValueError("Missing LUNARCRUSH_API_KEY in environment (.env)")

    @staticmethod
    def _parse_date(s: str):
        return datetime.strptime(s, "%Y-%m-%d").date()

    def _time_range_seconds(self):
        start_ts = int(datetime.combine(self.start_date, datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(self.end_date, datetime.max.time()).timestamp())
        return start_ts, end_ts

    def _fetch_symbol(self, symbol: str) -> pd.DataFrame:
        start_ts, end_ts = self._time_range_seconds()
        url = f"{self.BASE_URL}/{symbol}/time-series/v2"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"bucket": self.bucket, "start": start_ts, "end": end_ts}
        r = requests.get(url, headers=headers, params=params, timeout=40)
        if r.status_code != 200:
            raise RuntimeError(f"LunarCrush API {symbol} error {r.status_code}: {r.text[:200]}")
        data = r.json().get("data", [])
        if not data:
            return pd.DataFrame()
        rows = []
        for d in data:
            ts = d.get("time")
            if ts is None:
                continue
            rows.append({
                "time": int(ts),
                f"{symbol}_close": d.get("close", 0) or 0,
                f"{symbol}_market_dominance": d.get("market_dominance", 0) or 0,
                f"{symbol}_social_dominance": d.get("social_dominance", 0) or 0,
            })
        return pd.DataFrame(rows)

    def run(self) -> Dict[str, Any]:
        merged: pd.DataFrame | None = None
        for i, sym in enumerate(self.symbols, 1):
            try:
                df = self._fetch_symbol(sym)
            except Exception as e:
                print(f"[WARN] {sym} skipped: {e}")
                continue
            if df.empty:
                print(f"[WARN] {sym} returned no rows.")
                continue
            if merged is None:
                merged = df
            else:
                merged = merged.merge(df, on="time", how="inner")
            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)

        if merged is None or merged.empty:
            raise ValueError("No data collected for any symbol.")

        # Zeitfenster filtern (Sicherheit)
        start_ts, end_ts = self._time_range_seconds()
        merged = merged[(merged["time"] >= start_ts) & (merged["time"] <= end_ts)]
        if merged.empty:
            raise ValueError("Merged dataset empty after final time window filter.")

        # Zeitspalten erzeugen
        merged.sort_values("time", inplace=True)
        merged.reset_index(drop=True, inplace=True)
        merged["timestamp_iso"] = pd.to_datetime(merged["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
        merged["timestamp_nano"] = merged["timestamp_iso"].apply(lambda s: dt_to_unix_nanos(pd.to_datetime(s, utc=True)))

        # Instrument ID fest (analog FNG)
        merged.insert(2, "instrument_id", "DOMINANCE.BINANCE")

        # Spalten-Reihenfolge
        time_cols = ["timestamp_nano", "timestamp_iso", "instrument_id"]
        metric_cols = [c for c in merged.columns if c.endswith(("_close", "_market_dominance", "_social_dominance"))]
        final_df = merged[time_cols + metric_cols]

        out_path = None
        if self.save_as_csv:
            subdir = self.csv_output_subdir or os.getenv("CSV_OUTPUT_SUBDIR") or "csv_data"
            out_dir = self.base_dir / subdir / "DOMINANCE.BINANCE"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "DOMINANCE.csv"
            final_df.to_csv(out_path, index=False)
            print(f"[OK] Dominance CSV: {out_path}")

        return {
            "symbols": self.symbols,
            "rows": len(final_df),
            "csv_path": str(out_path) if out_path else None,
            "columns": final_df.columns.tolist(),
        }

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data_catalog"
    dl = LunarDominanceDownloader(
        start_date="2024-01-01",
        end_date="2025-09-24",
        base_data_dir=str(base_dir),
        symbols=["BTC", "ETH", "SOL", "DOGE", "PEPE"],
        bucket="hour",
        save_as_csv=True,
        csv_output_subdir=os.getenv("CSV_OUTPUT_SUBDIR"),
    )
    info = dl.run()
    print(info)
