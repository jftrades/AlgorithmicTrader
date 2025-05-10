import datetime as dt
from pathlib import Path
import pandas as pd
import shutil
import traceback

from binance_historical_data import BinanceDataDumper

# === 1. Konfiguration ===
TICKER = "BTCUSDT"
DATA_FREQUENCY_DOWNLOAD = "15m"
DATA_FREQUENCY_FILENAME = "15MINUTE"

START_DATE = dt.date(2022, 7, 1)
END_DATE = dt.date(2022, 8, 15)

BASE_DATA_DIR = Path("./DATA_STORAGE")
TEMP_RAW_DOWNLOAD_DIR = BASE_DATA_DIR / "temp_raw_downloads"

start_date_str_for_folder = START_DATE.strftime("%Y-%m-%d")
end_date_str_for_folder = END_DATE.strftime("%Y-%m-%d")
final_processed_data_main_folder_name = f"processed_data_{start_date_str_for_folder}_to_{end_date_str_for_folder}"
FINAL_PROCESSED_DATA_DIR = BASE_DATA_DIR / final_processed_data_main_folder_name
FINAL_PROCESSED_CSV_SUBDIR = FINAL_PROCESSED_DATA_DIR / "csv"

EXPECTED_CSV_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_volume", "ignore"
]
FINAL_CSV_COLUMNS = ["timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"]

