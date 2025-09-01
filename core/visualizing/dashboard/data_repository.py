# core/visualizing/dashboard/data_repository.py
from pathlib import Path
import pandas as pd
from dataclasses import dataclass
from core.visualizing.dashboard.slide_menu import RunValidator

@dataclass
class DashboardData:
    collectors: dict          # {collector_name: {"bars_df": df, "bars_variants": {tf: df}, "trades_df": df, "indicators_df": {name: df}}}
    selected: str | None
    all_results_df: pd.DataFrame | None

class ResultsRepository:
    def __init__(self, results_root: Path):
        self.results_root = Path(results_root)
        self.run_validator = RunValidator(results_root)

    def _latest_run_dir(self) -> Path | None:
        runs = [p for p in self.results_root.iterdir() if p.is_dir() and p.name.startswith("run")]
        if not runs:
            return None
        # newest by mtime (or sort by run index if you prefer)
        return max(runs, key=lambda p: p.stat().st_mtime)

    def load_dashboard(self) -> DashboardData:
        run_dir = self._latest_run_dir()
        collectors = {}
        selected = None
        all_results_df = None

        if run_dir is None:
            print(f"[repo] No run folders found in {self.results_root}")
            # try to read all_backtest_results even if no runs yet
            abr = self.results_root / "all_backtest_results.csv"
            if abr.exists():
                try:
                    all_results_df = pd.read_csv(abr)
                except Exception as e:
                    print(f"[repo] Failed to read {abr}: {e}")
            return DashboardData(collectors, selected, all_results_df)

        print(f"[repo] Using run folder: {run_dir}")

        # load collectors: any subfolder except 'general'
        for sub in run_dir.iterdir():
            if not sub.is_dir():
                continue
            if sub.name.lower() == "general":
                continue
            cdata = self._load_collector(sub)
            if cdata:
                collectors[sub.name] = cdata
                print(f"[repo] Loaded collector: {sub.name}")

        if collectors:
            selected = next(iter(collectors.keys()))

        # all_backtest_results is one level above run_dir
        abr = run_dir.parent / "all_backtest_results.csv"
        if abr.exists():
            try:
                all_results_df = pd.read_csv(abr)
            except Exception as e:
                print(f"[repo] Failed to read {abr}: {e}")

        return DashboardData(collectors, selected, all_results_df)

    def load_validated_runs(self) -> pd.DataFrame:
        """Lädt und validiert alle Runs mit strikter Prüfung"""
        return self.run_validator.validate_and_load()
    
    def load_specific_run(self, run_identifier) -> DashboardData:
        """Lädt einen spezifischen Run.
        run_identifier:
          - str: wird als run_id interpretiert (Ordnername == run_id)
          - int: legacy -> erwartet Ordner 'run{index}'
        """
        # Neu: zuerst versuchen wir eine direkte run_id (str)
        run_dir = None
        run_id = None
        if isinstance(run_identifier, str):
            candidate = self.results_root / run_identifier
            if candidate.exists() and candidate.is_dir():
                run_dir = candidate
                run_id = run_identifier
        # Fallback: integer Index (altes Schema run0, run1, ...)
        if run_dir is None and isinstance(run_identifier, int):
            candidate = self.results_root / f"run{run_identifier}"
            if candidate.exists() and candidate.is_dir():
                run_dir = candidate
                run_id = candidate.name  # run0 ...
        if run_dir is None:
            raise FileNotFoundError(f"CRITICAL: Run directory not found for identifier: {run_identifier}")

        # Config validieren
        config_path = run_dir / "run_config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"CRITICAL: run_config.yaml not found in {run_dir}")

        collectors = {}
        selected = None

        # Collectors laden
        for sub in run_dir.iterdir():
            if not sub.is_dir() or sub.name.lower() == "general":
                continue
            cdata = self._load_collector(sub)
            if cdata:
                collectors[sub.name] = cdata

        if collectors:
            selected = next(iter(collectors.keys()))

        # all_backtest_results laden (global)
        all_results_df = None
        abr = self.results_root / "all_backtest_results.csv"
        if abr.exists():
            try:
                all_results_df = pd.read_csv(abr)
            except Exception as e:
                print(f"[repo] Failed to read {abr}: {e}")

        return DashboardData(collectors, selected, all_results_df)

    def _load_collector(self, folder: Path):
        import pandas as pd

        out = {"bars_df": None, "bars_variants": {}, "trades_df": None, "indicators_df": {}}

        # Bars (pick the shortest timeframe as primary)
        bars_list = []
        for f in folder.glob("bars-*.csv"):
            try:
                df = pd.read_csv(f)
                if not df.empty and "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns", errors="coerce")
                    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
                    tf = f.stem.replace("bars-", "")
                    df["timeframe"] = tf
                    bars_list.append(df)
                    out["bars_variants"][tf] = df
            except Exception as e:
                print(f"[repo] Bars error {f}: {e}")

        if bars_list:
            def tf_seconds(tf: str) -> int:
                import re
                m = re.match(r"(\d+)\s*([smhdSMHD])", tf)
                if not m:
                    return 10**9
                val = int(m.group(1))
                unit = m.group(2).lower()
                mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 10**6)
                return val * mult
            # Highest timeframe == max seconds
            largest = max(bars_list, key=lambda d: tf_seconds(d["timeframe"].iloc[0]))
            out["bars_df"] = largest

        # Trades
        tpath = folder / "trades.csv"
        if tpath.exists():
            try:
                tdf = pd.read_csv(tpath)
                if not tdf.empty and "timestamp" in tdf.columns:
                    for c in ["timestamp", "closed_timestamp"]:
                        if c in tdf.columns:
                            # try ns; fallback to normal parse if it fails
                            try:
                                tdf[c] = pd.to_datetime(tdf[c], unit="ns")
                            except Exception:
                                tdf[c] = pd.to_datetime(tdf[c], errors="coerce")
                    out["trades_df"] = tdf
            except Exception as e:
                print(f"[repo] Trades error {tpath}: {e}")

        # Indicators
        idir = folder / "indicators"
        if idir.exists():
            for ind_file in idir.glob("*.csv"):
                try:
                    idf = pd.read_csv(ind_file)
                    if not idf.empty and "timestamp" in idf.columns:
                        try:
                            idf["timestamp"] = pd.to_datetime(idf["timestamp"], unit="ns")
                        except Exception:
                            idf["timestamp"] = pd.to_datetime(idf["timestamp"], errors="coerce")
                        if "plot_id" not in idf.columns:
                            base = ind_file.stem.lower()
                            pid = 0
                            if any(k in base for k in ["equity", "position", "unrealized", "realized", "total_"]):
                                pid = 2
                            elif "rsi" in base:
                                pid = 1
                            idf["plot_id"] = pid
                        out["indicators_df"][ind_file.stem] = idf
                except Exception as e:
                    print(f"[repo] Indicator error {ind_file}: {e}")

        # Neu: Collector nur ausschließen, wenn GAR KEINE CSV (weder bars, trades.csv noch indicator CSVs) gefunden wurde.
        has_any_csv = bool(out["bars_variants"]) or (out["trades_df"] is not None) or bool(out["indicators_df"])
        if not has_any_csv:
            return None
        return out
