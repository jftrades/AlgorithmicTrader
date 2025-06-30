import datetime as dt
from pathlib import Path
import pandas as pd
import requests
import zipfile
import traceback

# === 1. Konfiguration ===
TICKER = "BTCUSDT"
START_DATE = dt.date(2024, 1, 1)
END_DATE = dt.date(2024, 1, 3)  # Kleiner Zeitraum zum Testen
MARKET_TYPE = "futures"  # spot oder futures (geändert zu futures für BTCUSDT-PERP)

BASE_DATA_DIR = Path(__file__).resolve().parent.parent / "DATA_STORAGE"
TEMP_DIR = BASE_DATA_DIR / "temp_tick_downloads"
start_str = START_DATE.strftime("%Y-%m-%d")
end_str = END_DATE.strftime("%Y-%m-%d")
PROCESSED_DIR = BASE_DATA_DIR / f"processed_tick_data_{start_str}_to_{end_str}" / "csv"

# Binance URLs
SPOT_URL = "https://data.binance.vision/data/spot/daily/trades"
FUTURES_URL = "https://data.binance.vision/data/futures/um/daily/trades"

def download_tick_data_for_date(date_str: str) -> pd.DataFrame:
    """Download und verarbeite Tick-Daten für ein spezifisches Datum"""
    base_url = FUTURES_URL if MARKET_TYPE == "futures" else SPOT_URL
    filename = f"{TICKER}-trades-{date_str}.zip"
    url = f"{base_url}/{TICKER}/{filename}"
    
    zip_path = TEMP_DIR / filename
    csv_path = TEMP_DIR / f"{TICKER}-trades-{date_str}.csv"
    
    try:
        print(f"📥 Download: {date_str}")
        response = requests.get(url, timeout=60)
        if response.status_code != 200:
            print(f"❌ Error {response.status_code} for {date_str}")
            return pd.DataFrame()
        
        # ZIP speichern und extrahieren
        with open(zip_path, 'wb') as f:
            f.write(response.content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(TEMP_DIR)
        
        # Prüfe welche CSV-Datei erstellt wurde
        csv_files = list(TEMP_DIR.glob("*.csv"))
        if not csv_files:
            print(f"❌ Keine CSV-Datei gefunden für {date_str}")
            return pd.DataFrame()
        
        csv_path = csv_files[0]  # Nimm die erste CSV-Datei
        
        # CSV lesen (Binance Tick Format) - sehr robust
        df = pd.read_csv(
            csv_path,
            names=['trade_id', 'price', 'quantity', 'base_quantity', 'timestamp', 'is_buyer_maker'],
            low_memory=False  # Verhindert DtypeWarning
        )
        
        # Datentypen sicher konvertieren ohne Int64 (das macht Probleme)
        df['trade_id'] = pd.to_numeric(df['trade_id'], errors='coerce')
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
        df['base_quantity'] = pd.to_numeric(df['base_quantity'], errors='coerce')
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df['is_buyer_maker'] = df['is_buyer_maker'].astype(str).str.lower() == 'true'
        
        # Ungültige Zeilen entfernen
        df.dropna(subset=['price', 'quantity', 'timestamp'], inplace=True)
        
        # Nur sinnvolle Daten behalten
        df = df[df['price'] > 0]
        df = df[df['quantity'] > 0]
        df = df[df['timestamp'] > 0]
        
        # Cleanup temp files
        zip_path.unlink(missing_ok=True)
        for csv_file in TEMP_DIR.glob("*.csv"):
            csv_file.unlink(missing_ok=True)
        
        print(f"✅ {len(df):,} ticks für {date_str}")
        return df
        
    except Exception as e:
        print(f"❌ Fehler für {date_str}: {e}")
        return pd.DataFrame()

def main():
    print(f"Starte Tick-Download für {TICKER} ({MARKET_TYPE}) von {START_DATE} bis {END_DATE}")
    
    # Verzeichnisse erstellen
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Alle Daten sammeln
    all_dfs = []
    current_date = START_DATE
    
    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y-%m-%d")
        df = download_tick_data_for_date(date_str)
        
        if not df.empty:
            df['date'] = date_str
            # Doppelte Sicherstellung für timestamp - muss numerisch sein
            df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
            df = df.dropna(subset=['timestamp'])  # Entferne Zeilen mit ungültigen timestamps
            df = df[df['timestamp'] > 0]  # Nur positive timestamps
            
            # Jetzt datetime erstellen
            try:
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['side'] = df['is_buyer_maker'].map({True: 'SELL', False: 'BUY'})
                all_dfs.append(df)
                print(f"  ✅ {len(df):,} valide Ticks hinzugefügt")
            except Exception as e:
                print(f"  ❌ Datetime-Fehler: {e}")
                # Debug: Zeige ein paar timestamp-Werte
                print(f"  Debug - timestamp dtype: {df['timestamp'].dtype}")
                print(f"  Debug - erste 5 timestamps: {df['timestamp'].head().tolist()}")
                print(f"  Debug - timestamp min/max: {df['timestamp'].min()}/{df['timestamp'].max()}")
        
        current_date += dt.timedelta(days=1)
    
    if not all_dfs:
        print("❌ Keine Daten heruntergeladen")
        return
    
    # Kombinieren und speichern
    print("📦 Kombiniere alle Daten...")
    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
    
    # Spalten für Nautilus vorbereiten
    columns_order = ['timestamp', 'trade_id', 'price', 'quantity', 'side', 'is_buyer_maker']
    final_df = combined_df[columns_order]
    
    # CSV speichern (ähnlich wie bei Bars)
    output_file = PROCESSED_DIR / f"{TICKER}_TICKS_{start_str}_to_{end_str}.csv"
    final_df.to_csv(output_file, index=False)
    
    # Cleanup temp
    if TEMP_DIR.exists():
        import shutil
        shutil.rmtree(TEMP_DIR)
    
    print(f"\n✅ Fertig!")
    print(f"📊 {len(final_df):,} Ticks gespeichert")
    print(f"💾 Datei: {output_file}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Hauptfehler: {e}")
        traceback.print_exc()
