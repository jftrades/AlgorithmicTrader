from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from pathlib import Path
from nautilus_trader.model.instruments.base import Instrument
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog
import pandas as pd
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.data import TradeTick  # Import ergänzen

CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"

print("Starte Katalog-Initialisierung und Instrument-Metadaten-Check.")
CATALOG_ROOT_PATH.mkdir(parents=True, exist_ok=True)
PRICE_PRECISION = 1
SIZE_PRECISION = 3
catalog = ParquetDataCatalog(path=CATALOG_ROOT_PATH)
instrument_for_meta = TestInstrumentProvider.btcusdt_perp_binance()
if instrument_for_meta.size_precision != SIZE_PRECISION:
    print(f"WARNUNG: size_precision des TestInstruments ({instrument_for_meta.size_precision}) != {SIZE_PRECISION}")
catalog.write_data([instrument_for_meta])
print("Instrument-Metadaten gespeichert.")

CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data_2024-01-01_to_2024-01-03" / "csv" / "BTCUSDT_TICKS_2024-01-01_to_2024-01-03.csv"
print(f"Lese CSV-Datei: {CSV_PATH}")
Instrument = TestInstrumentProvider.btcusdt_perp_binance()
wrangler = TradeTickDataWrangler(instrument=Instrument)

# Zielordner für Parquet-Dateien (jetzt pro InstrumentId und mit 'TradeTick' statt 'tick')
TICK_OUT_DIR = CATALOG_ROOT_PATH / "data" / "TradeTick" / instrument_for_meta.id.value
TICK_OUT_DIR.mkdir(parents=True, exist_ok=True)

chunk_size = 100_000_000
chunk_count = 0
for chunk in pd.read_csv(CSV_PATH, chunksize=chunk_size):
    print(f"Lese Chunk {chunk_count+1} ...")
    chunk['timestamp'] = pd.to_datetime(chunk['timestamp'], utc=True)
    chunk = chunk.set_index('timestamp')
    ticks = wrangler.process(chunk)
    print(f"  -> {len(ticks)} Ticks im Chunk")
    df_ticks = pd.DataFrame([TradeTick.to_dict(t) for t in ticks])
    chunk_count += 1
    out_path = TICK_OUT_DIR / f"ticks_chunk_{chunk_count}.parquet"
    df_ticks.to_parquet(out_path)
    print(f"Chunk {chunk_count} gespeichert: {out_path.resolve()}")

# Lösche temporären Download-Ordner, falls vorhanden
TEMP_DOWNLOADS = Path(__file__).resolve().parent / "downloads"
if TEMP_DOWNLOADS.exists() and TEMP_DOWNLOADS.is_dir():
    import shutil
    shutil.rmtree(TEMP_DOWNLOADS)
    print(f"Temp-Ordner gelöscht: {TEMP_DOWNLOADS}")

print("Alle Chunks wurden verarbeitet und in den Nautilus-Katalog geschrieben.")



