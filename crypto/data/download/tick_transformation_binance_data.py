from pathlib import Path
import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import (
    TradeTick, InstrumentId, Symbol, Venue, Price, Quantity, AggressorSide
)
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import TradeTickDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# === Konfiguration ===
CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data_2024-01-01_to_2024-01-03" / "csv" / "BTCUSDT_TICKS_2024-01-01_to_2024-01-03.csv"
CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"
PRICE_PRECISION = 1
SIZE_PRECISION = 3

TARGET_INSTRUMENT_ID = InstrumentId(Symbol("BTCUSDT-PERP"), Venue("BINANCE"))
print(f"INFO: Daten werden für Instrument '{TARGET_INSTRUMENT_ID}' vorbereitet.")

# === Daten einlesen ===
print(f"INFO: Lade CSV: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
df[["price", "quantity"]] = df[["price", "quantity"]].apply(pd.to_numeric, errors='coerce')

# === Ungültige Ticks filtern ===
initial_len = len(df)
df.dropna(inplace=True)
df = df[df["quantity"] > 0]
df = df[df["price"] > 0]
print(f"INFO: Gefiltert: {initial_len - len(df)} ungültige Zeilen entfernt, {len(df)} verbleiben.")

# === Aggressor Side Mapping (BUY/SELL zu AggressorSide) ===
df['aggressor_side'] = df['side'].map({
    'BUY': AggressorSide.BUYER,
    'SELL': AggressorSide.SELLER
})

# === Wrangling mit TradeTickDataWranglerV2 ===
wrangler = TradeTickDataWranglerV2(
    instrument_id="BTCUSDT-PERP.BINANCE",  # String statt InstrumentId-Objekt
    price_precision=PRICE_PRECISION,
    size_precision=SIZE_PRECISION
)

# DataFrame für Wrangler vorbereiten (benötigt spezifische Spalten)
wrangler_df = df.rename(columns={
    'timestamp': 'ts_event',
    'trade_id': 'trade_id',
    'price': 'price',
    'quantity': 'size',
    'aggressor_side': 'aggressor_side'
}).copy()

# Timestamps in Nanosekunden konvertieren
wrangler_df['ts_event'] = pd.to_datetime(wrangler_df['ts_event']).astype(int)

print(f"INFO: Starte Wrangling von {len(wrangler_df):,} Ticks...")

# Stdout unterdrücken während Wrangling (verhindert Tick-Spam)
import sys
import os
original_stdout = sys.stdout
sys.stdout = open(os.devnull, 'w')

try:
    # Ticks erstellen (SILENT!)
    ticks = wrangler.from_pandas(wrangler_df)
finally:
    # Stdout wiederherstellen
    sys.stdout.close()
    sys.stdout = original_stdout

print(f"✅ {len(ticks):,} TradeTicks erstellt.")

# === KOMPLETT SILENT AB HIER ===
print("💾 Speichere in Nautilus Catalog...")

# ALLE stdout-Ausgaben ab hier unterdrücken (NUCLEAR OPTION)
import sys
import os
original_stdout = sys.stdout
original_stderr = sys.stderr

# Umleitung auf null für Windows/Linux
null_device = 'nul' if os.name == 'nt' else '/dev/null'
sys.stdout = open(null_device, 'w')
sys.stderr = open(null_device, 'w')

try:
    # ALLES was folgt ist SILENT
    catalog = ParquetDataCatalog(str(CATALOG_ROOT_PATH))
    catalog.write_data(ticks)
    instruments = catalog.instruments()
    tick_data = catalog.trade_ticks()
    
finally:
    # Stdout und stderr wiederherstellen
    sys.stdout.close()
    sys.stderr.close()
    sys.stdout = original_stdout
    sys.stderr = original_stderr

print(f"✅ {len(ticks):,} TradeTicks in Catalog gespeichert!")
print(f"📊 Catalog Inhalt: {len(instruments)} Instrumente, {len(tick_data)} Tick-Dateien")
print(f"💾 Catalog Pfad: {CATALOG_ROOT_PATH}")
print("🎯 Tick Transformation abgeschlossen!")
