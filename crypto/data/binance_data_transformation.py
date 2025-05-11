from pathlib import Path
import pandas as pd
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.loaders import CSVBarDataLoader
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2

# === Konfiguration ===
CSV_PATH = Path("DATA_STORAGE/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2022-07.csv")
CATALOG_PATH = Path("DATA_STORAGE/data_catalog_wrangled/")
BAR_TYPE = "BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL"



PRICE_PRECISION = 2
SIZE_PRECISION = 4

# === Step 1: Binance CSV manuell einlesen und vorbereiten ===
df = pd.read_csv(CSV_PATH, header=None)
df.columns = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
]
df["timestamp"] = pd.to_datetime(df["open_time"], unit="us")  # oder "us", je nach Quelle
df = df[["timestamp", "open", "high", "low", "close", "volume"]]

# === Step 2: Wrangle zu Nautilus Bars ===
wrangler = BarDataWranglerV2(
    bar_type=BAR_TYPE,
    price_precision=PRICE_PRECISION,
    size_precision=SIZE_PRECISION,
)
bars = wrangler.from_pandas(df)

# === Step 3: Speichern im Catalog ===
catalog = ParquetDataCatalog(path=CATALOG_PATH)
catalog.write_data(bars)

print(f"✅ {len(bars)} Bars erfolgreich verarbeitet und gespeichert.")
