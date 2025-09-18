import sys
from pathlib import Path
import pandas as pd

# Default: Beispiel-Datei (anpassen oder per Argument übergeben)
DEFAULT_INPUT = Path(r"C:\Users\Karmalker\Desktop\projectX\AlgorithmicTrader\data\DATA_STORAGE\csv_data_processed\AI16ZUSDT-PERP\matched_data.csv")

KEEP_COLS = [
    "open",
    "high",
    "low",
    "close",
    "lunar_galaxy_score",
    "fng_fng"
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
    trimmed = df[KEEP_COLS].copy()
    out_path = input_path.with_name(input_path.stem + "_trimmed.csv")
    trimmed.to_csv(out_path, index=False)
    print(f"[OK] Gespeichert: {out_path}  (Rows={len(trimmed)})")

if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    trim_csv(path)
