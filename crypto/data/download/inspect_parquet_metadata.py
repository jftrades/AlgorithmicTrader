import pyarrow.parquet as pq
from pathlib import Path

# Passe diesen Pfad ggf. an deinen Katalog an!
parquet_dir = Path("C:/Users/Ferdi/Desktop/projectx/AlgorithmicTrader/crypto/data/DATA_STORAGE/data_catalog_wrangled/data/trade_tick/BTCUSDT-PERP.BINANCE")

print(f"Prüfe Parquet-Dateien in: {parquet_dir}")

files = list(parquet_dir.glob("*.parquet"))
if not files:
    print("❌ Keine Parquet-Dateien gefunden!")
    exit(1)

for file in files:
    print(f"\n--- {file.name} ---")
    try:
        pq_file = pq.ParquetFile(file)
        meta = pq_file.metadata
        print(f"Spalten: {pq_file.schema.names}")
        print(f"Anzahl Zeilen: {meta.num_rows}")
        # Parquet key-value metadata
        kv_meta = meta.metadata
        if kv_meta:
            print("Key-Value-Metadaten:")
            for k, v in kv_meta.items():
                print(f"  {k}: {v}")
        else:
            print("Keine Key-Value-Metadaten gefunden.")
        # Zeige die ersten Zeilen als DataFrame
        df = pq.read_table(file).to_pandas().head(3)
        print("Beispiel-Daten:")
        print(df)
    except Exception as e:
        print(f"❌ Fehler beim Lesen: {e}")
