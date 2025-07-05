from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from pathlib import Path
from nautilus_trader.model.instruments.base import Instrument
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.data import TradeTick
import pandas as pd

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

chunk_size = 100_000
output_name = "trade_tick_all{i}"
first_chunk = True
for df_chunk in pd.read_csv(CSV_PATH, chunksize=chunk_size):
    df_chunk['timestamp'] = pd.to_datetime(df_chunk['timestamp'], utc=True)
    df_chunk = df_chunk.set_index('timestamp')
    ticks_chunk = wrangler.process(df_chunk)
    if first_chunk:
        catalog.write_data(ticks_chunk, basename_template=output_name)
        first_chunk = False
    else:
        catalog.append_data(ticks_chunk, basename_template=output_name)
    print(f"Chunk mit {len(ticks_chunk)} Ticks gespeichert/angehängt.")

print("Alle Chunks wurden Nautilus-kompatibel in den Katalog geschrieben.")

