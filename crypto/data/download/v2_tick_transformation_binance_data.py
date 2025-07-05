from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from pathlib import Path
from nautilus_trader.model.instruments.base import Instrument
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from nautilus_trader.test_kit.providers import TestInstrumentProvider
CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"


# === In Parquet-Katalog speichern
CATALOG_ROOT_PATH.mkdir(parents=True, exist_ok=True)
PRICE_PRECISION = 1
SIZE_PRECISION = 3
catalog = ParquetDataCatalog(path=CATALOG_ROOT_PATH)
instrument_for_meta = TestInstrumentProvider.btcusdt_perp_binance()
if instrument_for_meta.size_precision != SIZE_PRECISION:
    print(f"WARNUNG: size_precision des TestInstruments ({instrument_for_meta.size_precision}) != {SIZE_PRECISION}")

catalog.write_data([instrument_for_meta])


CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data_2024-01-01_to_2024-01-02" / "csv" / "BTCUSDT_TICKS_2024-01-01_to_2024-01-02.csv"
print("1")
Instrument = TestInstrumentProvider.btcusdt_perp_binance()
print("2")
wrangler = TradeTickDataWrangler(instrument=Instrument)
print("3")
data = CSVTickDataLoader.load(file_path=CSV_PATH)
ticks = wrangler.process(data)
print("4")
catalog.write_data(ticks)



