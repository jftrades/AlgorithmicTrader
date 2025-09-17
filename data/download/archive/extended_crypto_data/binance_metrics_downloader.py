from pathlib import Path
from binance_historical_data import BinanceDataDumper
import shutil
import pandas as pd
from datetime import datetime, date

class MetricsDownloader:
    def __init__(self, symbol, start_date, end_date, base_data_dir):
        self.symbol = symbol
        # Convert incoming dates to datetime.date and keep ISO strings for naming
        self.start_date_dt = self._to_date(start_date)
        self.end_date_dt = self._to_date(end_date)
        self.start_date_str = self.start_date_dt.isoformat()
        self.end_date_str = self.end_date_dt.isoformat()
        self.base_data_dir = base_data_dir
        self.temp_raw_download_dir = Path(base_data_dir) / "temp_metrics_downloads"
        self.processed_dir = Path(base_data_dir) / f"processed_metrics_data_{self.start_date_str}_to_{self.end_date_str}" / "csv"

    def _to_date(self, d):
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").date()
        raise TypeError("start_date/end_date must be str 'YYYY-MM-DD' or datetime.date")

    def run(self):
        self.temp_raw_download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        dumper = BinanceDataDumper(
            path_dir_where_to_dump=str(self.temp_raw_download_dir),
            asset_class="um",          # um = USDT-M Futures
            data_type="metrics",       # Metrics-Daten
        )

        dumper.dump_data(
            tickers=[self.symbol],
            date_start=self.start_date_dt,
            date_end=self.end_date_dt,
            is_to_update_existing=False,
        )

        # Alle CSVs zusammenfassen
        all_csvs = sorted(self.temp_raw_download_dir.rglob("*.csv"))
        if not all_csvs:
            print("❌ Keine Metrics-CSVs gefunden.")
            shutil.rmtree(self.temp_raw_download_dir, ignore_errors=True)
            print(f"🧹 Temporäre Downloads gelöscht: {self.temp_raw_download_dir}")
            return

        combined_path = self.processed_dir / f"{self.symbol}_METRICS_{self.start_date_str}_to_{self.end_date_str}.csv"
        # Open with newline='' to avoid extra blank lines on Windows
        with open(combined_path, "w", newline="") as outfile:
            header_written = False
            for file in all_csvs:
                df = pd.read_csv(file)
                if not header_written:
                    df.to_csv(outfile, index=False, header=True, lineterminator="\n")
                    header_written = True
                else:
                    df.to_csv(outfile, index=False, header=False, lineterminator="\n")
        print(f"✅ Metrics CSV gespeichert: {combined_path}")

        shutil.rmtree(self.temp_raw_download_dir, ignore_errors=True)
        print(f"🧹 Temporäre Downloads gelöscht: {self.temp_raw_download_dir}")

if __name__ == "__main__":

    symbol = "BTCUSDT"         # Futures Symbol
    start_date = "2024-01-01"
    end_date = "2025-01-01"
    base_data_dir = str(Path(__file__).resolve().parents[2] / "DATA_STORAGE")

    downloader = MetricsDownloader(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_data_dir=base_data_dir,
    )
    downloader.run()
