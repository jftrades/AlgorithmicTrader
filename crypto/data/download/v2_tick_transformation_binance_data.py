import pandas as pd
from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from pathlib import Path

CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"
CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data_2024-01-01_to_2024-01-03" / "csv" / "BTCUSDT_TICKS_2024-01-01_to_2024-01-03.csv"

# Clean start (optional)
CATALOG_ROOT_PATH.mkdir(parents=True, exist_ok=True)
catalog = ParquetDataCatalog(path=CATALOG_ROOT_PATH)

# Instrument schreiben
instrument = TestInstrumentProvider.btcusdt_perp_binance()
catalog.write_data([instrument])

# Chunk-basiert laden
CHUNK_SIZE = 10_000_000  # Zeilen pro Chunk – passe das ggf. an deinen RAM an
chunk_iter = pd.read_csv(CSV_PATH, chunksize=CHUNK_SIZE)

wrangler = TradeTickDataWrangler(instrument=instrument)

for i, chunk_df in enumerate(chunk_iter):
    print(f"Verarbeite Chunk {i+1}...")

    tmp_csv = CATALOG_ROOT_PATH / f"tmp_chunk_{i}.csv"
    chunk_df.to_csv(tmp_csv, index=False)

    data = CSVTickDataLoader.load(file_path=tmp_csv)
    ticks = wrangler.process(data)

    catalog.write_data(ticks, skip_disjoint_check=True)

    tmp_csv.unlink()  # temporäre Datei löschen

print("✅ Alle Chunks erfolgreich verarbeitet.")

