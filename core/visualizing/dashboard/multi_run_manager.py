from typing import List, Dict, Tuple
import pandas as pd

# Farbschemata pro Run (BUY, SHORT, INDICATOR_GRADIENT_BASE)
RUN_COLOR_SETS = [
    ("#28a745", "#dc3545", "#000000"),  # Run 1 (bestehendes Schema)
    ("#7e3ff2", "#8b4513", "#55309d"),  # Run 2 (Purple / Brown)
    ("#0b3d91", "#ff8800", "#0b3d91"),  # Run 3 (Blue / Orange)
    ("#1f5e3d", "#7a0c2e", "#1f5e3d"),  # Run 4 (Green / Crimson)
    ("#5a3d73", "#6d5600", "#5a3d73"),  # Run 5 (Violet / Golden)
]

def short_run_label(run_id: str) -> str:
    """Kompakte Label-Darstellung."""
    if not run_id:
        return "run"
    # z.B. nur ersten 6 Zeichen (UUID/Hash) oder vollständige ID wenn kurz
    return run_id[:6] if len(run_id) > 10 else run_id

def gather_multi_run_data(runs_cache: Dict[str, object],
                          run_ids: List[str],
                          collector: str):
    """
    Liefert:
      bars_df (vom ersten Run mit Daten),
      indicators_per_run: Dict[run_id -> Dict[ind_name -> df]]
      trades_per_run: Dict[run_id -> trades_df]
    """
    def _get(coll, name):
        if coll is None:
            return None
        if isinstance(coll, dict):
            return coll.get(name)
        return getattr(coll, name, None)

    indicators_per_run = {}
    trades_per_run = {}
    bars_df = None

    for ridx, rid in enumerate(run_ids):
        rd = runs_cache.get(rid)
        if not rd:
            continue
        collectors_map = getattr(rd, "collectors", {}) or {}
        coll = collectors_map.get(collector)
        if not coll:
            continue

        # Bars nur einmal setzen (kein bool check auf DataFrame!)
        if bars_df is None:
            candidate = _get(coll, "bars_df")
            if isinstance(candidate, pd.DataFrame) and not candidate.empty:
                bars_df = candidate

        # Trades sicher holen
        t_candidate = _get(coll, "trades_df")
        trades_df = t_candidate if isinstance(t_candidate, pd.DataFrame) else None

        # Indicators (Mapping) holen
        ind_map = _get(coll, "indicators_df")
        if not ind_map:
            ind_map = _get(coll, "indicators")
        if not isinstance(ind_map, dict):
            ind_map = {}

        indicators_per_run[rid] = ind_map
        trades_per_run[rid] = trades_df

    return bars_df, indicators_per_run, trades_per_run

def run_color_for_index(i: int) -> Tuple[str, str, str]:
    """Farben (BUY, SHORT, Indicator-Basis) für Run-Index i."""
    return RUN_COLOR_SETS[i % len(RUN_COLOR_SETS)]
