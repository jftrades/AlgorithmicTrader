from pathlib import Path
import pandas as pd

# Basis-/Output-Verzeichnisse analog pre_processing.py
BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE"/ "csv_data_catalog"
PROCESSED_ROOT = BASE_DATA_DIR / "csv_data_all_processed"
FILTERED_ROOT = BASE_DATA_DIR / "csv_data_all_filtered"

INPUT_FILENAME = "matched_data.csv"
OUTPUT_FILENAME = "matched_data_filtered.csv"

# columns to remove
DROP_COLS = {
    "timestamp_nano",
    "timestamp_iso",
    "metrics_timestamp_nano",
    "lunar_close",
    "lunar_high",
    "lunar_low",
    "lunar_open",
    "lunar_timestamp_nano",
    "lunar_volume_24h",
    "fng_classification",
    "fng_timestamp_nano",
    "dom_timestamp_nano",
    "symbol",
}

def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"[WARN] Konnte {path} nicht laden: {e}")
        return None

def _build_timestamp(df: pd.DataFrame) -> pd.Series:
    if "timestamp_iso" in df.columns:
        ts = pd.to_datetime(df["timestamp_iso"], utc=True, errors="coerce")
    elif "timestamp_nano" in df.columns:
        # nanoseconds -> datetime
        ts = pd.to_datetime(pd.to_numeric(df["timestamp_nano"], errors="coerce"), utc=True, unit="ns")
    else:
        raise ValueError("Weder timestamp_iso noch timestamp_nano vorhanden.")
    ts = ts.dropna()
    return ts.dt.strftime("%Y-%m-%d %H:%M:%S")

def process_directory(sym_dir: Path, dest_root: Path):  # geändert: Zielroot
    in_file = sym_dir / INPUT_FILENAME
    if not in_file.exists():
        return
    df = _load_csv(in_file)
    if df is None or df.empty:
        return

    # create new timestamp column
    try:
        new_timestamp = _build_timestamp(df)
    except Exception as e:
        print(f"[SKIP] {sym_dir.name}: Timestamp-Erstellung fehlgeschlagen: {e}")
        return

    # Sortierung anhand vorhandener Zeit (nutze timestamp_iso falls möglich sonst timestamp_nano)
    sort_key = None
    if "timestamp_nano" in df.columns:
        sort_key = ("timestamp_nano", True)   # numerisch
    elif "timestamp_iso" in df.columns:
        sort_key = ("timestamp_iso", False)
    if sort_key:
        key, is_numeric = sort_key
        if is_numeric:
            df[key] = pd.to_numeric(df[key], errors="coerce")
        else:
            df[key] = pd.to_datetime(df[key], utc=True, errors="coerce")
        df = df.sort_values(key).reset_index(drop=True)

    # ts_since_listing (beginnend bei 1)
    df["ts_since_listing"] = range(1, len(df) + 1)
    df["timestamp"] = new_timestamp

    # Spalten entfernen
    cols_to_drop = [c for c in DROP_COLS if c in df.columns]
    df = df.drop(columns=cols_to_drop, errors="ignore")

    # Spalten-Reihenfolge: timestamp, ts_since_listing, instrument_id gefolgt vom Rest
    front = ["timestamp", "ts_since_listing"]
    if "instrument_id" in df.columns:
        front.append("instrument_id")
    remaining = [c for c in df.columns if c not in front]
    df = df[front + remaining]

    out_dir = dest_root / sym_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    print(f"[OK] {sym_dir.name}: {len(df)} Zeilen -> {out_path}")

def run():
    if not PROCESSED_ROOT.exists():
        raise FileNotFoundError(f"Verzeichnis nicht gefunden: {PROCESSED_ROOT}")
    FILTERED_ROOT.mkdir(parents=True, exist_ok=True)
    for sym_dir in sorted(PROCESSED_ROOT.iterdir()):
        if not sym_dir.is_dir():
            continue
        process_directory(sym_dir, FILTERED_ROOT)

if __name__ == "__main__":
    run()
