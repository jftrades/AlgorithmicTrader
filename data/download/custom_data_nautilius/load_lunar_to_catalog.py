# lunar_csv_to_catalog.py
import pandas as pd
from pathlib import Path
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.core.datetime import dt_to_unix_nanos

# Unsere Custom-Klasse importieren
from data.download.custom_data_nautilius.lunar_data import LunarData


def load_lunar_csv_to_catalog(csv_path: str, catalog_path: str, instrument_str: str):
    df = pd.read_csv(csv_path)

    instrument_id = InstrumentId(Symbol(instrument_str), Venue("BINANCE"))
    records = []

    for _, row in df.iterrows():
        # timestamp → datetime → unix nanos
        ts_event = dt_to_unix_nanos(pd.to_datetime(row["datetime"], utc=True))
        ts_init = ts_event

        data = LunarData(
            instrument_id=instrument_id,
            ts_event=ts_event,
            ts_init=ts_init,
            contributors_active=row["contributors_active"],
            contributors_created=row["contributors_created"],
            interactions=row["interactions"],
            posts_active=row["posts_active"],
            posts_created=row["posts_created"],
            sentiment=row["sentiment"],
            spam=row["spam"],
            alt_rank=row["alt_rank"],
            circulating_supply=row["circulating_supply"],
            close=row["close"],
            galaxy_score=row["galaxy_score"],
            high=row["high"],
            low=row["low"],
            market_cap=row["market_cap"],
            market_dominance=row["market_dominance"],
            open=row["open"],  # CSV hat "open", Klasse hat "open_"
            social_dominance=row["social_dominance"],
            volume_24h=row["volume_24h"],
        )
        records.append(data)

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data(records)
    print(f"✅ {len(records)} LunarData Einträge in {catalog_path} gespeichert.")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2] / "DATA_STORAGE"

    # Hier deine Pfade anpassen
    catalog_path = str(base_dir / "data_catalog_wrangled")
    csv_path = str(base_dir / "processed_lunarcrush_2024-10-01_to_2024-10-31" / "csv"/ "BTC_LUNARCRUSH_2024-10-01_to_2024-10-31.csv")

    load_lunar_csv_to_catalog(csv_path, catalog_path, "BTCUSDT-PERP")
