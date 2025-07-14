"""
Einfache Databento ES.FUT Download/Transform für NautilusTrader 1.219
Folgt Databento Standards - keine komplexen Konvertierungen
"""
import time
import databento as db
import pandas as pd
from pathlib import Path
from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
import shutil


def download_dbn(symbol, start_date, end_date, dataset, schema, api_key, raw_dir):
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
        stype_in="continuous",  # ← Standard ES.FUT
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


def transform_dbn_to_parquet(symbol, raw_dir, catalog_root_path, venue="GLBX", delete_raw_dir=True):
    raw_dir = Path(raw_dir)
    
    organized_path = Path(catalog_root_path) / "ES_FUTURES_2024_GLBX"
    organized_path.mkdir(parents=True, exist_ok=True)
    
    files = list(raw_dir.rglob("*.dbn*"))
    if not files:
        print("[WARNING] Keine DBN-Dateien gefunden")
        return
    
    loader = DatabentoDataLoader()
    catalog = ParquetDataCatalog(path=organized_path)
    
    print(f"[INFO] Transformiere {len(files)} DBN-Dateien...")
    print(f"[INFO] Speichere in: {organized_path}")
    
    for data_file in files:
        try:
            data = loader.from_dbn_file(
                path=str(data_file),
                instrument_id=None,
                as_legacy_cython=True,
                use_exchange_as_venue=False,  # ← ÄNDERUNG: False statt True!
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

def continous_reprocessing_parquet(
    contract_dir,
    output_contract_dir,
    continuous_contract_name="ES.c.0.GLBX"
):
    import pandas as pd
    from pathlib import Path

    contract_dir = Path(contract_dir)
    output_contract_dir = Path(output_contract_dir)
    output_contract_dir.mkdir(parents=True, exist_ok=True)

    # Rekursiv alle Parquet-Dateien in allen Unterordnern finden
    contract_files = sorted(contract_dir.rglob("*.parquet"))
    contract_dfs = []
    for file in contract_files:
        if file.stat().st_size > 0:
            try:
                df = pd.read_parquet(file)
                if "ts_event" in df.columns:
                    contract_dfs.append(df)
                else:
                    print(f"[WARNING] Datei {file} enthält keine 'ts_event'-Spalte und wird übersprungen.")
            except Exception as e:
                print(f"[WARNING] Datei {file} konnte nicht als Parquet geladen werden: {e}")

    if contract_dfs:
        continuous_contract_df = pd.concat(contract_dfs, ignore_index=True)
        continuous_contract_df.sort_values("ts_event", inplace=True)
        continuous_contract_path = output_contract_dir / f"{continuous_contract_name}.parquet"
        continuous_contract_df.to_parquet(continuous_contract_path)
        print(f"[INFO] Continuous Future Parquet gespeichert unter: {continuous_contract_path}")
    else:
        print("[WARNING] Keine gültigen Parquet-Kontraktdateien mit 'ts_event'-Spalte gefunden.")