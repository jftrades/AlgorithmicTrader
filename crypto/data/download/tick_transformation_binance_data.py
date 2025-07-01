from pathlib import Path
import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import (
    TradeTick, InstrumentId, Symbol, Venue, Price, Quantity, AggressorSide
)
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import TradeTickDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# === Konfiguration ===
CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data_2024-01-01_to_2024-02-01" / "csv" / "BTCUSDT_TICKS_2024-01-01_to_2024-02-01.csv"
CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"
PRICE_PRECISION = 1
SIZE_PRECISION = 3
CHUNK_SIZE = 1_000_000  # 1 Million Ticks pro Chunk (MEMORY SAFE!)

print("🚀 Starte CHUNKED Tick Transformation (MEMORY-SAFE)...")
print(f"📥 CSV: {CSV_PATH.name}")
print(f"⚙️  Chunk-Größe: {CHUNK_SIZE:,} Ticks")

# === CHUNKED Processing Function (MEMORY OPTIMIZED) ===
def process_tick_data_in_chunks():
    """Verarbeite große CSV-Datei in Memory-sicheren Chunks UND speichere direkt im Catalog"""
    chunk_count = 0
    total_ticks = 0
    
    # Catalog einmal erstellen
    catalog = ParquetDataCatalog(str(CATALOG_ROOT_PATH))
    
    # Wrangler einmal erstellen
    wrangler = TradeTickDataWranglerV2(
        instrument_id="BTCUSDT-PERP.BINANCE",
        price_precision=PRICE_PRECISION,
        size_precision=SIZE_PRECISION
    )
    
    print(f"📊 Lade CSV in {CHUNK_SIZE:,} Zeilen Chunks...")
    
    # CSV in Chunks einlesen (MEMORY SAFE!)
    for chunk_df in pd.read_csv(CSV_PATH, chunksize=CHUNK_SIZE):
        chunk_count += 1
        print(f"\n🔄 Chunk {chunk_count}: {len(chunk_df):,} Zeilen")
        
        # Daten vorbereiten
        chunk_df["timestamp"] = pd.to_datetime(chunk_df["timestamp"], unit="ms")
        chunk_df[["price", "quantity"]] = chunk_df[["price", "quantity"]].apply(pd.to_numeric, errors='coerce')
        
        # Filtern
        initial_len = len(chunk_df)
        chunk_df.dropna(inplace=True)
        chunk_df = chunk_df[chunk_df["quantity"] > 0]
        chunk_df = chunk_df[chunk_df["price"] > 0]
        print(f"🔍 Gefiltert: {initial_len - len(chunk_df)} ungültige, {len(chunk_df):,} verbleiben")
        
        if len(chunk_df) == 0:
            continue
            
        # Aggressor Side Mapping
        chunk_df['aggressor_side'] = chunk_df['side'].map({
            'BUY': AggressorSide.BUYER,
            'SELL': AggressorSide.SELLER
        })
        
        # DataFrame für Wrangler vorbereiten
        wrangler_df = chunk_df.rename(columns={
            'timestamp': 'ts_event',
            'trade_id': 'trade_id',
            'price': 'price',
            'quantity': 'size',
            'aggressor_side': 'aggressor_side'
        }).copy()
        
        # Timestamps in Nanosekunden
        wrangler_df['ts_event'] = pd.to_datetime(wrangler_df['ts_event']).astype(int)
        
        print(f"⚙️  Wrangling Chunk {chunk_count}...")
        
        # Stdout unterdrücken für Wrangling (SILENT!)
        import sys
        import os
        original_stdout = sys.stdout
        sys.stdout = open('nul' if os.name == 'nt' else '/dev/null', 'w')
        
        try:
            chunk_ticks = wrangler.from_pandas(wrangler_df)
        finally:
            sys.stdout.close()
            sys.stdout = original_stdout
            
        print(f"✅ Chunk {chunk_count}: {len(chunk_ticks):,} TradeTicks erstellt")
        
        # SOFORT im Catalog speichern (CHUNK by CHUNK!)
        print(f"💾 Speichere Chunk {chunk_count} direkt in Catalog...")
        
        # Stdout für Catalog-Schreibvorgang unterdrücken
        original_stdout = sys.stdout
        sys.stdout = open('nul' if os.name == 'nt' else '/dev/null', 'w')
        
        try:
            catalog.write_data(chunk_ticks)
        finally:
            sys.stdout.close()
            sys.stdout = original_stdout
            
        total_ticks += len(chunk_ticks)
        print(f"📈 Gesamt gespeichert: {total_ticks:,} TradeTicks")
        
        # Memory cleanup nach jedem Chunk (KRITISCH!)
        import gc
        del chunk_df, wrangler_df, chunk_ticks
        gc.collect()
    
    return total_ticks

# === CHUNKED Processing UND Speichern starten ===
total_ticks = process_tick_data_in_chunks()
print(f"\n✅ {total_ticks:,} TradeTicks CHUNK-weise verarbeitet und gespeichert!")

# === FINALE CATALOG INFO ===
print("\n� Finale Catalog-Informationen...")

# Stdout für finale Info-Abfragen unterdrücken
import sys
import os
original_stdout = sys.stdout
original_stderr = sys.stderr

null_device = 'nul' if os.name == 'nt' else '/dev/null'
sys.stdout = open(null_device, 'w')
sys.stderr = open(null_device, 'w')

try:
    catalog = ParquetDataCatalog(str(CATALOG_ROOT_PATH))
    instruments = catalog.instruments()
    tick_data = catalog.trade_ticks()
finally:
    sys.stdout.close()
    sys.stderr.close()
    sys.stdout = original_stdout
    sys.stderr = original_stderr

print(f"📊 Catalog Inhalt: {len(instruments)} Instrumente, {len(tick_data)} Tick-Dateien")
print(f"💾 Catalog Pfad: {CATALOG_ROOT_PATH}")
print("🎯 CHUNK-BY-CHUNK Transformation ERFOLGREICH abgeschlossen!")
