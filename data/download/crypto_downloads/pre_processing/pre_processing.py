from pathlib import Path
import pandas as pd
import shutil

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data_catalog"
INPUT_ROOT = BASE_DATA_DIR / "csv_data_all"
OUTPUT_ROOT = BASE_DATA_DIR / "csv_data_all_processed"
FNG_DIR_NAME = "FNG-INDEX.BINANCE"
FNG_FILE = INPUT_ROOT / FNG_DIR_NAME / "FNG.csv"
DOMINANCE_DIR_NAME = "DOMINANCE.BINANCE"
DOMINANCE_FILE = INPUT_ROOT / DOMINANCE_DIR_NAME / "DOMINANCE.csv"


def _read_csv_safe(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _prepare_time(df: pd.DataFrame, col: str = "timestamp_nano") -> pd.DataFrame:
    if col not in df.columns:
        raise ValueError(f"Missing required timestamp column '{col}'")
    df = df.copy()
    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df = df.dropna(subset=[col])
    df[col] = df[col].astype("int64")
    df = df.sort_values(col)
    return df


def _merge_asof(base: pd.DataFrame,
                feat: pd.DataFrame,
                right_key: str,
                prefix: str,
                forward_fill: bool = True,
                fill_zeros: bool = True) -> pd.DataFrame:
    if feat is None or feat.empty:
        return base
    feat = feat.copy()

    target_time_col = f"{prefix}_timestamp_nano"
    if right_key != target_time_col:
        feat = feat.rename(columns={right_key: target_time_col})
        right_key = target_time_col

    rename_map = {}
    for c in feat.columns:
        if c == right_key:
            continue
        if not c.startswith(f"{prefix}_"):
            rename_map[c] = f"{prefix}_{c}"
    if rename_map:
        feat = feat.rename(columns=rename_map)

    # Sort + eindeutige Zeitstempel (letzter Wert gewinnt)
    feat = feat.sort_values(right_key).drop_duplicates(subset=[right_key], keep="last")
    feat = feat.sort_values(right_key)

    merged = pd.merge_asof(
        base.sort_values("timestamp_nano"),
        feat,
        left_on="timestamp_nano",
        right_on=right_key,
        direction="backward",
    )

    if forward_fill:
        new_cols = [c for c in feat.columns if c != right_key]
        merged[new_cols] = merged[new_cols].ffill()

    return merged


def load_fng():
    if not FNG_FILE.exists():
        return None
    fng = pd.read_csv(FNG_FILE)
    if "timestamp_nano" not in fng.columns:
        # Reconstruct from ISO if needed
        if "timestamp_iso" in fng.columns:
            fng["timestamp_nano"] = pd.to_datetime(fng["timestamp_iso"], utc=True, errors="coerce").astype("int64")
        else:
            raise ValueError("FNG file missing timestamp_nano and timestamp_iso.")
    fng = _prepare_time(fng, "timestamp_nano")
    # Normalisieren
    if "fear_greed" in fng.columns:
        fng["fng"] = pd.to_numeric(fng["fear_greed"], errors="coerce")
    elif "fng" not in fng.columns:
        raise ValueError("FNG file missing fear_greed/fng column.")
    if "classification" in fng.columns:
        fng["fng_classification"] = fng["classification"]
    elif "fng_classification" not in fng.columns:
        fng["fng_classification"] = ""
    keep = ["timestamp_nano", "fng", "fng_classification"]
    return fng[keep].sort_values("timestamp_nano")


def load_dominance():
    if not DOMINANCE_FILE.exists():
        return None
    dom = pd.read_csv(DOMINANCE_FILE)
    if "timestamp_nano" not in dom.columns:
        if "timestamp_iso" in dom.columns:
            dom["timestamp_nano"] = pd.to_datetime(dom["timestamp_iso"], utc=True, errors="coerce").astype("int64")
        else:
            raise ValueError("Dominance file missing timestamp_nano and timestamp_iso.")
    dom = _prepare_time(dom, "timestamp_nano")
    # Unnötige Spalten entfernen
    dom = dom.drop(columns=[c for c in ["timestamp_iso", "instrument_id"] if c in dom.columns], errors="ignore")
    # Sicherstellen, dass mindestens eine Metrik vorhanden ist
    metric_cols = [c for c in dom.columns if c != "timestamp_nano"]
    if not metric_cols:
        return None
    return dom[["timestamp_nano"] + metric_cols].sort_values("timestamp_nano")


def process_symbol_dir(sym_dir: Path, fng_df: pd.DataFrame, dom_df: pd.DataFrame):
    symbol = sym_dir.name
    ohlcv_path = sym_dir / "OHLCV.csv"
    metrics_path = sym_dir / "METRICS.csv"
    lunar_path = sym_dir / "LUNAR.csv"

    ohlcv = _read_csv_safe(ohlcv_path)
    if ohlcv is None:
        print(f"[SKIP] {symbol}: OHLCV.csv fehlt.")
        return

    required_ohlcv = {"timestamp_nano", "timestamp_iso", "symbol", "open", "high", "low", "close", "volume"}
    missing = required_ohlcv.difference(ohlcv.columns)
    if missing:
        print(f"[WARN] {symbol}: OHLCV fehlende Spalten {missing}, skip.")
        return

    ohlcv = _prepare_time(ohlcv, "timestamp_nano")
    ohlcv = ohlcv.sort_values("timestamp_nano").reset_index(drop=True)

    # Basis DataFrame + instrument_id
    merged = ohlcv.copy()
    merged["instrument_id"] = merged["symbol"]

    # METRICS
    metrics = _read_csv_safe(metrics_path)
    if metrics is not None and not metrics.empty:
        metrics = _prepare_time(metrics, "timestamp_nano")
        # Drop duplicate columns if exist
        drop_cols = {"symbol", "timestamp_iso"}
        metrics = metrics.drop(columns=[c for c in drop_cols if c in metrics.columns], errors="ignore")
        merged = _merge_asof(merged, metrics, right_key="timestamp_nano", prefix="metrics")

    # LUNAR
    lunar = _read_csv_safe(lunar_path)
    if lunar is not None and not lunar.empty:
        lunar = _prepare_time(lunar, "timestamp_nano")
        drop_cols = {"symbol", "timestamp_iso"}
        lunar = lunar.drop(columns=[c for c in drop_cols if c in lunar.columns], errors="ignore")
        merged = _merge_asof(merged, lunar, right_key="timestamp_nano", prefix="lunar")

    # FNG (global)
    if fng_df is not None and not fng_df.empty:
        merged = _merge_asof(merged, fng_df, right_key="timestamp_nano", prefix="fng")

    # dominance (global)
    if dom_df is not None and not dom_df.empty:
        merged = _merge_asof(merged, dom_df, right_key="timestamp_nano", prefix="dom")

    # Spaltenordnung bauen
    base_cols = ["timestamp_nano", "timestamp_iso", "instrument_id", "open", "high", "low", "close", "volume"]
    metrics_cols = sorted([c for c in merged.columns if c.startswith("metrics_")])
    lunar_cols = sorted([c for c in merged.columns if c.startswith("lunar_")])
    fng_cols = sorted([c for c in merged.columns if c.startswith("fng_")])
    dom_cols = sorted([c for c in merged.columns if c.startswith("dom_")])
    others = [c for c in merged.columns if c not in base_cols + metrics_cols + lunar_cols + fng_cols + dom_cols]
    # Ensure base first, then features
    final_cols = base_cols + metrics_cols + lunar_cols + fng_cols + dom_cols + [c for c in others if c not in base_cols]

    merged = merged[final_cols]

    # fill empty entries with 0
    merged = merged.replace("", pd.NA).fillna(0)

    # Output schreiben
    out_dir = OUTPUT_ROOT / symbol
    if out_dir.exists():
        shutil.rmtree(out_dir)
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "matched_data.csv"
    merged.to_csv(out_file, index=False)
    print(f"[OK] {symbol}: merged rows={len(merged)} -> {out_file}")


def run():
    if not INPUT_ROOT.exists():
        raise FileNotFoundError(f"Input root not found: {INPUT_ROOT}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    fng_df = load_fng()
    if fng_df is None:
        print("[WARN] Kein FNG gefunden – fng Spalten bleiben leer.")

    dom_df = load_dominance()
    if dom_df is None:
        print("[WARN] Keine Dominance-Daten gefunden – dom Spalten bleiben leer.")

    for sym_dir in sorted(INPUT_ROOT.iterdir()):
        if not sym_dir.is_dir():
            continue
        if sym_dir.name in {FNG_DIR_NAME, DOMINANCE_DIR_NAME}:
            continue
        process_symbol_dir(sym_dir, fng_df, dom_df)


if __name__ == "__main__":
    run()
