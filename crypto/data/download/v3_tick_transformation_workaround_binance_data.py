from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from pathlib import Path
from nautilus_trader.model.instruments.base import Instrument
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.data import TradeTick
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import re
import shutil

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"

print("Starte Katalog-Initialisierung und Instrument-Metadaten-Check.")
CATALOG_ROOT_PATH.mkdir(parents=True, exist_ok=True)
catalog = ParquetDataCatalog(path=CATALOG_ROOT_PATH)

instrument = TestInstrumentProvider.btcusdt_perp_binance()
catalog.write_data([instrument])
print("Instrument-Metadaten gespeichert.")

CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data_2024-01-01_to_2024-01-03" / "csv" / "BTCUSDT_TICKS_2024-01-01_to_2024-01-03.csv"
print(f"Lese CSV-Datei: {CSV_PATH}")
wrangler = TradeTickDataWrangler(instrument=instrument)

# Schritt 1: Chunks RAM-schonend als Parquet speichern
PARQUET_DIR = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "parquet_chunks"
PARQUET_DIR.mkdir(parents=True, exist_ok=True)

chunk_size = 100_000
for idx, df_chunk in enumerate(pd.read_csv(CSV_PATH, chunksize=chunk_size)):
    df_chunk.to_parquet(PARQUET_DIR / f"chunk_{idx}.parquet")
    print(f"Chunk {idx} als Parquet gespeichert.")

# Schritt 2: Alle Parquet-Chunks zusammenfügen und in TradeTick-Objekte umwandeln
all_ticks = []
overall_min = None
overall_max = None
for parquet_file in sorted(PARQUET_DIR.glob("chunk_*.parquet"), key=natural_sort_key):
    df = pd.read_parquet(parquet_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    if df['timestamp'].isnull().any():
        print(f"Warnung: Leere oder ungültige Timestamps in {parquet_file.name} ({df['timestamp'].isnull().sum()} Zeilen)")
    df = df.set_index('timestamp')
    ticks_chunk = wrangler.process(df)
    all_ticks.extend(ticks_chunk)
    if not df.empty:
        chunk_min = df.index.min()
        chunk_max = df.index.max()
        if overall_min is None or chunk_min < overall_min:
            overall_min = chunk_min
        if overall_max is None or chunk_max > overall_max:
            overall_max = chunk_max
    print(f"Chunk {parquet_file.name} geladen und in TradeTicks umgewandelt.")

# Schritt 2.5: Sortiere alle Ticks nach ts_init (Pflicht für Nautilus)
all_ticks.sort(key=lambda x: x.ts_init)

# Schritt 3: In Nautilus-Katalog schreiben, Dateiname enthält Zeitraum
start_date = overall_min.strftime('%Y-%m-%d') if overall_min is not None else 'unknown'
end_date = overall_max.strftime('%Y-%m-%d') if overall_max is not None else 'unknown'
output_name = f"trade_tick_{start_date}_to_{end_date}_all_{{i}}"
catalog.write_data(all_ticks, basename_template=output_name)
print(f"Alle Ticks wurden Nautilus-kompatibel als {output_name}.parquet in den Katalog geschrieben.")

shutil.rmtree(PARQUET_DIR)
print(f"Parquet-Chunks in {PARQUET_DIR} wurden gelöscht.")