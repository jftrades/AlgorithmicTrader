"""
Einfache Databento ES.FUT Download/Transform für NautilusTrader 1.219
Folgt Databento Standards - keine komplexen Konvertierungen
"""
import time
import databento as db
from pathlib import Path
from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
import shutil


def download_dbn(symbol, start_date, end_date, dataset, schema, api_key, raw_dir):
    """Standard DBN-Download"""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    client = db.Historical(api_key)
    print(f"[INFO] Download {schema} für {symbol}")
    
    job = client.batch.submit_job(
        dataset=dataset,
        start=start_date,
        end=end_date,
        symbols=symbol,
        schema=schema,
        split_duration="month",
        stype_in="parent",  # ← Standard ES.FUT
    )
    
    print(f"[INFO] Job ID: {job['id']}")
    
    while True:
        done_jobs = [j["id"] for j in client.batch.list_jobs("done")]
        if job["id"] in done_jobs:
            break
        time.sleep(1.0)
    
    files = client.batch.download(job_id=job["id"], output_dir=raw_dir)
    print(f"[INFO] {len(files)} Dateien heruntergeladen")
    return files


def transform_dbn_to_parquet(symbol, raw_dir, catalog_root_path, venue="XCME", delete_raw_dir=True):
    """OFFIZIELLE Nautilus DBN→Parquet via Catalog"""
    raw_dir = Path(raw_dir)
    catalog_root_path = Path(catalog_root_path)
    catalog_root_path.mkdir(parents=True, exist_ok=True)
    
    files = list(raw_dir.rglob("*.dbn*"))
    if not files:
        print(f"[WARNING] Keine DBN-Dateien")
        return
    
    # OFFIZIELLE METHODE: Catalog macht alles automatisch
    catalog = ParquetDataCatalog(path=catalog_root_path)
    
    print(f"[INFO] Importiere {len(files)} DBN-Dateien via Catalog...")
    
    for data_file in files:
        try:
            print(f"[INFO] Importiere: {data_file.name}")
            catalog.write_data(str(data_file))
            print(f"  ✓ Erfolgreich importiert")
            
        except Exception as e:
            print(f"  ✗ Fehler: {e}")
            continue
    
    print(f"[INFO] ✓ Import abgeschlossen")
    
    if delete_raw_dir and raw_dir.exists():
        shutil.rmtree(raw_dir)
        print(f"[INFO] Raw-Dateien gelöscht")