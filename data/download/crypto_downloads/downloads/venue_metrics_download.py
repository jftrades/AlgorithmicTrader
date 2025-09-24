from pathlib import Path
from datetime import datetime, date
import shutil
import pandas as pd
import os  # NEU
from binance_historical_data import BinanceDataDumper
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_iso8601
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from data.download.crypto_downloads.custom_class.metrics_data import MetricsData


class VenueMetricsDownloader:
    def __init__(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        base_data_dir: str,
        save_as_csv: bool = True,
        save_in_catalog: bool = True,
        download_if_missing: bool = True,
        remove_processed: bool = True,  # NEU
        csv_output_subdir: str | None = None,  # NEU
    ):
        self.symbol = symbol              # z.B. SOLUSDT-PERP
        self.base_symbol = symbol.replace("-PERP", "")
        self.start_date_dt = self._to_date(start_date)
        self.end_date_dt = self._to_date(end_date)
        self.start_date = self.start_date_dt.isoformat()
        self.end_date = self.end_date_dt.isoformat()
        self.base_data_dir = Path(base_data_dir)
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.download_if_missing = download_if_missing
        self.remove_processed = remove_processed  # NEU
        self.csv_output_subdir = csv_output_subdir  # NEU

        # NEU: Cache Root
        self.cache_dir = self.base_data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # processed jetzt unter cache
        self.processed_dir = self.cache_dir / f"processed_metrics_data_{self.start_date}_to_{self.end_date}" / "csv"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.base_data_dir / "data_catalog_wrangled"

    @staticmethod
    def _to_date(d):
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").date()
        raise TypeError("start_date/end_date must be str YYYY-MM-DD or datetime.date")

    def _combined_metrics_path(self) -> Path:
        return self.processed_dir / f"{self.base_symbol}_METRICS_{self.start_date}_to_{self.end_date}.csv"

    def _download_raw_if_needed(self) -> Path:
        combined_path = self._combined_metrics_path()
        if combined_path.exists():
            return combined_path
        if not self.download_if_missing:
            raise FileNotFoundError(f"Metrics file not found and download disabled: {combined_path}")

        # temp Ordner unter cache
        temp_dir = self.cache_dir / "temp_metrics_downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)

        dumper = BinanceDataDumper(
            path_dir_where_to_dump=str(temp_dir),
            asset_class="um",
            data_type="metrics",
        )
        dumper.dump_data(
            tickers=[self.base_symbol],
            date_start=self.start_date_dt,
            date_end=self.end_date_dt,
            is_to_update_existing=False,
        )

        all_csvs = sorted(temp_dir.rglob("*.csv"))
        if not all_csvs:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError("No metrics CSVs downloaded.")

        with open(combined_path, "w", newline="") as outfile:
            header_written = False
            for p in all_csvs:
                df = pd.read_csv(p)
                if not header_written:
                    df.to_csv(outfile, index=False, header=True, lineterminator="\n")
                    header_written = True
                else:
                    df.to_csv(outfile, index=False, header=False, lineterminator="\n")

        shutil.rmtree(temp_dir, ignore_errors=True)
        return combined_path

    def _load_raw(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        required = {
            "create_time",
            "sum_open_interest",
            "sum_open_interest_value",
            "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio",
            "count_long_short_ratio",
            "sum_taker_long_short_vol_ratio",
        }
        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        return df

    def run(self):
        raw_file = self._download_raw_if_needed()
        df = self._load_raw(raw_file)

        instrument_id = InstrumentId(Symbol(self.symbol), Venue("BINANCE"))
        records = []
        csv_rows = []

        for _, row in df.iterrows():
            ts_event = dt_to_unix_nanos(pd.to_datetime(row["create_time"], utc=True))
            md = MetricsData(
                instrument_id=instrument_id,
                ts_event=ts_event,
                ts_init=ts_event,
                sum_open_interest=row["sum_open_interest"],
                sum_open_interest_value=row["sum_open_interest_value"],
                count_toptrader_long_short_ratio=row["count_toptrader_long_short_ratio"],
                sum_toptrader_long_short_ratio=row["sum_toptrader_long_short_ratio"],
                count_long_short_ratio=row["count_long_short_ratio"],
                sum_taker_long_short_vol_ratio=row["sum_taker_long_short_vol_ratio"],
            )
            records.append(md)
            if self.save_as_csv:
                csv_rows.append({
                    "timestamp_nano": ts_event,
                    "timestamp_iso": unix_nanos_to_iso8601(ts_event),
                    "symbol": self.symbol,
                    "sum_open_interest": row["sum_open_interest"],
                    "sum_open_interest_value": row["sum_open_interest_value"],
                    "count_toptrader_long_short_ratio": row["count_toptrader_long_short_ratio"],
                    "sum_toptrader_long_short_ratio": row["sum_toptrader_long_short_ratio"],
                    "count_long_short_ratio": row["count_long_short_ratio"],
                    "sum_taker_long_short_vol_ratio": row["sum_taker_long_short_vol_ratio"],
                })

        if self.save_in_catalog:
            self.catalog_path.mkdir(parents=True, exist_ok=True)
            catalog = ParquetDataCatalog(str(self.catalog_path))
            catalog.write_data(records)

        if self.save_as_csv:
            subdir = self.csv_output_subdir or os.getenv("CSV_OUTPUT_SUBDIR") or "csv_data"  # NEU
            out_dir = self.base_data_dir / subdir / self.symbol
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "METRICS.csv"
            pd.DataFrame(csv_rows).to_csv(out_path, index=False)

        result = {
            "raw_file": str(raw_file),
            "records": len(records),
            "catalog_written": self.save_in_catalog,
            "csv_written": self.save_as_csv,
        }

        # NEU: Cleanup processed directory
        if self.remove_processed:
            parent_dir = self.processed_dir.parent  # processed_metrics_data_x_to_y
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
    downloader = VenueMetricsDownloader(
        symbol="SOLUSDT-PERP",
        start_date="2025-01-01",
        end_date="2025-01-02",
        base_data_dir=str(base_dir),
        save_as_csv=True,
        save_in_catalog=True,
    )
    info = downloader.run()
    print(info)
