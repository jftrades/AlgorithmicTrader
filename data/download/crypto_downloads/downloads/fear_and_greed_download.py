import requests
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any
import os  # NEU

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_iso8601

from data.download.crypto_downloads.custom_class.fear_and_greed_data import FearAndGreedData

import json


class FearAndGreedDownloader:
    """
    Downloader für den Crypto Fear & Greed Index (alternative.me) mit
    CSV- und Parquet-Katalog-Ausgabe analog zu Lunar / Venue Metrics.
    """
    API_URL = "https://api.alternative.me/fng/"

    def __init__(
        self,
        start_date: str,
        end_date: str,
        base_data_dir: str,
        instrument_id_str: str = "FNG-INDEX.BINANCE",
        limit: int = 0,                 # 0 => alle
        save_as_csv: bool = True,
        save_in_catalog: bool = True,
        download_if_missing: bool = True,
        remove_processed: bool = True,
        csv_output_subdir: str | None = None,  # NEU
    ):
        self.start_dt = self._to_date(start_date)
        self.end_dt = self._to_date(end_date)
        if self.end_dt < self.start_dt:
            raise ValueError("end_date < start_date")
        self.base_dir = Path(base_data_dir)
        self.instrument_id_str = instrument_id_str
        self.limit = limit
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.download_if_missing = download_if_missing
        self.remove_processed = remove_processed
        self.csv_output_subdir = csv_output_subdir

        # Cache-Struktur wie andere Downloader
        self.cache_dir = self.base_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir = self.cache_dir / f"processed_fng_{self.start_dt}_to_{self.end_dt}" / "csv"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.catalog_path = self.base_dir / "data_catalog_wrangled"

    @staticmethod
    def _to_date(v):
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date()
        raise TypeError("Date must be str YYYY-MM-DD or datetime.date")

    def _combined_path(self) -> Path:
        return self.processed_dir / f"FNG_{self.start_dt}_to_{self.end_dt}.csv"

    def _download_raw_if_needed(self) -> Path:
        target = self._combined_path()
        if target.exists():
            return target
        if not self.download_if_missing:
            raise FileNotFoundError(f"Raw FNG file missing and download disabled: {target}")

        url = f"{self.API_URL}?limit={self.limit}&date_format=world"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Fear & Greed API error {resp.status_code}: {resp.text}")

        payload = resp.json()
        data = payload.get("data", [])
        if not data:
            raise ValueError("No FNG data returned from API.")

        df = pd.DataFrame(data)
        # API liefert "timestamp" als YYYY-MM-DD (oder älter evtl epoch?). Robust umwandeln:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        df = df.dropna(subset=["timestamp"])
        # Zu Tages-Start normalisieren
        df["timestamp"] = df["timestamp"].dt.normalize()

        # Filter auf Fenster
        df = df[(df["timestamp"].dt.date >= self.start_dt) & (df["timestamp"].dt.date <= self.end_dt)]
        if df.empty:
            raise ValueError("Filtered FNG dataset empty for given date window.")

        # fear_greed int und classification
        df["fear_greed"] = pd.to_numeric(df["value"], errors="coerce").fillna(0).astype(int)
        df["classification"] = df["value_classification"].fillna("UNKNOWN")

        out_df = df[["timestamp", "fear_greed", "classification"]].sort_values("timestamp")
        out_df.to_csv(target, index=False)
        return target

    def _load_raw(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        for col in ["timestamp", "fear_greed", "classification"]:
            if col not in df.columns:
                raise ValueError(f"Missing column '{col}' in FNG raw CSV.")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["fear_greed"] = pd.to_numeric(df["fear_greed"], errors="coerce").fillna(0).astype(int)
        df["classification"] = df["classification"].fillna("UNKNOWN")
        return df

    def run(self) -> Dict[str, Any]:
        raw_file = self._download_raw_if_needed()
        df = self._load_raw(raw_file)

        instrument_id = InstrumentId.from_str(self.instrument_id_str)
        records: List[FearAndGreedData] = []
        csv_rows: List[Dict[str, Any]] = []

        for _, row in df.iterrows():
            # Tageszeit: wir nehmen 00:00:00 UTC als Event
            ts_event = dt_to_unix_nanos(row["timestamp"])
            fad = FearAndGreedData(
                instrument_id=instrument_id,
                ts_event=ts_event,
                ts_init=ts_event,
                fear_greed=int(row["fear_greed"]),
                classification=str(row["classification"]),
            )
            records.append(fad)
            if self.save_as_csv:
                csv_rows.append({
                    "timestamp_nano": ts_event,
                    "timestamp_iso": unix_nanos_to_iso8601(ts_event),
                    "instrument_id": self.instrument_id_str,
                    "fear_greed": fad.fear_greed,
                    "classification": fad.classification,
                })

        if self.save_in_catalog:
            self.catalog_path.mkdir(parents=True, exist_ok=True)
            catalog = ParquetDataCatalog(str(self.catalog_path))
            catalog.write_data(records)

        if self.save_as_csv:
            subdir = self.csv_output_subdir or os.getenv("CSV_OUTPUT_SUBDIR") or "csv_data"  # NEU
            out_dir = self.base_dir / subdir / self.instrument_id_str
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "FNG.csv"
            pd.DataFrame(csv_rows).to_csv(out_path, index=False)

        result = {
            "raw_file": str(raw_file),
            "records": len(records),
            "catalog_written": self.save_in_catalog,
            "csv_written": self.save_as_csv,
        }

        if self.remove_processed:
            parent_dir = self.processed_dir.parent
            try:
                if parent_dir.exists():
                    # Entfernen nur wenn raw_file nicht mehr gebraucht wird
                    import shutil
                    shutil.rmtree(parent_dir)
                    result["processed_dir_removed"] = True
                else:
                    result["processed_dir_removed"] = False
            except Exception as e:
                result["processed_dir_removed"] = f"error: {e}"

        return result


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
    downloader = FearAndGreedDownloader(
        start_date="2023-12-01",
        end_date="2023-12-31",
        base_data_dir=str(base_dir),
        instrument_id_str="FNG-INDEX.BINANCE",
        limit=0,
        save_as_csv=True,
        save_in_catalog=True,
        download_if_missing=True,
        remove_processed=False,
    )
    info = downloader.run()
    print(json.dumps(info, indent=2))
