from pathlib import Path
import pandas as pd
import numpy as np
import json
import math

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE"/ "csv_data_catalog"
MERGED_ROOT = BASE_DATA_DIR / "csv_data_all_merged"
MERGED_FILE = MERGED_ROOT / "all_matched_data.csv"

OUTPUT_ROOT = BASE_DATA_DIR / "cache" / "csv_data_analysis_global"
# Angepasst: Zeitspalte nicht erzwingen (timestamp_nano kann fehlen nach Filter)
REQUIRED_COLS = ["instrument_id", "open", "high", "low", "close", "volume"]

MAX_CORR_FEATURES = 40
DO_CORR = True  # bei Bedarf False setzen

def load_merged() -> pd.DataFrame:
    if not MERGED_FILE.exists():
        raise FileNotFoundError(f"Merged CSV fehlt: {MERGED_FILE}")
    df = pd.read_csv(MERGED_FILE)
    if df.empty:
        raise ValueError("Merged CSV ist leer.")
    return df

def ensure_columns(df: pd.DataFrame):
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Pflichtspalten fehlen: {missing}")

def analyze_instruments(df: pd.DataFrame):
    issues_rows = []
    per_inst_rows = []
    # Zeitbasis bestimmen (timestamp_nano bevorzugt, sonst 'timestamp')
    if "timestamp_nano" in df.columns:
        ts = pd.to_numeric(df["timestamp_nano"], errors="coerce")
    elif "timestamp" in df.columns:
        # bereits im Format YYYY-MM-DD HH:MM:SS
        ts_parsed = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        ts = ts_parsed.view("int64")  # ns
    else:
        ts = pd.Series([np.nan] * len(df), dtype="float64")
        issues_rows.append({"instrument_id": "GLOBAL", "issue": "no_time_column"})
    df["_ts"] = ts
    df = df.dropna(subset=["_ts"])
    df["_ts"] = df["_ts"].astype("int64")

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    grouped = df.groupby("instrument_id", sort=True)
    for inst, g in grouped:
        g_sorted = g.sort_values("_ts")
        monotonic = (g_sorted["_ts"].diff().fillna(0) >= 0).all()
        dup_cnt = int(g_sorted["_ts"].duplicated().sum())
        price_incons = 0
        neg_vol = 0
        if {"open","high","low","close"}.issubset(g_sorted.columns):
            cond = (g_sorted["high"] >= g_sorted["open"]) & \
                   (g_sorted["high"] >= g_sorted["close"]) & \
                   (g_sorted["low"] <= g_sorted["open"]) & \
                   (g_sorted["low"] <= g_sorted["close"]) & \
                   (g_sorted["high"] >= g_sorted["low"])
            price_incons = int((~cond).sum())
        if "volume" in g_sorted.columns:
            neg_vol = int((pd.to_numeric(g_sorted["volume"], errors="coerce") < 0).sum())

        numeric_cols_inst = [c for c in numeric_cols if c not in {"timestamp_nano", "_ts"}]
        total_numeric_cells = len(g_sorted) * len(numeric_cols_inst) if numeric_cols_inst else 0
        zero_values_total = int((g_sorted[numeric_cols_inst] == 0).sum().sum()) if total_numeric_cells else 0
        zero_values_ratio = float(zero_values_total / total_numeric_cells) if total_numeric_cells else 0.0

        issue_list = []
        if not monotonic:
            issue_list.append("non_monotonic_time")
        if dup_cnt > 0:
            issue_list.append(f"duplicate_timestamps={dup_cnt}")
        if price_incons > 0:
            issue_list.append(f"price_inconsistent={price_incons}")
        if neg_vol > 0:
            issue_list.append(f"negative_volume={neg_vol}")

        per_inst_rows.append({
            "instrument_id": inst,
            "rows": len(g_sorted),
            "ts_min": int(g_sorted["_ts"].min()) if len(g_sorted) else 0,
            "ts_max": int(g_sorted["_ts"].max()) if len(g_sorted) else 0,
            "duplicates": dup_cnt,
            "price_inconsistencies": price_incons,
            "negative_volume_rows": neg_vol,
            "zero_values_total": zero_values_total,
            "zero_values_ratio": zero_values_ratio,
            "issues": ";".join(issue_list)
        })
        for it in issue_list:
            issues_rows.append({"instrument_id": inst, "issue": it})

    feature_stats = []
    for c in numeric_cols:
        ser = pd.to_numeric(df[c], errors="coerce")
        nn = ser.dropna()
        if nn.empty:
            continue
        feature_stats.append({
            "feature": c,
            "count": int(nn.count()),
            "mean": float(nn.mean()),
            "std": float(nn.std(ddof=0)) if nn.count() > 1 else 0.0,
            "min": float(nn.min()),
            "p25": float(nn.quantile(0.25)),
            "median": float(nn.median()),
            "p75": float(nn.quantile(0.75)),
            "max": float(nn.max()),
            "zeros": int((nn == 0).sum()),
            "zeros_ratio": float((nn == 0).mean()),
            "null_ratio": float(ser.isna().mean()),
        })

    global_zero_values = int((df[numeric_cols] == 0).sum().sum()) if numeric_cols else 0
    global_numeric_cells = int(len(df) * len([c for c in numeric_cols if c not in {"timestamp_nano", "_ts"}]))
    global_zero_ratio = float(global_zero_values / global_numeric_cells) if global_numeric_cells else 0.0

    return per_inst_rows, feature_stats, issues_rows, df, {
        "global_zero_values": global_zero_values,
        "global_zero_ratio": global_zero_ratio,
        "global_numeric_cells": global_numeric_cells,
    }

