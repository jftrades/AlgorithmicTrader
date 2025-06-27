

import datetime as dt
from pathlib import Path
import pandas as pd
import shutil
import traceback

from binance_historical_data import BinanceDataDumper

# === 1. Konfiguration ===
TICKER = "BTCUSDT"
DATA_FREQUENCY_DOWNLOAD = "5m"
DATA_FREQUENCY_FILENAME = "5MINUTE"
START_DATE = dt.date(2020, 1, 1)
END_DATE = dt.date(2025, 6, 1)

BASE_DATA_DIR = Path(__file__).resolve().parent.parent / "DATA_STORAGE"
TEMP_RAW_DOWNLOAD_DIR = BASE_DATA_DIR / "temp_raw_downloads"

start_str = START_DATE.strftime("%Y-%m-%d")
end_str = END_DATE.strftime("%Y-%m-%d")
PROCESSED_DIR = BASE_DATA_DIR / f"processed_data_{start_str}_to_{end_str}" / "csv"
EXPECTED_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_volume", "ignore"
]
OUTPUT_COLUMNS = ["timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"]

def normalize_timestamp_units(df):
    max_raw = df["open_time"].max()
    ts_2200 = int(pd.Timestamp("2200-01-01").timestamp() * 1000)

    if max_raw > ts_2200:
        print(f"⚠️ Ungültige Timestamps erkannt (z.B. Jahr > 2200): {max_raw}")
        # Versuche plausible Korrektur durch Umrechnungsversuche
        for factor in [1000, 1000000]:
            scaled = df["open_time"] // factor
            if scaled.max() < ts_2200:
                print(f"✅ Skaliere open_time durch {factor} → plausible Zeitwerte")
                df["open_time"] = scaled
                return df

        print("❌ Kein gültiger Skalierungsfaktor gefunden. Breche ab.")
        raise ValueError("open_time enthält nicht korrigierbare Zeitstempel.")
    return df

def main():
    print(f"Starte Download & Verarbeitung für {TICKER} ({DATA_FREQUENCY_DOWNLOAD}) von {START_DATE} bis {END_DATE}")
    TEMP_RAW_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        dumper = BinanceDataDumper(
            path_dir_where_to_dump=str(TEMP_RAW_DOWNLOAD_DIR),
            asset_class="um",
            data_type="klines",
            data_frequency=DATA_FREQUENCY_DOWNLOAD,
        )

        dumper.dump_data(
            tickers=[TICKER],
            date_start=START_DATE,
            date_end=END_DATE,
            is_to_update_existing=False
        )

        search_root = TEMP_RAW_DOWNLOAD_DIR

        print("Inhalt von", search_root)
        for path in search_root.rglob("*"):
            print("  ", path)
        all_csvs = sorted(search_root.rglob("*.csv"))

        if not all_csvs:
            print("❌ Keine CSV-Dateien gefunden.")
            return

        print(f"📁 {len(all_csvs)} CSV-Dateien gefunden. Lade und verarbeite...")

        df_list = []
        for file in all_csvs:
            try:
                # Prüfe, ob die erste Zeile ein Header ist
                with open(file, "r") as f:
                    first_line = f.readline()
                skip = 1 if "open_time" in first_line else 0

                df = pd.read_csv(
                    file,
                    header=None,
                    names=EXPECTED_COLUMNS,
                    dtype={"open_time": "int64"},
                    skiprows=skip,
                )
                df = normalize_timestamp_units(df)
                df_list.append(df)
            except Exception as e:
                print(f"⚠️ Fehler beim Verarbeiten von {file.name}: {e}")

        if not df_list:
            print("❌ Keine gültigen Daten geladen.")
            return

        df = pd.concat(df_list, ignore_index=True)
        df.rename(columns={"open_time": "open_time_ms"}, inplace=True)

        df.drop_duplicates(subset=["open_time_ms"], inplace=True)
        df.sort_values(by="open_time_ms", inplace=True)

        df["timestamp"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True).astype("int64")

        for col in ["open", "high", "low", "close", "volume", "number_of_trades"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df_final = df[OUTPUT_COLUMNS].dropna()
        if df_final.empty:
            print("❌ Nach Filtern keine gültigen Zeilen übrig.")
            return

        start_dt = pd.to_datetime(df_final["open_time_ms"].min(), unit="ms")
        end_dt = pd.to_datetime(df_final["open_time_ms"].max(), unit="ms")
        filename = f"{TICKER}_{DATA_FREQUENCY_FILENAME}_{start_str}_to_{end_dt.strftime('%Y-%m-%d')}.csv"
        output_path = PROCESSED_DIR / filename

        df_final.to_csv(output_path, index=False, header=False)

        print(f"✅ CSV erfolgreich gespeichert: {output_path.resolve()}")
        print(f"📅 Zeitbereich: {start_dt} bis {end_dt}")

    except Exception as e:
        print("❌ Fehler im Hauptprozess:", e)
        traceback.print_exc()

    finally:
        if TEMP_RAW_DOWNLOAD_DIR.exists():
            shutil.rmtree(TEMP_RAW_DOWNLOAD_DIR)
            print(f"🧹 Temporäres Verzeichnis gelöscht: {TEMP_RAW_DOWNLOAD_DIR.resolve()}")

if __name__ == "__main__":
    main()
