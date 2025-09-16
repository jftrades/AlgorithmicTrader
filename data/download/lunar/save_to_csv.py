import requests
import pandas as pd
from datetime import datetime, date
from dotenv import load_dotenv
from pathlib import Path
import os
import shutil
import json


class LunarCrushDownloader:
    BASE_URL = "https://lunarcrush.com/api4/public/coins"

    def __init__(self, symbol, start_date, end_date, base_data_dir):
        load_dotenv()
        self.api_key = os.getenv("LUNARCRUSH_API_KEY")
        if not self.api_key:
            raise ValueError("❌ Kein LUNARCRUSH_API_KEY in .env gefunden")

        self.symbol = symbol.upper()  # z. B. "ALPACA"
        self.start_date_dt = self._to_date(start_date)
        self.end_date_dt = self._to_date(end_date)

        self.start_date_str = self.start_date_dt.isoformat()
        self.end_date_str = self.end_date_dt.isoformat()

        self.base_data_dir = Path(base_data_dir)
        self.temp_raw_download_dir = self.base_data_dir / "temp_lunarcrush_downloads"
        self.processed_dir = (
            self.base_data_dir
            / f"processed_lunarcrush_{self.start_date_str}_to_{self.end_date_str}"
            / "csv"
        )

        self.temp_raw_download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _to_date(self, d):
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").date()
        raise TypeError("start_date/end_date muss str 'YYYY-MM-DD' oder datetime.date sein")

    def run(self):
        start_timestamp = int(datetime.combine(self.start_date_dt, datetime.min.time()).timestamp())
        end_timestamp = int(datetime.combine(self.end_date_dt, datetime.max.time()).timestamp())

        url = f"{self.BASE_URL}/{self.symbol}/time-series/v2"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {
            "bucket": "hour",  # minutendaten nicht langfristig verfügbar
            "start": start_timestamp,
            "end": end_timestamp,
        }

        print(f"⬇️ Lade Daten für {self.symbol} von {self.start_date_str} bis {self.end_date_str}")
        response = requests.get(url, headers=headers, params=params)
        print("Status Code:", response.status_code)

        if response.status_code != 200:
            print(f"❌ Fehler beim Abruf: {response.text}")
            return

        data = response.json()

        # Debug: Ausgabe der ersten Keys
        print("Beispiel-Eintrag:")
        print(json.dumps(data.get("data", [{}])[0], indent=2))

        records = []
        for point in data.get("data", []):
            records.append({
                "timestamp": point.get("time"),
                "datetime": datetime.fromtimestamp(point.get("time", 0)).strftime('%Y-%m-%d %H:%M:%S'),
                "contributors_active": point.get("contributors_active"),
                "contributors_created": point.get("contributors_created"),
                "interactions": point.get("interactions"),
                "posts_active": point.get("posts_active"),
                "posts_created": point.get("posts_created"),
                "sentiment": point.get("sentiment"),
                "spam": point.get("spam"),
                "alt_rank": point.get("alt_rank"),
                "circulating_supply": point.get("circulating_supply"),
                "close": point.get("close"),
                "galaxy_score": point.get("galaxy_score"),
                "high": point.get("high"),
                "low": point.get("low"),
                "market_cap": point.get("market_cap"),
                "market_dominance": point.get("market_dominance"),
                "open": point.get("open"),
                "social_dominance": point.get("social_dominance"),
                "volume_24h": point.get("volume_24h"),
            })

        if not records:
            print("❌ Keine Daten zurückgegeben.")
            return

        df = pd.DataFrame(records)

        # Temporär speichern
        temp_path = (
            self.temp_raw_download_dir
            / f"{self.symbol}_lunarcrush_{self.start_date_str}_to_{self.end_date_str}.csv"
        )
        df.to_csv(temp_path, index=False)
        print(f"📂 Temporäre Datei gespeichert: {temp_path}")

        # Final speichern
        combined_path = (
            self.processed_dir
            / f"{self.symbol}_LUNARCRUSH_{self.start_date_str}_to_{self.end_date_str}.csv"
        )
        df.to_csv(combined_path, index=False)
        print(f"✅ Endgültige CSV gespeichert: {combined_path}")

        # Temp-Ordner aufräumen
        shutil.rmtree(self.temp_raw_download_dir, ignore_errors=True)
        print(f"🧹 Temporäre Downloads gelöscht: {self.temp_raw_download_dir}")


if __name__ == "__main__":
    symbol = "BTC"  # Beispiel
    start_date = "2025-08-18"
    end_date = "2025-08-30"

    base_data_dir = str(Path(__file__).resolve().parents[2] / "DATA_STORAGE")

    downloader = LunarCrushDownloader(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_data_dir=base_data_dir,
    )
    downloader.run()
