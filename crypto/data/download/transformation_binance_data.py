from pathlib import Path
import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import (
    Bar, BarSpecification, BarType, BarAggregation, PriceType,
    AggregationSource, InstrumentId, Symbol, Venue, Price, Quantity,
)
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.core.datetime import unix_nanos_to_dt

# === Konfiguration ===
CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_data_2024-02-01_to_2025-04-15" / "csv" / "BTCUSDT_15MINUTE_2024-02-01_to_2025-04-15.csv"
CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"
PRICE_PRECISION = 2
SIZE_PRECISION = 6
WRANGLER_INIT_BAR_TYPE_STRING = "BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL"
FINAL_TARGET_AGGREGATION_SOURCE = AggregationSource.EXTERNAL

TARGET_INSTRUMENT_ID = InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE"))
TARGET_BAR_SPEC = BarSpecification(step=15, aggregation=BarAggregation.MINUTE, price_type=PriceType.LAST)
TARGET_BAR_TYPE_OBJ = BarType(
    instrument_id=TARGET_INSTRUMENT_ID,
    spec=TARGET_BAR_SPEC,
    aggregation_source=FINAL_TARGET_AGGREGATION_SOURCE
)
FINAL_BAR_TYPE_STR_FOR_CATALOG = str(TARGET_BAR_TYPE_OBJ)
print(f"INFO: Daten werden für BarType '{FINAL_BAR_TYPE_STR_FOR_CATALOG}' vorbereitet.")

# === Daten einlesen ===
df = pd.read_csv(CSV_PATH, header=None, names=[
    "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
])
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns")
df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors='coerce')

# === Ungültige Bars filtern ===
initial_len = len(df)
df.dropna(inplace=True)
df = df[df["volume"] > 0]
df = df[df["high"] != df["low"]]
print(f"INFO: Gefiltert: {initial_len - len(df)} ungültige Zeilen entfernt, {len(df)} verbleiben.")

# === Wrangling
wrangler = BarDataWranglerV2(
    bar_type=WRANGLER_INIT_BAR_TYPE_STRING,
    price_precision=PRICE_PRECISION,
    size_precision=SIZE_PRECISION
)
initial_bars_from_wrangler = wrangler.from_pandas(df)

final_bars = []
if initial_bars_from_wrangler and isinstance(initial_bars_from_wrangler[0], Bar):
    for b_in in initial_bars_from_wrangler:
        final_bars.append(Bar(
            bar_type=TARGET_BAR_TYPE_OBJ,
            open=b_in.open,
            high=b_in.high,
            low=b_in.low,
            close=b_in.close,
            volume=Quantity(b_in.volume.as_double(), SIZE_PRECISION),
            ts_event=b_in.ts_event,
            ts_init=b_in.ts_init,
        ))
    print(f"INFO: {len(final_bars)} Bar-Objekte vom Wrangler erzeugt.")
else:
    print("WARNUNG: Keine gültigen Bar-Objekte vom Wrangler erhalten. Beende.")
    exit()

# === In Parquet-Katalog speichern
CATALOG_ROOT_PATH.mkdir(parents=True, exist_ok=True)
catalog = ParquetDataCatalog(path=CATALOG_ROOT_PATH)

instrument_for_meta = TestInstrumentProvider.btcusdt_binance()
if instrument_for_meta.size_precision != SIZE_PRECISION:
    print(f"WARNUNG: size_precision des TestInstruments ({instrument_for_meta.size_precision}) != {SIZE_PRECISION}")

catalog.write_data([instrument_for_meta])
catalog.write_data(final_bars)

print(f"✅ {len(final_bars)} Bars in '{CATALOG_ROOT_PATH.resolve()}' gespeichert.")

# === Zeitbereich der gespeicherten Daten loggen
if final_bars:
    ts_min = unix_nanos_to_dt(min(bar.ts_event for bar in final_bars))
    ts_max = unix_nanos_to_dt(max(bar.ts_event for bar in final_bars))
    print(f"📈 Gespeicherter Zeitbereich: {ts_min} bis {ts_max}")
else:
    print("❌ Keine Bars vorhanden zum Prüfen des Zeitbereichs.")
