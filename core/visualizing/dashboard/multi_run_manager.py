from __future__ import annotations
from typing import Dict, Tuple, List
import pandas as pd

# Simple color palette (fallback – charts may still override)
_PALETTE = [
    "#2563eb", "#16a34a", "#dc2626", "#7c3aed", "#ea580c",
    "#0891b2", "#4f46e5", "#059669", "#b45309", "#be123c",
    "#0d9488", "#9333ea", "#1d4ed8", "#15803d", "#b91c1c"
]

# Deutlich unterschiedliche Farbpaare (LONG, SHORT) pro Run
# Run 0 bleibt semantisch grün/rot; danach klare Farbharmonien für bessere Unterscheidbarkeit
_RUN_COLOR_PAIRS: list[tuple[str, str]] = [
    ("#10b981", "#ef4444"),  # Run 0  (Green / Red - Standard)
    ("#2563eb", "#f59e0b"),  # Run 1  (Blue / Amber)
    ("#9333ea", "#ea580c"),  # Run 2  (Purple / Orange)
    ("#0d9488", "#db2777"),  # Run 3  (Teal / Rose)
    ("#6366f1", "#b45309"),  # Run 4  (Indigo / Brown-Orange)
    ("#0891b2", "#b91c1c"),  # Run 5  (Cyan / Dark Red)
    ("#7c3aed", "#065f46"),  # Run 6  (Violet / Deep Teal)
    ("#1d4ed8", "#be123c"),  # Run 7  (Royal Blue / Crimson)
    ("#14b8a6", "#c2410c"),  # Run 8  (Aqua / Burnt Orange)
    ("#4f46e5", "#e11d48"),  # Run 9  (Indigo / Pink-Red)
]

def _hash_color(seed: str) -> tuple[str, str]:
    """Fallback: deterministisches zusätzliches Paar erzeugen (falls mehr Runs als Paare)."""
    import hashlib, colorsys
    h = hashlib.md5(seed.encode()).hexdigest()
    # Zwei unterschiedliche Hues erzeugen
    hue1 = (int(h[:6], 16) % 360) / 360.0
    hue2 = (int(h[6:12], 16) % 360) / 360.0
    def hue_to_rgb(hv):
        r, g, b = colorsys.hsv_to_rgb(hv, 0.55, 0.78)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    c1 = hue_to_rgb(hue1)
    c2 = hue_to_rgb(hue2)
    if c1 == c2:  # minimal sicherstellen, dass sie verschieden sind
        hue2 = (hue2 + 0.17) % 1.0
        c2 = hue_to_rgb(hue2)
    return c1, c2

def run_color_for_index(idx: int) -> Tuple[str, str, str]:
    """
    Returns (buy_color, short_color, neutral_color) for a run index.
      buy_color  -> LONG Marker Farbe (nicht immer Grün ab Run 1)
      short_color-> SHORT Marker Farbe (nicht immer Rot ab Run 1)
      neutral_color -> weiter für Linien / Indikatoren (bestehende Palette)
    """
    if idx < len(_RUN_COLOR_PAIRS):
        buy, short = _RUN_COLOR_PAIRS[idx]
    else:
        buy, short = _hash_color(f"run-{idx}")
    neutral = _PALETTE[idx % len(_PALETTE)]
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
