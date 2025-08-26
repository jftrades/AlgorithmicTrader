from typing import List, Dict, Tuple
import pandas as pd

# Farbschemata pro Run (BUY, SHORT, INDICATOR_GRADIENT_BASE)
RUN_COLOR_SETS = [
    ("#1E88E5", "#E53935", "#37474F"),  # Blue / Red
    ("#8E24AA", "#FB8C00", "#5E548E"),  # Purple / Orange
    ("#00897B", "#D81B60", "#00695C"),  # Teal / Pink
    ("#5E35B1", "#F4511E", "#3949AB"),  # Deep Purple / Deep Orange
    ("#3949AB", "#FDD835", "#1B5E20"),  # Indigo / Amber
    ("#00796B", "#C62828", "#2E7D32"),  # Green set
    ("#6D4C41", "#FF7043", "#4E342E"),  # Brown / Coral
]

def short_run_label(run_id: str) -> str:
    if not run_id:
        return "run"
    return run_id[:6] if len(run_id) > 10 else run_id

def gather_multi_run_data(runs_cache: Dict[str, object],
                          run_ids: List[str],
                          collector: str,
                          timeframe: str | None = None):
    """
    Returns (bars_df, indicators_per_run, trades_per_run)
    bars_df: reference bars (first run that has data for collector + timeframe)
    indicators_per_run: { run_id: { name: df } }
    trades_per_run: { run_id: df }
    """
    indicators_per_run: Dict[str, Dict[str, pd.DataFrame]] = {}
    trades_per_run: Dict[str, pd.DataFrame] = {}
    bars_df = None

    for rid in run_ids:
        rd = runs_cache.get(rid)
        if not rd:
            continue
        collectors_map = getattr(rd, "collectors", {}) or {}
        coll = collectors_map.get(collector)
        if not isinstance(coll, dict):
            continue

        # timeframe selection
        candidate = None
        if timeframe and timeframe != "__default__":
            candidate = (coll.get("bars_variants") or {}).get(timeframe)
        if candidate is None:
            candidate = coll.get("bars_df")

        if bars_df is None and isinstance(candidate, pd.DataFrame) and not candidate.empty:
            bars_df = candidate

        # trades
        tdf = coll.get("trades_df")
        if isinstance(tdf, pd.DataFrame) and "timestamp" in tdf.columns:
            trades_per_run[rid] = tdf

        # indicators
        ind_map = coll.get("indicators_df") or {}
        im_out = {}
        if isinstance(ind_map, dict):
            for name, df in ind_map.items():
                if isinstance(df, pd.DataFrame) and "timestamp" in df.columns and not df.empty:
                    im_out[name] = df
        if im_out:
            indicators_per_run[rid] = im_out

    return bars_df, indicators_per_run, trades_per_run

def run_color_for_index(i: int) -> Tuple[str, str, str]:
    return RUN_COLOR_SETS[i % len(RUN_COLOR_SETS)]
