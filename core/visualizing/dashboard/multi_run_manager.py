from __future__ import annotations
from typing import Dict, Tuple, List
import pandas as pd

# Simple color palette (fallback – charts may still override)
_PALETTE = [
    "#2563eb", "#16a34a", "#dc2626", "#7c3aed", "#ea580c",
    "#0891b2", "#4f46e5", "#059669", "#b45309", "#be123c",
    "#0d9488", "#9333ea", "#1d4ed8", "#15803d", "#b91c1c"
]

def run_color_for_index(idx: int) -> Tuple[str, str, str]:
    """
    Returns (buy_color, short_color, neutral_color) for a run index.
    Neutral color used for lines / indicator tint if needed.
    """
    base = _PALETTE[idx % len(_PALETTE)]
    # Derive slight variants
    buy = base
    short = "#000000"  # consistent black for SHORT markers (aligned with new design)
    neutral = base
    return buy, short, neutral

def short_run_label(run_id) -> str:
    """Compact label for legend."""
    s = str(run_id)
    if len(s) <= 10:
        return s
    return f"{s[:4]}…{s[-4:]}"

def _select_timeframe_variant(collector: dict, timeframe: str | None):
    if not isinstance(collector, dict):
        return None
    if timeframe and timeframe != "__default__":
        bv = (collector.get("bars_variants") or {}).get(timeframe)
        if isinstance(bv, pd.DataFrame) and not bv.empty:
            return bv
    return collector.get("bars_df")

def gather_multi_run_data(runs_cache: Dict[str, object],
                          active_runs: List[str],
                          instrument: str,
                          timeframe: str | None = None):
    """
    Collects per-run data for a single instrument across multiple runs.

    Returns:
        bars_df: A reference bars DataFrame (first non-empty found)
        indicators_per_run: {run_id: {indicator_name: df}}
        trades_per_run: {run_id: trades_df}
    """
    bars_df = None
    indicators_per_run = {}
    trades_per_run = {}

    for rid in active_runs:
        run_obj = runs_cache.get(rid)
        if not run_obj:
            continue
        collectors = getattr(run_obj, "collectors", {}) or {}
        coll = collectors.get(instrument)
        if not coll:
            continue

        # Bars
        bdf = _select_timeframe_variant(coll, timeframe)
        if bars_df is None and isinstance(bdf, pd.DataFrame) and not bdf.empty:
            bars_df = bdf

        # Trades
        tdf = coll.get("trades_df")
        if isinstance(tdf, pd.DataFrame) and not tdf.empty:
            trades_per_run[rid] = tdf

        # Indicators
        idict = coll.get("indicators_df") or {}
        if isinstance(idict, dict) and idict:
            indicators_per_run[rid] = idict

    if bars_df is None:
        bars_df = pd.DataFrame()  # keep type stability
    return bars_df, indicators_per_run, trades_per_run
