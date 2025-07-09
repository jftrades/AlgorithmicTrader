"""
Zentrale Steuerung für Index-Daten-Download und -Transformation via Databento
Kompatibel zu NautilusTrader 1.219
API-Key wird sicher aus .env/Umgebung geladen (niemals im Code speichern!)
"""
from pathlib import Path
from dotenv import load_dotenv
import os
from data.download.download_logic_index import download_dbn, transform_dbn_to_parquet

# .env laden (falls vorhanden)
load_dotenv()

# Zentrale Parameter
symbol = "ES.FUT"
start_date = "2011-01-01"
end_date = "2025-07-01"
dataset = "GLBX.MDP3"
schema = "ohlcv-1d"
encoding = "dbn"
venue = "XCME"
base_data_dir = str(Path(__file__).resolve().parents[1] / "DATA_STORAGE")
raw_dir = Path(base_data_dir) / "raw_downloads"
catalog_root_path = Path(base_data_dir) / "data_catalog_wrangled"
api_key = os.getenv("DATABENTO_API_KEY")

if not api_key:
    raise ValueError("DATABENTO_API_KEY nicht gefunden! Bitte in .env oder als Umgebungsvariable setzen.")

dbn_file = raw_dir / f"{symbol}_{schema}_{start_date}_{end_date}.dbn"

if __name__ == "__main__":
    downloaded_files = download_dbn(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        dataset=dataset,
        schema=schema,
        encoding=encoding,
        api_key=api_key,
        raw_dir=raw_dir,
    )
    transform_dbn_to_parquet(
        symbol=symbol,
        raw_dir=raw_dir,
        catalog_root_path=catalog_root_path,
        venue=venue,
    )
