# In binance_data_transformation.py (Version 14 - Produktiv, stark gekürzt)

from pathlib import Path
import pandas as pd

from nautilus_trader.core.nautilus_pyo3 import (
    Bar, BarSpecification, BarType, BarAggregation, PriceType,
    AggregationSource, InstrumentId, Symbol, Venue, Price, Quantity,
)
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# === Konfiguration ===
CSV_PATH = Path("DATA_STORAGE/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2022-07.csv")
CATALOG_ROOT_PATH = Path("DATA_STORAGE/data_catalog_wrangled/")
PRICE_PRECISION = 2
SIZE_PRECISION = 6 # Basierend auf Instrument-Anforderung
# Dieser String muss dem entsprechen, was die Strategie/Engine für `aggregation_source` als Wert '1' (oft EXTERNAL) erwartet.
# Wenn die Strategie/Engine INTERNAL (Wert '2') verarbeiten kann, kann dies auf INTERNAL geändert werden.
WRANGLER_INIT_BAR_TYPE_STRING = "BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL"
FINAL_TARGET_AGGREGATION_SOURCE = AggregationSource.EXTERNAL # Oder .INTERNAL, je nachdem was der Backtest verarbeiten kann

# Ziel-BarType für die zu schreibenden Bars
TARGET_INSTRUMENT_ID = InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE"))
TARGET_BAR_SPEC = BarSpecification(step=15, aggregation=BarAggregation.MINUTE, price_type=PriceType.LAST)
TARGET_BAR_TYPE_OBJ = BarType(
    instrument_id=TARGET_INSTRUMENT_ID,
    spec=TARGET_BAR_SPEC,
    aggregation_source=FINAL_TARGET_AGGREGATION_SOURCE
)
FINAL_BAR_TYPE_STR_FOR_CATALOG = str(TARGET_BAR_TYPE_OBJ)
print(f"INFO: Transformer: Daten werden für BarType '{FINAL_BAR_TYPE_STR_FOR_CATALOG}' vorbereitet und gespeichert.")

# === Datenaufbereitung und Transformation ===
CATALOG_ROOT_PATH.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(CSV_PATH, header=None,
                 names=["open_time", "open", "high", "low", "close", "volume",
                        "close_time", "quote_asset_volume", "number_of_trades",
                        "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"])
df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric)
df = df[["timestamp", "open", "high", "low", "close", "volume"]]
print(f"INFO: Transformer: CSV '{CSV_PATH.name}' mit {len(df)} Zeilen geladen.")

wrangler = BarDataWranglerV2(
    bar_type=WRANGLER_INIT_BAR_TYPE_STRING, # Nur zur Initialisierung des Wranglers
    price_precision=PRICE_PRECISION,
    size_precision=SIZE_PRECISION
)
initial_bars_from_wrangler = wrangler.from_pandas(df)

final_bars = []
if initial_bars_from_wrangler and isinstance(initial_bars_from_wrangler[0], Bar):
    for b_in in initial_bars_from_wrangler:
        final_bars.append(Bar(
            bar_type=TARGET_BAR_TYPE_OBJ, # Der gewünschte, finale BarType
            open=b_in.open, high=b_in.high, low=b_in.low, close=b_in.close,
            volume=Quantity(b_in.volume.as_double(), SIZE_PRECISION), # Stellt korrekte Präzision sicher
            ts_event=b_in.ts_event, ts_init=b_in.ts_init
        ))
    print(f"INFO: Transformer: {len(final_bars)} Bar-Objekte für Katalog vorbereitet.")
else:
    print("WARNUNG: Transformer: Keine gültigen Bar-Objekte vom Wrangler erhalten. Nichts zu speichern.")
    exit()

# === Im Katalog speichern ===
if final_bars:
    catalog = ParquetDataCatalog(path=CATALOG_ROOT_PATH)
    instrument_for_meta = TestInstrumentProvider.btcusdt_binance()
    # Sicherstellen, dass das Metadaten-Instrument mit der SIZE_PRECISION der Daten übereinstimmt
    if instrument_for_meta.size_precision != SIZE_PRECISION:
        print(f"WARNUNG: Transformer: size_precision des Metadaten-Instruments ({instrument_for_meta.size_precision}) "
              f"weicht von Daten-Präzision ({SIZE_PRECISION}) ab. Erwäge manuelle Anpassung des Instruments.")
    catalog.write_data([instrument_for_meta])
    catalog.write_data(final_bars)
    print(f"INFO: Transformer: {len(final_bars)} Bars und Metadaten in '{CATALOG_ROOT_PATH.resolve()}' geschrieben.")
    print(f"INFO: Transformer: Bar-Daten wurden für BarType '{FINAL_BAR_TYPE_STR_FOR_CATALOG}' gespeichert.")
else:
    print("WARNUNG: Transformer: Keine finalen Bars zum Schreiben vorhanden.")

print("INFO: Transformer: Daten-Transformation erfolgreich abgeschlossen.") 
