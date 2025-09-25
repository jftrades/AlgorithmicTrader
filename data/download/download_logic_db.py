from pathlib import Path
from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.instruments import FuturesContract
import shutil
import time
import databento as db


def download_dbn(symbol, start_date, end_date, dataset, schema, api_key, raw_dir, stype_out="instrument_id"):
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
        stype_in="raw_symbol",
        stype_out=stype_out,
    )
    
    print(f"[INFO] Job ID: {job['id']}")
    
    while True:
        done_jobs = [j["id"] for j in client.batch.list_jobs("done")]
        if job["id"] in done_jobs:
            break
        time.sleep(1.0)
    
    files = client.batch.download(job_id=job["id"], output_dir=raw_dir)
    print(f"[INFO] {len(files)} Dateien heruntergeladen")
    print(files)
    return files


def transform_dbn_to_parquet(symbol, raw_dir, catalog_root_path, venue="GLBX", delete_raw_dir=True, flat_structure=False):
    raw_dir = Path(raw_dir)
    
    if flat_structure:
        organized_path = Path(catalog_root_path)
    else:
        organized_path = Path(catalog_root_path) / f"{symbol}_{venue}"
    
    organized_path.mkdir(parents=True, exist_ok=True)
    
    files = list(raw_dir.rglob("*.dbn*"))
    if not files:
        print("[WARNING] Keine DBN-Dateien gefunden")
        return
    
    loader = DatabentoDataLoader()
    catalog = ParquetDataCatalog(path=organized_path)
    
    print(f"[INFO] Transformiere {len(files)} DBN-Dateien...")
    print(f"[INFO] Speichere in: {organized_path}")
    print(f"[INFO] Target venue: {venue}")
    
    for data_file in files:
        try:
            data = loader.from_dbn_file(
                path=str(data_file),
                instrument_id=None,
                as_legacy_cython=True,
                use_exchange_as_venue=False,
            )
            
            if data:
                catalog.write_data(data)
                print(f"  ✓ {data_file.name}: {len(data)} Objekte")
                
        except Exception as e:
            print(f"  ✗ {data_file.name}: {e}")
            continue
    
    if delete_raw_dir and raw_dir.exists():
        shutil.rmtree(raw_dir)
        
    print(f"[INFO] ✓ Fertig in: {organized_path}")
