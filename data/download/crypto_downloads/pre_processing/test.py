import sys
from pathlib import Path
import pandas as pd

# Default: Beispiel-Datei (anpassen oder per Argument übergeben)
DEFAULT_INPUT = Path(r"C:\Users\Karmalker\Desktop\projectX\AlgorithmicTrader\data\DATA_STORAGE\csv_data_processed\DOGEUSDT-PERP\matched_data.csv")

KEEP_COLS = [
    "timestamp_iso",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "fng_fng",
    "lunar_market_dominance"
]

def trim_csv(input_path: Path):
    if not input_path.exists():
        print(f"[ERROR] Datei nicht gefunden: {input_path}")
        return
    df = pd.read_csv(input_path)
    missing = [c for c in KEEP_COLS if c not in df.columns]
    if missing:
        print(f"[ERROR] Fehlende Spalten: {missing}")
        return

    # Neu: timestamp_iso in Format "YYYY-MM-DD HH:MM:SS" umwandeln
    try:
        df["timestamp_iso"] = pd.to_datetime(df["timestamp_iso"], utc=True, errors="coerce") \
                                .dt.tz_convert(None) \
                                .dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"[WARN] Konnte timestamp_iso nicht konvertieren: {e}")

    trimmed = df[KEEP_COLS].copy()
    out_path = input_path.with_name(input_path.stem + "_trimmed2.csv")
    trimmed.to_csv(out_path, index=False)
    print(f"[OK] Gespeichert: {out_path}  (Rows={len(trimmed)})")

if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    trim_csv(path)
