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

# Memory-Management Konfiguration
CHUNK_DAYS = 30  # Verarbeite 30 Tage auf einmal (Memory-schonend)
CHUNK_SIZE = 100000  # Ticks pro Chunk beim CSV-Schreiben

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

def write_chunk_to_csv(chunk_df: pd.DataFrame, output_file: Path, is_first_chunk: bool = False):
    """Schreibt einen Chunk direkt in die CSV (Memory-effizient)"""
    mode = 'w' if is_first_chunk else 'a'
    header = is_first_chunk
    
    try:
        chunk_df.to_csv(output_file, mode=mode, header=header, index=False)
        print(f"  📝 {len(chunk_df):,} Ticks geschrieben")
    except Exception as e:
        print(f"  ❌ CSV-Schreibfehler: {e}")

def process_date_range_chunk(start_date: dt.date, end_date: dt.date, output_file: Path, is_first_chunk: bool = False):
    """Verarbeitet einen Datumsbereich chunk-weise ohne alles im RAM zu sammeln"""
    chunk_ticks = []
    total_ticks = 0
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        df = download_tick_data_for_date(date_str)
        
        if not df.empty:
            df['date'] = date_str
            df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
            df = df.dropna(subset=['timestamp'])
            df = df[df['timestamp'] > 0]
            
            try:
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['side'] = df['is_buyer_maker'].map({True: 'SELL', False: 'BUY'})
                
                # Spalten für Nautilus vorbereiten
                columns_order = ['timestamp', 'trade_id', 'price', 'quantity', 'side', 'is_buyer_maker']
                processed_df = df[columns_order].copy()
                
                chunk_ticks.append(processed_df)
                total_ticks += len(processed_df)
                
                # Memory-Management: Schreibe Chunk wenn zu groß
                if total_ticks >= CHUNK_SIZE:
                    combined_chunk = pd.concat(chunk_ticks, ignore_index=True)
                    combined_chunk = combined_chunk.sort_values('timestamp').reset_index(drop=True)
                    write_chunk_to_csv(combined_chunk, output_file, is_first_chunk)
                    
                    # Memory cleanup
                    chunk_ticks.clear()
                    del combined_chunk
                    total_ticks = 0
                    is_first_chunk = False
                    
            except Exception as e:
                print(f"  ❌ Verarbeitungsfehler für {date_str}: {e}")
        
        current_date += dt.timedelta(days=1)
    
    # Restliche Ticks schreiben
    if chunk_ticks:
        combined_chunk = pd.concat(chunk_ticks, ignore_index=True)
        combined_chunk = combined_chunk.sort_values('timestamp').reset_index(drop=True)
        write_chunk_to_csv(combined_chunk, output_file, is_first_chunk)
        
        # Memory cleanup
        chunk_ticks.clear()
        del combined_chunk
    
    return total_ticks

def main():
    """Chunk-weise Download für sehr große Zeiträume (Memory-effizient)"""
    print(f"🚀 Starte CHUNK-WEISEN Tick-Download für {TICKER} ({MARKET_TYPE})")
    print(f"📅 Zeitraum: {START_DATE} bis {END_DATE}")
    print(f"⚙️  Chunk-Größe: {CHUNK_DAYS} Tage, {CHUNK_SIZE:,} Ticks pro Schreibvorgang")
    
    # Verzeichnisse erstellen
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Output-Datei definieren
    start_str = START_DATE.strftime("%Y-%m-%d")
    end_str = END_DATE.strftime("%Y-%m-%d")
    output_file = PROCESSED_DIR / f"{TICKER}_TICKS_{start_str}_to_{end_str}.csv"
    
    # Falls Datei existiert, lösche sie (fresh start)
    if output_file.exists():
        output_file.unlink()
        print(f"🗑️  Alte Datei gelöscht")
    
    total_days = (END_DATE - START_DATE).days + 1
    processed_days = 0
    total_ticks_written = 0
    is_first_chunk = True
    
    # Chunk-weise Verarbeitung
    current_start = START_DATE
    while current_start <= END_DATE:
        current_end = min(current_start + dt.timedelta(days=CHUNK_DAYS - 1), END_DATE)
        chunk_days = (current_end - current_start).days + 1
        
        print(f"\n📦 CHUNK {processed_days // CHUNK_DAYS + 1}: {current_start} bis {current_end} ({chunk_days} Tage)")
        
        try:
            chunk_ticks = process_date_range_chunk(current_start, current_end, output_file, is_first_chunk)
            total_ticks_written += chunk_ticks
            processed_days += chunk_days
            is_first_chunk = False
            
            # Fortschritt anzeigen
            progress = (processed_days / total_days) * 100
            print(f"  ✅ Chunk abgeschlossen: {chunk_ticks:,} Ticks")
            print(f"  📊 Fortschritt: {processed_days}/{total_days} Tage ({progress:.1f}%)")
            print(f"  🎯 Gesamt Ticks bisher: {total_ticks_written:,}")
            
            # Memory cleanup zwischen Chunks
            import gc
            gc.collect()
            
        except Exception as e:
            print(f"  ❌ Chunk-Fehler: {e}")
            import traceback
            traceback.print_exc()
        
        current_start = current_end + dt.timedelta(days=1)
    
    # Cleanup temp directory
    if TEMP_DIR.exists():
        import shutil
        shutil.rmtree(TEMP_DIR)
        print(f"🗑️  Temp-Verzeichnis bereinigt")
    
    print(f"\n🎯 DOWNLOAD ABGESCHLOSSEN!")
    print(f"📊 Gesamt: {total_ticks_written:,} Ticks in {processed_days} Tagen")
    print(f"💾 Datei: {output_file}")
    print(f"📏 Dateigröße: {output_file.stat().st_size / (1024**3):.2f} GB")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Hauptfehler: {e}")
        traceback.print_exc()