# === Hauptfunktion ===
def main():
    print(f"Starte Prozess für {TICKER} ({DATA_FREQUENCY_DOWNLOAD}) von {START_DATE} bis {END_DATE}.")
    print(f"Daten werden in Unterordnern von '{BASE_DATA_DIR.resolve()}' verarbeitet.")
    print(f"Temporäre Rohdaten in: '{TEMP_RAW_DOWNLOAD_DIR.resolve()}'")
    print(f"Finale prozessierte CSVs in: '{FINAL_PROCESSED_CSV_SUBDIR.resolve()}'")

    BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_RAW_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_PROCESSED_CSV_SUBDIR.mkdir(parents=True, exist_ok=True)

    try:
        dumper = BinanceDataDumper(
            path_dir_where_to_dump=str(TEMP_RAW_DOWNLOAD_DIR), # Dumper legt 'spot' etc. HIERDRIN an
            asset_class="spot",
            data_type="klines",
            data_frequency=DATA_FREQUENCY_DOWNLOAD,
        )
        print(f"Lade Rohdaten nach '{TEMP_RAW_DOWNLOAD_DIR.resolve()}'...")
        # Die Ausgabe "Data will be saved here:" bezieht sich auf den asset_class Ordner
        # z.B. ...\temp_raw_downloads\spot
        dumper.dump_data(
            tickers=[TICKER],
            date_start=START_DATE,
            date_end=END_DATE,
            is_to_update_existing=False
        )
        print("Download der Rohdaten abgeschlossen.")

        # --- Schritt 2: Heruntergeladene CSV-Dateien finden (vereinfacht und robuster) ---
        # Der Dumper speichert die CSVs in einer Struktur unterhalb von:
        # TEMP_RAW_DOWNLOAD_DIR / <asset_class> / <data_type> / (<monthly_or_daily>) / <TICKER> / *.csv
        
        # Wir suchen ab dem <asset_class> Ordner ('spot') rekursiv.
        search_root = TEMP_RAW_DOWNLOAD_DIR / "spot" # Der Dumper erstellt 'spot'
        
        print(f"Suche rekursiv nach CSV-Dateien für {TICKER} unter: {search_root.resolve()}")

        if not search_root.exists() or not search_root.is_dir():
            print(f"FEHLER: Das erwartete Basis-Downloadverzeichnis '{search_root.resolve()}' (erstellt von BinanceDataDumper) existiert nicht oder ist kein Verzeichnis.")
            return

        # rglob durchsucht alle Unterverzeichnisse von 'search_root'
        all_csv_files = sorted(list(search_root.rglob(f"{TICKER}-{DATA_FREQUENCY_DOWNLOAD}-*.csv")))
        
        if not all_csv_files:
            print(f"FEHLER: Keine CSV-Rohdateien für {TICKER} mit dem Muster '{TICKER}-{DATA_FREQUENCY_DOWNLOAD}-*.csv' unter '{search_root.resolve()}' gefunden.")
            print("\n--- Inhalt des temporären Download-Verzeichnisses (rekursiv ab TEMP_RAW_DOWNLOAD_DIR) ---")
            for item in TEMP_RAW_DOWNLOAD_DIR.rglob('*'):
                print(item)
            print("-------------------------------------------------------------------------------------\n")
            return

        print(f"{len(all_csv_files)} CSV-Rohdateien insgesamt gefunden. Werden nun zusammengeführt und verarbeitet.")
        # for f in all_csv_files: print(f"  Gefunden: {f}") # Zum Debuggen

        df_list = []
        for csv_file in all_csv_files:
            try:
                df_temp = pd.read_csv(csv_file, header=None, names=EXPECTED_CSV_COLUMNS)
                df_list.append(df_temp)
            except Exception as e:
                print(f"Warnung: Fehler beim Lesen von {csv_file}: {e}. Datei wird übersprungen.")
                continue

        if not df_list:
            print("Keine Daten konnten aus den CSV-Rohdateien geladen werden.")
            return

        df_combined = pd.concat(df_list, ignore_index=True)
        df_combined.sort_values(by="open_time", inplace=True)
        df_combined.drop_duplicates(subset=['open_time'], keep='first', inplace=True)
        print(f"Kombinierter DataFrame mit {len(df_combined)} Zeilen erstellt.")

        df_combined.rename(columns={'open_time': 'open_time_ms'}, inplace=True)
        df_combined["timestamp"] = pd.to_datetime(df_combined["open_time_ms"], unit="ms", utc=True).astype('int64')
        numeric_cols_to_convert = ["open", "high", "low", "close", "volume", "number_of_trades"]
        for col in numeric_cols_to_convert:
            df_combined[col] = pd.to_numeric(df_combined[col], errors='coerce')
        df_final_csv = df_combined[FINAL_CSV_COLUMNS].copy()
        df_final_csv.dropna(inplace=True)

        if df_final_csv.empty:
            print("Nach der Transformation sind keine gültigen Daten mehr für die CSV-Ausgabe vorhanden.")
            return

        actual_end_date_data_str = pd.to_datetime(df_final_csv["open_time_ms"].max(), unit="ms").strftime("%Y-%m-%d")
        output_filename = f"{TICKER}_{DATA_FREQUENCY_FILENAME}_{start_date_str_for_folder}_to_{actual_end_date_data_str}.csv"
        output_filepath = FINAL_PROCESSED_CSV_SUBDIR / output_filename

        print(f"Speichere {len(df_final_csv)} Zeilen als CSV-Datei: {output_filepath.resolve()}")
        df_final_csv.to_csv(output_filepath, index=False)
        print(f"✅ CSV-Datei erfolgreich erstellt: {output_filepath.resolve()}")

    except Exception as e:
        print(f"Ein Fehler ist im Hauptprozess aufgetreten: {e}")
        traceback.print_exc()

    finally:
        if TEMP_RAW_DOWNLOAD_DIR.exists():
            try:
                shutil.rmtree(TEMP_RAW_DOWNLOAD_DIR)
                print(f"Temporäres Download-Verzeichnis '{TEMP_RAW_DOWNLOAD_DIR.resolve()}' erfolgreich gelöscht.")
            except Exception as e_rm:
                print(f"Fehler beim Löschen des temporären Verzeichnisses '{TEMP_RAW_DOWNLOAD_DIR.resolve()}': {e_rm}")
        else:
            print(f"Temporäres Download-Verzeichnis '{TEMP_RAW_DOWNLOAD_DIR.resolve()}' nicht gefunden oder bereits gelöscht.")

if __name__ == "__main__":
    main() 
    

