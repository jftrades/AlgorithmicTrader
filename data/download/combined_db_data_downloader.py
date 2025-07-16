
from pathlib import Path
from dotenv import load_dotenv
import os
from data.download.download_logic_index import download_dbn, transform_dbn_to_parquet

load_dotenv()

# Parameter
symbol = "AAPL"
start_date = "2018-05-01"
end_date = "2025-07-14"
dataset = "XNAS.ITCH"
venue = "Nasdaq"
base_data_dir = str(Path(__file__).resolve().parents[1] / "DATA_STORAGE")
raw_dir = Path(base_data_dir) / "raw_downloads"
catalog_root_path = Path(base_data_dir) / "data_catalog_wrangled"
api_key = os.getenv("DATABENTO_API_KEY")

if not api_key:
    raise ValueError("DATABENTO_API_KEY nicht gefunden! Bitte in .env setzen.")

if __name__ == "__main__":
    # Download OHLCV und Definitionen
    for schema in ["ohlcv-1d", "definition"]:
        download_dbn(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            dataset=dataset,
            schema=schema,
            api_key=api_key,
            raw_dir=raw_dir,
        )
    
    # Transformiere alle DBN-Dateien zu Parquet
    transform_dbn_to_parquet(
        symbol=symbol,
        raw_dir=raw_dir,
        catalog_root_path=catalog_root_path,
        venue=venue,
        delete_raw_dir=False,
    )

