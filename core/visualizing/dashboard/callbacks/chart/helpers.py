import pandas as pd

def _to_dt(x):
    try:
        return pd.to_datetime(x)
    except Exception:
        return None

def extract_collector_data(coll):
    """Return (bars_df, trades_df, indicators_map) for collector object or dict."""
    if coll is None:
        return None, None, {}
    if isinstance(coll, dict):
        return (
            coll.get("bars_df"),
            coll.get("trades_df"),
            coll.get("indicators_df", {}) or coll.get("indicators", {})
        )
    return (
        getattr(coll, "bars_df", None),
        getattr(coll, "trades_df", None),
        getattr(coll, "indicators_df", {}) or getattr(coll, "indicators", {})
    )

def compute_x_range(relayoutData):
    """
    Extrahiert [start, end] aus Plotly relayoutData für die X-Achse.
    Unterstützt folgende Formen:
      {'xaxis.range[0]': '2024-01-01 ...', 'xaxis.range[1]': '...'}
      {'xaxis.range': ['2024-01-01 ...','...']}
      {'xaxis.autorange': True} -> None
    """
    if not relayoutData or not isinstance(relayoutData, dict):
        return None
    # Autorange reset
    if relayoutData.get("xaxis.autorange"):
        return None

    r0 = relayoutData.get("xaxis.range[0]")
    r1 = relayoutData.get("xaxis.range[1]")
    if r0 and r1:
        d0, d1 = _to_dt(r0), _to_dt(r1)
        if d0 is not None and d1 is not None and d0 < d1:
            return [d0, d1]

    rlist = relayoutData.get("xaxis.range")
    if isinstance(rlist, (list, tuple)) and len(rlist) == 2:
        d0, d1 = _to_dt(rlist[0]), _to_dt(rlist[1])
        if d0 is not None and d1 is not None and d0 < d1:
            return [d0, d1]

    # Sometimes Plotly returns axis names like 'xaxis2.range[0]' when secondary axes manipulated – ignore for sync.
    return None

def iter_indicator_groups(indicators_dict):
    """Group indicator DataFrames by plot_id (>0)."""
    groups = {}
    if not isinstance(indicators_dict, dict):
        return groups
    for name, df in indicators_dict.items():
        try:
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            if "plot_id" in df.columns and len(df["plot_id"]) > 0:
                try:
                    pid = int(df["plot_id"].iloc[0])  # fixed: positional access
                except Exception:
                    pid = 0
            else:
                pid = 0
            groups.setdefault(pid, []).append((name, df))
        except Exception:
            continue
    return groups

def flatten_customdata(cd):
    """Flatten nested customdata ([[a,b,c]] -> [a,b,c])."""
    if isinstance(cd, (list, tuple)):
        if len(cd) == 1 and isinstance(cd[0], (list, tuple)):
            return flatten_customdata(cd[0])
        return list(cd)
    return [cd]
