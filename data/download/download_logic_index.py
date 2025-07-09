"""
Transformationslogik und Download für Index-Daten von Databento DBN zu NautilusTrader Parquet
Kompatibel zu NautilusTrader 1.219
wichtig: lädt in batches herunter
"""
import operator
import time
import databento as db
from pathlib import Path
from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
import shutil


def download_dbn(symbol, start_date, end_date, dataset, schema, encoding, api_key, raw_dir):
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    print("[INFO] Starte Batch-Job für DBN-Download von Databento...")
    client = db.Historical(api_key)
    new_job = client.batch.submit_job(
        dataset=dataset,
        start=start_date,
        end=end_date,
        symbols=symbol,
        schema=schema,
        split_duration="month",
        stype_in="parent",
    )
    new_job_id = new_job["id"]
    print(f"[INFO] Batch-Job ID: {new_job_id}")
    # Warten bis der Job fertig ist
    while True:
        done_jobs = list(map(operator.itemgetter("id"), client.batch.list_jobs("done")))
        if new_job_id in done_jobs:
            break
        time.sleep(1.0)
    print("[INFO] Batch-Job abgeschlossen. Lade Dateien...")
    downloaded_files = client.batch.download(
        job_id=new_job_id,
        output_dir=raw_dir,
    )
    print(f"[INFO] DBN-Dateien heruntergeladen: {[str(f) for f in downloaded_files]}")
    return downloaded_files

def transform_dbn_to_parquet(symbol, raw_dir, catalog_root_path, venue="XCME", delete_raw_dir=True):
    raw_dir = Path(raw_dir)
    catalog_root_path = Path(catalog_root_path)
    print(f"[INFO] Suche DBN-Dateien rekursiv in {raw_dir} ...")
    files = list(raw_dir.rglob("*.dbn*"))
    if not files:
        raise FileNotFoundError(f"Keine DBN-Dateien gefunden in {raw_dir}")
    for data_file in files:
        print(f"[INFO] Lade DBN-Datei: {data_file}")
        loader = DatabentoDataLoader()
        instrument_id = InstrumentId.from_str(f"{symbol}.{venue}")
        bars = loader.from_dbn_file(
            path=str(data_file),
            instrument_id=instrument_id,
            as_legacy_cython=False,
        )
        catalog_root_path.mkdir(parents=True, exist_ok=True)
        catalog = ParquetDataCatalog(path=catalog_root_path)
        catalog.write_data(bars)
        print(f"[INFO] {len(bars)} Bars aus {data_file} in '{catalog_root_path.resolve()}' gespeichert.")
    # Nach Verarbeitung: Lösche den gesamten Raw-Ordner inkl. aller Unterordner und Dateien
    if delete_raw_dir:
        try:
            shutil.rmtree(raw_dir)
            print(f"[INFO] Gesamter Rohdaten-Ordner gelöscht: {raw_dir}")
        except Exception as e:
            print(f"[WARN] Löschen des Rohdaten-Ordners fehlgeschlagen: {e}")

