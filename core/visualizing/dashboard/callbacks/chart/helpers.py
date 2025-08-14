import pandas as pd

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
    """Parse Plotly relayoutData for manual x range or autorange reset."""
    if isinstance(relayoutData, dict):
        if 'xaxis.range[0]' in relayoutData and 'xaxis.range[1]' in relayoutData:
            return [relayoutData['xaxis.range[0]'], relayoutData['xaxis.range[1]']]
        if relayoutData.get('xaxis.autorange'):
            return None
    return None

def iter_indicator_groups(indicators):
    """Group indicator DataFrames by plot_id (>0)."""
    groups = {}
    for name, df in (indicators or {}).items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            pid = int(df.get("plot_id", [0])[0]) if "plot_id" in df.columns else 0
            if pid > 0:
                groups.setdefault(pid, []).append((name, df))
    return groups

def flatten_customdata(cd):
    """Flatten nested customdata ([[a,b,c]] -> [a,b,c])."""
    if isinstance(cd, (list, tuple)):
        if len(cd) == 1 and isinstance(cd[0], (list, tuple)):
            return flatten_customdata(cd[0])
        return list(cd)
    return [cd]
