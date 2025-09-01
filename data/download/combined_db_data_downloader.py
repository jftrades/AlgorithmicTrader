from pathlib import Path
from dotenv import load_dotenv
import os
import shutil
from data.download.download_logic_db import download_dbn, transform_dbn_to_parquet

load_dotenv()

# Parameter 
# Futures Contract Month Codes:
# H = March (März)
# M = June (Juni)
# U = September (September)
# Z = December (Dezember)

symbol = "ESH4"
start_date = "2024-01-01"
end_date = "2024-12-30"
dataset = "GLBX.MDP3"
venue = "GLBX"
base_data_dir = str(Path(__file__).resolve().parents[1] / "DATA_STORAGE")
raw_dir = Path(base_data_dir) / "raw_downloads"

# Angepasste Pfad-Struktur - berücksichtigt Nautilus' automatische Ordnerstruktur
catalog_wrangled = Path(base_data_dir) / "data_catalog_wrangled"
data_root = catalog_wrangled / "data"

bar_catalog_path = catalog_wrangled  # Nautilus wird data/bar/ hinzufügen
futures_catalog_path = catalog_wrangled  # Let Nautilus create the structure, we'll specify the final path differently

api_key = os.getenv("DATABENTO_API_KEY")

if not api_key:
    raise ValueError("DATABENTO_API_KEY nicht gefunden! Bitte in .env setzen.")

if __name__ == "__main__":
    try:
        # Download OHLCV (Bar-Daten) - use instrument_id to get GLBX venue
        download_dbn(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            dataset=dataset,
            schema="ohlcv-1m",
            api_key=api_key,
            raw_dir=raw_dir / "bars",
            stype_out="instrument_id",  # This should give us GLBX venue
        )
    
        # Download Definitionen (Contract-Daten) - use instrument_id
        download_dbn(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            dataset=dataset,
            schema="definition",
            api_key=api_key,
            raw_dir=raw_dir / "definitions",
            stype_out="instrument_id",  # This should give us GLBX venue
        )
        
        # Transformiere Bar-Daten - Nautilus fügt data/bar automatisch hinzu
        transform_dbn_to_parquet(
            symbol=symbol,
            raw_dir=raw_dir / "bars",
            catalog_root_path=bar_catalog_path,  # catalog_wrangled - Nautilus fügt data/bar/ hinzu
            venue=venue,
            delete_raw_dir=False,
            flat_structure=True,
        )
        
        # Transformiere Contract-Definitionen - need to create custom path structure
        # Create the futures_contract directory manually first
        manual_futures_path = data_root / "futures_contract" / symbol
        manual_futures_path.mkdir(parents=True, exist_ok=True)
        
        transform_dbn_to_parquet(
            symbol=symbol,
            raw_dir=raw_dir / "definitions", 
            catalog_root_path=manual_futures_path.parent.parent.parent,  # Go back one more level
            venue=venue,
            delete_raw_dir=False,
            flat_structure=True,
        )
        
        print(f"[INFO] Bar-Daten sollten sein in: {catalog_wrangled}/data/bar/")
        print(f"[INFO] Contract-Daten sollten sein in: {data_root}/futures_contract/{symbol}/")
    finally:
        # Am Ende raw_downloads komplett löschen
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
            print(f"[INFO] Raw downloads gelöscht: {raw_dir}")