def build_correlations(df: pd.DataFrame):
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    drop_like = {"timestamp_nano","_ts"}
    num_cols = [c for c in num_cols if c not in drop_like]
    if not num_cols:
        return None
    if len(num_cols) > MAX_CORR_FEATURES:
        num_cols = num_cols[:MAX_CORR_FEATURES]
    return df[num_cols].corr(method="pearson")

def run():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    df = load_merged()
    ensure_columns(df)
    per_inst, feats, issues, df_aug, zero_meta = analyze_instruments(df)

    pd.DataFrame(per_inst).sort_values("instrument_id").to_csv(OUTPUT_ROOT / "instrument_overview.csv", index=False)
    pd.DataFrame(feats).sort_values("feature").to_csv(OUTPUT_ROOT / "feature_stats.csv", index=False)
    if issues:
        pd.DataFrame(issues).to_csv(OUTPUT_ROOT / "issues_log.csv", index=False)

    summary = {
        "instruments": len(per_inst),
        "rows_total": int(len(df)),
        "rows_median_per_instrument": float(pd.Series([r["rows"] for r in per_inst]).median()),
        "with_issues": int(sum(1 for r in per_inst if r["issues"])),
        "global_zero_values": zero_meta["global_zero_values"],
        "global_zero_ratio": zero_meta["global_zero_ratio"],
        "global_numeric_cells": zero_meta["global_numeric_cells"],
    }

    if DO_CORR:
        corr_df = build_correlations(df_aug)
        if corr_df is not None:
            corr_df.to_csv(OUTPUT_ROOT / "feature_correlations_sample.csv")
            summary["correlation_features"] = int(corr_df.shape[0])
        else:
            summary["correlation_features"] = 0

    with open(OUTPUT_ROOT / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("[OK] Analyse fertig")
    print(f"Instruments: {summary['instruments']}")
    print(f"Rows total: {summary['rows_total']}")
    print(f"Issues instruments: {summary['with_issues']}")
    print(f"Zero values (global): {summary['global_zero_values']} ({summary['global_zero_ratio']:.4f})")
    print(f"Output: {OUTPUT_ROOT}")

if __name__ == "__main__":
    run()
