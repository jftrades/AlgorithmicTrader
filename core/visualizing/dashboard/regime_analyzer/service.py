from __future__ import annotations

"""
service.py — Regime analysis logic for NautilusTrader visualizer

Features:
- Auto-load `total_*.csv` (equity) and all other `*.csv` indicators in current dir
- Safe timestamp parsing (ns → datetime), resampling & forward-fill with stale-drop
- Outcome labeling via forward return over horizon H
- Two analysis modes: quantile BINS and CONTINUOUS (smoothed rolling median)
- Bivariate heatmap (feature × feature) with performance & support
- Plotly figures ready for Dash

CSV schema (expected):
- Equity: columns [timestamp, value, plot_id] — only timestamp & value used
- Indicators: columns [timestamp, value, plot_id] — one file per indicator

Notes:
- No look-ahead: indicators are aligned using past values only (ffill)
- Robust stats option uses median & MAD-like scaling; otherwise mean & std
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# ---------------------------
# Helpers
# ---------------------------

def _to_dt(series: pd.Series) -> pd.Series:
    """Convert integer timestamps (ns, µs, ms, s) or ISO strings to pandas datetime (UTC naive).
    Robust: find first non-null value, try numeric coercion, fall back to string parse.
    """
    s = series
    # find first non-null sample
    first = None
    try:
        first = s.dropna().iloc[0]
    except Exception:
        first = None

    # if first looks numeric (or numeric-like string), coerce and use magnitude heuristic
    try:
        if first is not None:
            num = pd.to_numeric(first, errors="coerce")
            if not pd.isna(num):
                x = float(num)
                if x > 1e18:  # ps (unlikely)
                    dt = pd.to_datetime(s, unit="ps", errors="coerce")
                elif x > 1e15:  # ns
                    dt = pd.to_datetime(s, unit="ns", errors="coerce")
                elif x > 1e12:  # µs
                    dt = pd.to_datetime(s, unit="us", errors="coerce")
                elif x > 1e9:   # ms
                    dt = pd.to_datetime(s, unit="ms", errors="coerce")
                else:           # s
                    dt = pd.to_datetime(s, unit="s", errors="coerce")
                # fill any not-parsed with string parsing fallback
                if dt.isna().any():
                    dt_str = pd.to_datetime(s, utc=False, errors="coerce")
                    dt = dt.combine_first(dt_str)
                return dt.tz_localize(None)
    except Exception:
        pass

    # fallback: try direct datetime parse (strings)
    try:
        dt = pd.to_datetime(s, utc=False, errors="coerce")
        # if still all NaT, try strip and retry
        if dt.isna().all():
            dt = pd.to_datetime(s.astype(str).str.strip(), utc=False, errors="coerce")
        return dt.tz_localize(None)
    except Exception:
        # last resort: convert each element individually
        out = []
        for v in s:
            try:
                out.append(pd.to_datetime(v, utc=False))
            except Exception:
                out.append(pd.NaT)
        return pd.DatetimeIndex(out).tz_localize(None)


def _sanitize_name(p: Path) -> str:
    name = p.stem
    # drop common prefixes if any, keep concise
    return name.strip().replace(" ", "_").replace("-", "_")


def _mad(x: np.ndarray) -> float:
    med = np.median(x)
    return float(np.median(np.abs(x - med)))


def _rolling_smooth(x: np.ndarray, y: np.ndarray, points: int = 200) -> Tuple[np.ndarray, np.ndarray]:
    """Simple monotone-agnostic smoothing: sort by x, compute rolling median over ~N/50 window.
    Returns grid_x, smooth_y for plotting a continuous curve without external deps.
    """
    if len(x) < 10:
        return x, y
    order = np.argsort(x)
    xs, ys = x[order], y[order]
    n = len(xs)
    win = max(5, n // 50)
    # grid points across feature range
    grid_idx = np.linspace(0, n - 1, num=min(points, n)).astype(int)
    gx, gy = [], []
    for i in grid_idx:
        a = max(0, i - win // 2)
        b = min(n, i + win // 2 + 1)
        gx.append(xs[i])
        gy.append(float(np.median(ys[a:b])))
    return np.array(gx), np.array(gy)


# ---------------------------
# Core service
# ---------------------------

@dataclass
class RegimeConfig:
    dt: str = "5min"
    horizon: str = "1h"
    n_bins: int = 8
    max_ffill: Optional[int] = None  # number of steps to allow forward-fill; None = unlimited


class RegimeService:
    def __init__(self, base_dir: Path, config: Optional[RegimeConfig] = None):
        self.base_dir = Path(base_dir)
        self.config = config or RegimeConfig()
        # last diagnostics populated by get_dataset
        self._last_diag: Dict[str, object] = {}

    # ---------------
    # Public API
    # ---------------
    def clear_cache(self):
        self.get_dataset.cache_clear()  # type: ignore
        self.get_feature_names.cache_clear()  # type: ignore

    def get_last_diagnostics(self) -> Dict[str, object]:
        """Return last collected diagnostics from get_dataset (may be empty)."""
        return dict(self._last_diag)

    @lru_cache(maxsize=1)
    def get_feature_names(self, silent: bool = False) -> List[str]:
        _, ind_map, summary_files = self._discover_files()
        # Filter out any keys that look like summary/aggregate files (defensive)
        filtered = {k: v for k, v in ind_map.items() if not ("all_backtest_results" in k.lower() or "summary" in k.lower())}
        if not silent:
            try:
                print(f"[RegimeService.get_feature_names] indicators={list(filtered.keys())}, summary_files={summary_files}")
            except Exception:
                pass
        return sorted(list(filtered.keys()))

    @lru_cache(maxsize=8)
    def get_dataset(self, dt: Optional[str] = None, horizon: Optional[str] = None, drop_stale: bool = True) -> Optional[pd.DataFrame]:
        dt = dt or self.config.dt
        horizon = horizon or self.config.horizon

        # Load equity first and print diagnostics
        eq = self._load_equity()
        if eq is None or eq.empty:
            self._last_diag = {
                "base_dir": str(self.base_dir),
                "equity_found": False,
                "indicators_found": [],
                "note": "No equity file found under base_dir"
            }
            try:
                print(f"[RegimeService.get_dataset] NO EQUITY in {self.base_dir}")
            except Exception:
                pass
            return None

        try:
            print(f"[RegimeService.get_dataset] equity index dtype: {eq.index.dtype}, rows={len(eq)}, idx_min={eq.index.min()}, idx_max={eq.index.max()}")
        except Exception:
            pass

        eq = self._resample(eq, dt)
        indicators = self._load_indicators()
        ind_names = list(indicators.keys()) if indicators else []

        # Print indicators raw ranges before resample
        try:
            info = {}
            for name, s in indicators.items():
                try:
                    info[name] = {"rows": len(s), "min": str(s.index.min()), "max": str(s.index.max())}
                except Exception:
                    info[name] = {"rows": len(s)}
            print(f"[RegimeService.get_dataset] indicators discovered (pre-resample): {info}")
        except Exception:
            pass

        if indicators:
            for name, ser in indicators.items():
                ser_r = self._resample(ser.to_frame(name), dt, max_ffill=self.config.max_ffill)
                eq = eq.join(ser_r, how="left")

        # After join, report overlapping counts
        try:
            cols = list(eq.columns)
            counts = {c: int(eq[c].notna().sum()) for c in cols}
            idx_dtype = getattr(eq.index, "dtype", str(type(eq.index)))
            print(f"[RegimeService.get_dataset] after join index dtype: {idx_dtype}, columns={cols}, non_na_counts={counts}")
            # compute overlap between equity and any indicator (rows with any indicator present)
            indicator_cols = [c for c in cols if c not in ("equity", "fwd_return", "ret", "drawdown")]
            if indicator_cols:
                any_ind = int(eq[indicator_cols].notna().any(axis=1).sum())
                both = int(eq[[c for c in indicator_cols if c in eq.columns] + ["fwd_return"]].dropna().shape[0]) if "fwd_return" in cols else 0
                print(f"[RegimeService.get_dataset] rows_with_any_indicator={any_ind}, rows_with_indicator_and_fwd_return={both}")
        except Exception:
            pass

        # Outcome label: forward return over horizon
        fwd = self._forward_return(eq["equity"], dt, horizon)
        eq["fwd_return"] = fwd

        # Diagnostics and simple stats (populate before returning)
        try:
            eq_range = (None, None)
            if not eq.empty:
                eq_range = (str(eq.index.min()), str(eq.index.max()))
            counts = {}
            for name in ind_names:
                try:
                    counts[name] = int(eq[name].notna().sum())
                except Exception:
                    counts[name] = 0
            self._last_diag = {
                "base_dir": str(self.base_dir),
                "equity_found": True,
                "equity_range": eq_range,
                "indicators_found": ind_names,
                "indicator_non_na_counts": counts,
                "fwd_return_non_na": int(eq["fwd_return"].notna().sum())
            }
            try:
                print(f"[RegimeService.get_dataset] diagnostics: {self._last_diag}")
            except Exception:
                pass
        except Exception:
            self._last_diag = {"base_dir": str(self.base_dir)}

        # Diagnostics columns
        try:
            eq["drawdown"] = self._drawdown(eq["equity"]).values
            eq["ret"] = eq["equity"].pct_change().fillna(0.0)
        except Exception:
            # ensure we still return something minimal
            pass

        # Extra debug: print small sample of joined frame (head)
        try:
            print("[RegimeService.get_dataset] joined sample:\n" + eq.head(8).to_string())
        except Exception:
            pass

        return eq

    def _load_equity(self) -> Optional[pd.DataFrame]:
        eq_file, _, _ = self._discover_files()
        if eq_file is None:
            try:
                print(f"[RegimeService._load_equity] no equity CSV found in {self.base_dir!s}")
            except Exception:
                pass
            return None
        try:
            df = pd.read_csv(eq_file)
        except Exception as e:
            print(f"[RegimeService._load_equity] failed to read {eq_file}: {e}")
            return None
        if "timestamp" not in df.columns or "value" not in df.columns:
            raise ValueError(f"Equity CSV {eq_file} missing required columns 'timestamp' and 'value'")
        # Debug: print first raw timestamp values
        try:
            sample_ts = df["timestamp"].head(5).tolist()
            print(f"[RegimeService._load_equity] raw timestamps sample ({eq_file.name}): {sample_ts}")
        except Exception:
            pass
        dt = _to_dt(df["timestamp"])
        try:
            print(f"[RegimeService._load_equity] parsed timestamp dtype: {dt.dtype}, na_count={int(dt.isna().sum())}")
        except Exception:
            pass
        out = pd.DataFrame({"equity": df["value"].astype(float).values}, index=dt)
        out = out[~out.index.duplicated(keep="last")].sort_index()
        try:
            print(f"[RegimeService._load_equity] loaded {eq_file.name}, rows={len(out)}, index_range={out.index.min()} -> {out.index.max()}")
        except Exception:
            pass
        return out

    def _load_indicators(self) -> Dict[str, pd.Series]:
        _, ind_map, _ = self._discover_files()
        series: Dict[str, pd.Series] = {}
        for name, p in ind_map.items():
            try:
                df = pd.read_csv(p)
            except Exception:
                print(f"[RegimeService._load_indicators] failed to read {p}")
                continue
            if "timestamp" not in df.columns or "value" not in df.columns:
                print(f"[RegimeService._load_indicators] skipping {p.name}: missing columns")
                continue
            # debug raw ts sample
            try:
                raw_sample = df["timestamp"].head(3).tolist()
                print(f"[RegimeService._load_indicators] {p.name} raw ts sample: {raw_sample}")
            except Exception:
                pass
            dt = _to_dt(df["timestamp"])
            try:
                print(f"[RegimeService._load_indicators] {p.name} parsed ts dtype: {dt.dtype}, na_count={int(dt.isna().sum())}")
            except Exception:
                pass
            try:
                s = pd.Series(df["value"].astype(float).values, index=dt, name=name)
                s = s[~s.index.duplicated(keep="last")].sort_index()
                series[name] = s
                try:
                    print(f"[RegimeService._load_indicators] loaded {p.name}, rows={len(s)}, idx_min={s.index.min()}, idx_max={s.index.max()}, non_na={int(s.notna().sum())}")
                except Exception:
                    pass
            except Exception as e:
                print(f"[RegimeService._load_indicators] failed to parse {p.name}: {e}")
                continue
        return series

    def _resample(self, df: pd.DataFrame, dt: str, max_ffill: Optional[int] = None) -> pd.DataFrame:
        # Resample to dt and forward fill; limit to max_ffill if provided
        r = df.resample(dt).last()
        if max_ffill is None:
            return r.ffill()
        return r.ffill(limit=max_ffill)

    def _forward_return(self, equity: pd.Series, dt: str, horizon: str) -> pd.Series:
        # number of periods to shift
        try:
            n = int(pd.Timedelta(horizon) / pd.Timedelta(dt))
        except Exception:
            n = 1
        if n <= 0:
            n = 1
        fwd = equity.shift(-n) / equity - 1.0
        return fwd

    @staticmethod
    def _drawdown(equity: pd.Series) -> pd.Series:
        roll_max = equity.cummax()
        dd = equity / roll_max - 1.0
        return dd.fillna(0.0)

    def _discover_files(self) -> Tuple[Optional[Path], Dict[str, Path], List[str]]:
        """
        Discover CSV files under self.base_dir.
        Returns: (equity_file_or_None, indicators_map{name->Path}, summary_file_names)
        """
        eq_file: Optional[Path] = None
        ind_map: Dict[str, Path] = {}
        summary_files: List[str] = []

        try:
            base = Path(self.base_dir)
            if not base.exists() or not base.is_dir():
                return None, {}, []
            for p in sorted(base.glob("*.csv")):
                name_l = p.name.lower()
                # equity heuristics: total_equity / total_* containing 'equity'
                if ("equity" in name_l and (name_l.startswith("total") or "total_equity" in name_l)) or name_l.startswith("total_"):
                    if eq_file is None:
                        eq_file = p
                    continue
                # treat known summary/aggregate files separately
                if "all_backtest_results" in name_l or name_l.startswith("all_backtest") or "summary" in name_l:
                    summary_files.append(p.name)
                    continue
                # otherwise treat as indicator CSV
                ind_map[_sanitize_name(p)] = p
        except Exception:
            # defensive: return empties on any failure
            return None, {}, []

        try:
            print(f"[RegimeService._discover_files] base_dir={self.base_dir!s}, eq_file={eq_file!s}, indicators={[p.name for p in ind_map.values()]}, summaries={summary_files}")
        except Exception:
            pass
        return eq_file, ind_map, summary_files
