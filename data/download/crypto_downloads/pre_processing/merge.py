from pathlib import Path
import pandas as pd

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE"/ "csv_data_catalog"

# Quelle: Ergebnis von pre_processing (oder alternativ FILTERED_ROOT verwenden)
SOURCE_ROOT = BASE_DATA_DIR / "csv_data_all_filtered"    # bei Bedarf ändern auf "csv_data_all_filtered"
OUTPUT_DIR = BASE_DATA_DIR / "csv_data_all_merged"
OUTPUT_FILENAME = "all_matched_data.csv"

MATCHED_NAME = "matched_data_filtered.csv"

SORT_BY_TIMESTAMP = False        # True => final nach timestamp_nano sortieren (kostet RAM)
FILL_VALUE = 0                   # Wert für fehlende Spalten

def discover_files():
    for sub in sorted(SOURCE_ROOT.iterdir()):
        if not sub.is_dir():
            continue
        file = sub / MATCHED_NAME
        if file.exists():
            yield sub.name, file

def union_columns(file_infos):
    cols = set()
    for _, f in file_infos:
        try:
            head = pd.read_csv(f, nrows=1)
            cols.update(head.columns.tolist())
        except Exception:
            continue
    return list(cols)

def stream_merge(file_infos, all_columns, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header_written = False
    total_rows = 0
    meta = []
    for inst, f in file_infos:
        try:
            df = pd.read_csv(f)
        except Exception as e:
            print(f"[SKIP] {inst}: read error {e}")
            continue
        if df.empty:
            print(f"[SKIP] {inst}: empty")
            continue
        # Reindex auf vollständiges Schema
        df = df.reindex(columns=all_columns)
        df = df.fillna(FILL_VALUE)
        rows = len(df)
        mode = "w" if not header_written else "a"
        df.to_csv(out_path, mode=mode, header=not header_written, index=False)
        header_written = True
        total_rows += rows
        meta.append((inst, rows))
        print(f"[OK] {inst}: {rows} rows appended")
    return meta, total_rows

def optional_sort(out_path):
    df = pd.read_csv(out_path)
    if "timestamp_nano" in df.columns:
        df = df.sort_values("timestamp_nano")
    elif "timestamp" in df.columns:
        df = df.sort_values("timestamp")
    df.to_csv(out_path, index=False)
    print("[INFO] Final file sorted.")

def run():
    if not SOURCE_ROOT.exists():
        raise FileNotFoundError(f"Source root not found: {SOURCE_ROOT}")
    files = list(discover_files())
    if not files:
        raise RuntimeError("No matched_data.csv files found.")
    all_cols = union_columns(files)
    out_path = OUTPUT_DIR / OUTPUT_FILENAME
    meta, total = stream_merge(files, all_cols, out_path)
    if SORT_BY_TIMESTAMP:
        optional_sort(out_path)
    print("\nSummary:")
    for inst, rows in meta:
        print(f"  {inst}: {rows}")
    print(f"TOTAL rows: {total}")
    print(f"OUTPUT: {out_path}")

if __name__ == "__main__":
    run()
