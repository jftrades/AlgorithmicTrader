import pandas as pd
from pathlib import Path
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.core.datetime import dt_to_unix_nanos
from data.download.custom_data_nautilius.aggTrades_data import AggTradeData


def load_agg_csv_to_catalog(csv_path: str, catalog_path: str, instrument_str: str):
    df = pd.read_csv(csv_path)

    print(f"📂 Lade CSV: {csv_path}")
    print(df.head())
    print("➡️ Anzahl Zeilen:", len(df))

    instrument_id = InstrumentId(Symbol(instrument_str), Venue("BINANCE"))
    records = []

    for _, row in df.iterrows():
        ts_event = int(row["transact_time"]) * 1_000_000  # ms → ns
        ts_init = ts_event
        is_buyer_maker = str(row["is_buyer_maker"]).lower() == "true"

        data = AggTradeData(
            instrument_id=instrument_id,
            ts_event=ts_event,
            ts_init=ts_init,
            agg_trade_id=int(row["agg_trade_id"]),
            price=float(row["price"]),
            quantity=float(row["quantity"]),
            first_trade_id=int(row["first_trade_id"]),
            last_trade_id=int(row["last_trade_id"]),
            is_buyer_maker=is_buyer_maker,
        )
        records.append(data)

    if not records:
        print("⚠️ Keine Records erstellt – CSV leer oder Parsing kaputt.")
        return

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data(records)

    print(f"✅ {len(records)} AggTradeData Einträge in {catalog_path} gespeichert.")
    print("🔎 Beispiel:", records[0])

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2] / "DATA_STORAGE"
    catalog_path = str(base_dir / "data_catalog_wrangled")
    csv_path = str(base_dir / "aggtrades_raw/csv/BTCUSDT_AGGTRADES_2024-01-01_to_2024-01-05.csv")

    load_agg_csv_to_catalog(csv_path, catalog_path, "BTCUSDT-PERP")
