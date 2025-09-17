import pandas as pd
from pathlib import Path
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.core.datetime import dt_to_unix_nanos
from data.download.custom_data_nautilius.metrics_data import MetricsData

# Wichtig: Registrierung vor dem Schreiben!
from nautilus_trader.serialization.base import register_serializable_type
from nautilus_trader.serialization.arrow.serializer import register_arrow




def load_metrics_csv_to_catalog(csv_path: str, catalog_path: str, instrument_str: str):
    df = pd.read_csv(csv_path)

    instrument_id = InstrumentId(Symbol(instrument_str), Venue("BINANCE"))
    records = []

    for _, row in df.iterrows():
        ts_event = dt_to_unix_nanos(pd.to_datetime(row["create_time"], utc=True))
        ts_init = ts_event
        data = MetricsData(
            instrument_id=instrument_id,
            ts_event=ts_event,
            ts_init=ts_init,
            sum_open_interest=row["sum_open_interest"],
            sum_open_interest_value=row["sum_open_interest_value"],
            count_toptrader_long_short_ratio=row["count_toptrader_long_short_ratio"],
            sum_toptrader_long_short_ratio=row["sum_toptrader_long_short_ratio"],
            count_long_short_ratio=row["count_long_short_ratio"],
            sum_taker_long_short_vol_ratio=row["sum_taker_long_short_vol_ratio"],
        )
        records.append(data)

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data(records)
    print(f"{len(records)} MetricsData Einträge in {catalog_path} gespeichert.")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2] / "DATA_STORAGE"
    catalog_path = str(base_dir / "data_catalog_wrangled")
    csv_path = str(base_dir / "metrics_raw/csv/BTCUSDT_METRICS_2024-01-01_to_2025-01-01.csv")

    load_metrics_csv_to_catalog(csv_path, catalog_path, "BTCUSDT-PERP")

