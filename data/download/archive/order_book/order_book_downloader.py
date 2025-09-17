import requests
import zipfile
import io
import pandas as pd
from datetime import datetime, timedelta, date
from pathlib import Path
import shutil


class BookDepthDownloader:
    BASE_URL = "https://data.binance.vision/data/futures/um/daily/bookDepth"

    def __init__(self, symbol, start_date, end_date, base_data_dir):
        self.symbol = symbol.upper()  # z. B. "ATOMUSDT"

        self.start_date_dt = self._to_date(start_date)
        self.end_date_dt = self._to_date(end_date)
        self.start_date_str = self.start_date_dt.isoformat()
        self.end_date_str = self.end_date_dt.isoformat()

        self.base_data_dir = Path(base_data_dir)
        self.temp_raw_download_dir = self.base_data_dir / "temp_bookdepth_downloads"
        self.processed_dir = (
            self.base_data_dir
            / f"processed_bookdepth_{self.start_date_str}_to_{self.end_date_str}"
            / "csv"
        )

        self.temp_raw_download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _to_date(self, d):
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").date()
        raise TypeError("start_date/end_date must be str 'YYYY-MM-DD' or datetime.date")

    def run(self):
        current = self.start_date_dt
        temp_csvs = []

        while current <= self.end_date_dt:
            date_str = current.strftime("%Y-%m-%d")
            url = f"{self.BASE_URL}/{self.symbol}/{self.symbol}-bookDepth-{date_str}.zip"
            print(f"⬇️ Lade {url} ...")

            r = requests.get(url)
            if r.status_code != 200:
                print(f"❌ Keine Datei für {date_str} (Status {r.status_code})")
                current += timedelta(days=1)
                continue

            try:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                for name in z.namelist():
                    with z.open(name) as csvfile:
                        df = pd.read_csv(csvfile)

                        # Temporäre Datei speichern
                        temp_path = (
                            self.temp_raw_download_dir
                            / f"{self.symbol}_bookDepth_{date_str}.csv"
                        )
                        df.to_csv(temp_path, index=False)
                        temp_csvs.append(temp_path)
                        print(f"📂 Gespeichert: {temp_path}")
            except Exception as e:
                print(f"⚠️ Fehler beim Entpacken {url}: {e}")

            current += timedelta(days=1)

        if not temp_csvs:
            print("❌ Keine Daten geladen.")
            return

        # Alles zusammenfassen
        dfs = [pd.read_csv(p) for p in temp_csvs]
        final_df = pd.concat(dfs, ignore_index=True)
        combined_path = (
            self.processed_dir
            / f"{self.symbol}_BOOKDEPTH_{self.start_date_str}_to_{self.end_date_str}.csv"
        )
        final_df.to_csv(combined_path, index=False)

        print(f"✅ BookDepth CSV gespeichert: {combined_path}")

        # Temp-Ordner aufräumen
        shutil.rmtree(self.temp_raw_download_dir, ignore_errors=True)
        print(f"🧹 Temporäre Downloads gelöscht: {self.temp_raw_download_dir}")


if __name__ == "__main__":
    symbol = "ATOMUSDT"  # Beispiel
    start_date = "2025-09-05"
    end_date = "2025-09-09"

    base_data_dir = str(Path(__file__).resolve().parents[2] / "DATA_STORAGE")

    downloader = BookDepthDownloader(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_data_dir=base_data_dir,
    )
    downloader.run()
