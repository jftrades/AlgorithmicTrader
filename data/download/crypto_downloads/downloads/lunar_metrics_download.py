import os
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timezone
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_iso8601
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from data.download.crypto_downloads.custom_class.lunar_data import LunarData
import shutil  # NEU


class LunarMetricsDownloader:
    BASE_URL = "https://lunarcrush.com/api4/public/coins"

    def __init__(
        self,
        symbol: str,                  # Basis (z.B. SOL, BTC)
        start_date: str,
        end_date: str,
        base_data_dir: str,
        instrument_id_str: Optional[str] = None,  # z.B. SOLUSDT-PERP
        bucket: str = "hour",
        save_as_csv: bool = True,
        save_in_catalog: bool = True,
        download_if_missing: bool = True,
        remove_processed: bool = True,  # NEU
    ):
        self.symbol = symbol.upper()
        self.start_dt = self._to_date(start_date)
        self.end_dt = self._to_date(end_date)
        self.start_str = self.start_dt.isoformat()
        self.end_str = self.end_dt.isoformat()
        self.base_dir = Path(base_data_dir)
        # NEU: Cache Root
        self.cache_dir = self.base_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # temp & processed unter cache
        self.temp_dir = self.cache_dir / "temp_lunarcrush_downloads"
        self.processed_dir = self.cache_dir / f"processed_lunarcrush_{self.start_str}_to_{self.end_str}" / "csv"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.base_dir / "data_catalog_wrangled"
        self.bucket = bucket
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.download_if_missing = download_if_missing
        self.remove_processed = remove_processed  # NEU

        # Instrument-ID (Default: <BASE>USDT-PERP)
        self.instrument_id_str = instrument_id_str or f"{self.symbol}USDT-PERP"

        # Auth
        load_dotenv() 
        self.api_key = os.getenv("LUNARCRUSH_API_KEY")
        if not self.api_key:
            raise ValueError("Missing LUNARCRUSH_API_KEY in environment (.env)")

    @staticmethod
    def _to_date(d):
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").date()
        raise TypeError("Date must be YYYY-MM-DD or datetime.date")

    def _combined_path(self) -> Path:
        return self.processed_dir / f"{self.symbol}_LUNARCRUSH_{self.start_str}_to_{self.end_str}.csv"

    def _download_raw_if_needed(self) -> Path:
        target = self._combined_path()
        if target.exists():
            return target
        if not self.download_if_missing:
            raise FileNotFoundError(f"File missing and download disabled: {target}")

        self.temp_dir.mkdir(parents=True, exist_ok=True)

        start_ts = int(datetime.combine(self.start_dt, datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(self.end_dt, datetime.max.time()).timestamp())

        url = f"{self.BASE_URL}/{self.symbol}/time-series/v2"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"bucket": self.bucket, "start": start_ts, "end": end_ts}

        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"LunarCrush API error {resp.status_code}: {resp.text}")

        payload = resp.json()
        rows: List[Dict[str, Any]] = []

        required_fields = [
            "time", "contributors_active", "contributors_created", "interactions",
            "posts_active", "posts_created", "sentiment", "spam", "alt_rank",
            "circulating_supply", "close", "galaxy_score", "high", "low",
            "market_cap", "market_dominance", "open", "social_dominance", "volume_24h",
        ]

        def _fallback(v):
            return 0 if (v is None or v == "") else v

        for p in payload.get("data", []):
            record = {
                "timestamp": _fallback(p.get("time")),
                "datetime": datetime.fromtimestamp(_fallback(p.get("time")), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "contributors_active": _fallback(p.get("contributors_active")),
                "contributors_created": _fallback(p.get("contributors_created")),
                "interactions": _fallback(p.get("interactions")),
                "posts_active": _fallback(p.get("posts_active")),
                "posts_created": _fallback(p.get("posts_created")),
                "sentiment": _fallback(p.get("sentiment")),
                "spam": _fallback(p.get("spam")),
                "alt_rank": _fallback(p.get("alt_rank")),
                "circulating_supply": _fallback(p.get("circulating_supply")),
                "close": _fallback(p.get("close")),
                "galaxy_score": _fallback(p.get("galaxy_score")),
                "high": _fallback(p.get("high")),
                "low": _fallback(p.get("low")),
                "market_cap": _fallback(p.get("market_cap")),
                "market_dominance": _fallback(p.get("market_dominance")),
                "open": _fallback(p.get("open")),
                "social_dominance": _fallback(p.get("social_dominance")),
                "volume_24h": _fallback(p.get("volume_24h")),
            }
            for k in required_fields:
                if k not in record:
                    record[k] = 0
            rows.append(record)

        if not rows:
            raise ValueError("No LunarCrush data returned.")

        df = pd.DataFrame(rows)
        df.to_csv(target, index=False)

        # Cleanup
        if self.temp_dir.exists():
            try:
                for f in self.temp_dir.iterdir():
                    f.unlink(missing_ok=True)
                self.temp_dir.rmdir()
            except Exception:
                pass

        return target

    def _load_raw(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        expected = [
            "datetime","contributors_active","contributors_created","interactions",
            "posts_active","posts_created","sentiment","spam","alt_rank",
            "circulating_supply","close","galaxy_score","high","low",
            "market_cap","market_dominance","open","social_dominance","volume_24h",
        ]
        for col in expected:
            if col not in df.columns:
                df[col] = 0
        return df

    def run(self):
        csv_raw = self._download_raw_if_needed()
        df = self._load_raw(csv_raw)

        instrument_id = InstrumentId(Symbol(self.instrument_id_str), Venue("BINANCE"))
        catalog_records = []
        csv_rows = []

        for _, row in df.iterrows():
            ts_event = dt_to_unix_nanos(pd.to_datetime(row["datetime"], utc=True))
            ld = LunarData(
                instrument_id=instrument_id,
                ts_event=ts_event,
                ts_init=ts_event,
                contributors_active=row["contributors_active"],
                contributors_created=row["contributors_created"],
                interactions=row["interactions"],
                posts_active=row["posts_active"],
                posts_created=row["posts_created"],
                sentiment=row["sentiment"],
                spam=row["spam"],
                alt_rank=row["alt_rank"],
                circulating_supply=row["circulating_supply"],
                close=row["close"],
                galaxy_score=row["galaxy_score"],
                high=row["high"],
                low=row["low"],
                market_cap=row["market_cap"],
                market_dominance=row["market_dominance"],
                open=row["open"],
                social_dominance=row["social_dominance"],
                volume_24h=row["volume_24h"],
            )
            catalog_records.append(ld)
            if self.save_as_csv:
                csv_rows.append({
                    "timestamp_nano": ts_event,
                    "timestamp_iso": unix_nanos_to_iso8601(ts_event),
                    "symbol": self.instrument_id_str,
                    "contributors_active": row["contributors_active"],
                    "contributors_created": row["contributors_created"],
                    "interactions": row["interactions"],
                    "posts_active": row["posts_active"],
                    "posts_created": row["posts_created"],
                    "sentiment": row["sentiment"],
                    "spam": row["spam"],
                    "alt_rank": row["alt_rank"],
                    "circulating_supply": row["circulating_supply"],
                    "close": row["close"],
                    "galaxy_score": row["galaxy_score"],
                    "high": row["high"],
                    "low": row["low"],
                    "market_cap": row["market_cap"],
                    "market_dominance": row["market_dominance"],
                    "open": row["open"],
                    "social_dominance": row["social_dominance"],
                    "volume_24h": row["volume_24h"],
                })

        if self.save_in_catalog:
            self.catalog_path.mkdir(parents=True, exist_ok=True)
            catalog = ParquetDataCatalog(str(self.catalog_path))
            catalog.write_data(catalog_records)

        if self.save_as_csv:
            out_dir = self.base_dir / "csv_data" / self.instrument_id_str
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "LUNAR.csv"
            try:
                if out_path.exists():
                    out_path.unlink()  # NEU: Entfernen falls gelockt/veraltet
                pd.DataFrame(csv_rows).to_csv(out_path, index=False)
            except PermissionError as e:
                print(f"[WARN] Could not write LUNAR.csv (permission): {e}")

        result = {
            "raw_file": str(csv_raw),
            "records": len(catalog_records),
            "catalog_written": self.save_in_catalog,
            "csv_written": self.save_as_csv,
        }

        # NEU: Cleanup processed directory
        if self.remove_processed:
            parent_dir = self.processed_dir.parent  # processed_lunarcrush_x_to_y
            try:
                if parent_dir.exists():
                    shutil.rmtree(parent_dir)
                    result["processed_dir_removed"] = True
                else:
                    result["processed_dir_removed"] = False
            except Exception as e:
                result["processed_dir_removed"] = f"error: {e}"

        return result


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
    dl = LunarMetricsDownloader(
        symbol="SOL",
        start_date="2024-09-20",
        end_date="2024-09-30",
        base_data_dir=str(base_dir),
        instrument_id_str="SOLUSDT-PERP",
        save_as_csv=True,
        save_in_catalog=True,
    )
    info = dl.run()
    print(info)
