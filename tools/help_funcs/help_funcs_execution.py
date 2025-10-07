# Standard Library Importe
import sys
import time
import pandas as pd
import re
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import quantstats as qs
import webbrowser, os
import glob
import json
from pathlib import Path
import shutil
import importlib
from typing import Any, Dict, List

# Nautilus Kern Importe
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.config import BacktestDataConfig
from core.visualizing.dashboard1 import TradingDashboard

def run_backtest(run_config):
    node = BacktestNode(run_config)  # Übergib eine Liste!
    result = node.run()
    return result

def setup_visualizer():
    VIS_PATH = Path(__file__).resolve().parent.parent / "data" / "visualizing"
    
    if str(VIS_PATH) not in sys.path:
        sys.path.insert(0, str(VIS_PATH))
    
    return TradingDashboard

def visualize_existing_run(data_path, TradingDashboard=None):
    if TradingDashboard is None:
        TradingDashboard = setup_visualizer()
    visualizer = TradingDashboard(data_path=data_path)
    visualizer.load_data_from_csv()
    # NEU: Lade performance_metrics.csv, falls vorhanden
    perf_path = Path(data_path) / "performance_metrics.csv"
    if perf_path.exists():
        try:
            perf_df = pd.read_csv(perf_path)
            if not perf_df.empty:
                metrics = perf_df.iloc[0].to_dict()
                visualizer.metrics = metrics
                print("Performance-Metriken aus performance_metrics.csv geladen.")
        except Exception as e:
            print(f"Fehler beim Laden von performance_metrics.csv: {e}")
    print("Starte Dashboard für bestehenden Run...")
    visualizer.visualize(visualize_after_backtest=True)

def extract_metrics(result, run_params, run_id):
    metrics = {}
    result_obj = result[0] if isinstance(result, list) and len(result) > 0 else result

    metrics.update(run_params)
    metrics["run_id"] = run_id
    metrics["run_started"] = getattr(result_obj, "run_started", None)
    metrics["run_finished"] = getattr(result_obj, "run_finished", None)
    metrics["backtest_start"] = getattr(result_obj, "backtest_start", None)
    metrics["backtest_end"] = getattr(result_obj, "backtest_end", None)
    metrics["elapsed_time"] = getattr(result_obj, "elapsed_time", None)
    metrics["total_orders"] = getattr(result_obj, "total_orders", None)
    metrics["total_positions"] = getattr(result_obj, "total_positions", None)

    def _zero_if_null(x):
        # Covers: None, float NaN, numpy NaN, string "nan"/"NaN"
        if x is None:
            return 0
        try:
            if pd.isna(x):
                return 0
        except Exception:
            pass
        if isinstance(x, str) and x.strip().lower() == "nan":
            return 0
        return x

    if hasattr(result_obj, "stats_pnls"):
        for currency in ["USD", "USDT"]:
            if currency in result_obj.stats_pnls:
                for k, v in result_obj.stats_pnls[currency].items():
                    metrics[f"USDT_{k}"] = _zero_if_null(v)
                break

    if hasattr(result_obj, "stats_returns"):
        for k, v in result_obj.stats_returns.items():
            metrics[k] = _zero_if_null(v)

    max_dd = calculate_max_drawdown(run_id)
    metrics["Max Drawdown"] = max_dd

    return metrics

def calculate_max_drawdown(run_id):
    """
    Berechnet den maximalen Drawdown (als positiver Anteil 0..1) aus der total_equity.csv
    für den angegebenen run_id. Liefert 0.0 falls Datei fehlt oder keine validen Daten.
    """
    try:
        root_dir = Path(__file__).resolve().parents[2]  # .../AlgorithmicTrader
        equity_csv = (
            root_dir
            / "data"
            / "DATA_STORAGE"
            / "results"
            / str(run_id)
            / "general"
            / "indicators"
            / "total_equity.csv"
        )
        if not equity_csv.exists():
            return 0.0
        df = pd.read_csv(equity_csv, usecols=["timestamp", "value"])
        if df.empty or "value" not in df.columns:
            return 0.0
        # Bereinigung
        df = df.dropna(subset=["value"])
        if df.empty:
            return 0.0
        # Nach Zeit sortieren (falls nötig)
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp")
        equity = pd.to_numeric(df["value"], errors="coerce").dropna()
        if equity.empty:
            return 0.0
        # Laufendes Hoch
        running_peak = equity.cummax()
        # Vermeide Division durch 0 (FutureWarning Fix: statt fillna(method="ffill") -> ffill())
        running_peak = running_peak.replace(0, pd.NA).ffill()
        if running_peak.isna().all():
            return 0.0
        drawdowns = (running_peak - equity) / running_peak
        max_dd = drawdowns.max()
        if pd.isna(max_dd) or max_dd < 0:
            return 0.0
        return float(round(max_dd, 6))
    except Exception:
        return 0.0

def run_backtest_and_visualize(run_config, data_path=None, TradingDashboard=None):
    # Backtest ausführenp
    try:
        node = BacktestNode(configs=[run_config])
        print("Starte Backtest...")
        results = node.run()
    except Exception as e:
        print(f"FEHLER: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Ergebnisse anzeigen
    if results:
        result = results[0]
        print("=" * 50)
        print(f"Backtest: {result.backtest_start} bis {result.backtest_end}")
        print(f"Orders: {result.total_orders} | Positionen: {result.total_positions}")
        
        # Performance
        for currency, metrics in result.stats_pnls.items():
            pnl = metrics.get('PnL', 0)
            print(f"{currency} PnL: {pnl:.2f}")
        
        # Trade Reports
        engine = node.get_engine(run_config.id)
        trader = engine.trader
        fills_report = trader.generate_order_fills_report()
        
        if not fills_report.empty:
            print(f"Trades: {len(fills_report)}")
        else:
            print("Keine Trades!")
        print("=" * 50)
    else:
        print("Keine Ergebnisse.")
        return None

    time.sleep(1)

    # VISUALIZER
    if TradingDashboard is None:
        TradingDashboard = setup_visualizer()
    
    visualizer = TradingDashboard(data_path=data_path) if data_path else TradingDashboard()
    visualizer.collect_results(results)
    visualizer.load_data_from_csv()

    if visualizer.bars_df is not None:
        print(f"  - Bars geladen: {len(visualizer.bars_df)} Einträge")
    else:
        print("  - Keine Bars gefunden!")

    if visualizer.trades_df is not None:
        print(f"  - Trades geladen: {len(visualizer.trades_df)} Einträge")
    else:
        print("  - Keine Trades gefunden!")

    print(f"  - Indikatoren geladen: {len(visualizer.indicators_df)} Indikatoren")
    print(f"  - Metriken geladen: {len(visualizer.metrics) if visualizer.metrics else 0} Metriken")
    print("Starte Dashboard...")
    visualizer.visualize(visualize_after_backtest=True)

    return results

def export_equity_curve(run_dir):
    equity_path = run_dir / "indicators" / "equity.csv"
    try:
        balance_df = pd.read_csv(run_dir / "indicators" / "balance.csv", usecols=["timestamp", "value"])
        unrealized_df = pd.read_csv(run_dir / "indicators" / "unrealized_pnl.csv", usecols=["timestamp", "value"])
        merged = pd.merge(balance_df, unrealized_df, on="timestamp", suffixes=("_balance", "_unrealized"), how="outer").fillna(0)
        merged["equity"] = merged["value_balance"].astype(float) + merged["value_unrealized"].astype(float)
        # Fix: Spalte für QuantStats heißt "value"
        merged_out = merged[["timestamp", "equity"]].rename(columns={"equity": "value"})
        merged_out.to_csv(equity_path, index=False)
        print(f"Echte Equity-Kurve exportiert: {equity_path}")
    except Exception as e:
        print(f"Equity-Export fehlgeschlagen: {e}")

def show_quantstats_report_from_equity_csv(
    equity_csv,
    benchmark_symbol=None,
    output_path=None
):
    # Equity-Kurve laden, Duplikate entfernen, Zeitstempel als Index
    equity_df = pd.read_csv(equity_csv, usecols=["timestamp", "value"])
    equity = pd.Series(equity_df["value"].values, index=pd.to_datetime(equity_df["timestamp"], unit="ns"))
    equity = equity[~equity.index.duplicated(keep='first')]
    # Fix: Resample auf Tagesbasis, damit QuantStats mit Yahoo-Finance-Benchmark funktioniert
    equity_daily = equity.resample("1D").last().dropna()
    returns = equity_daily.pct_change(fill_method=None).dropna()

    # Benchmark von Yahoo Finance laden und Duplikate entfernen
    benchmark = None
    if benchmark_symbol:
        benchmark = qs.utils.download_returns(benchmark_symbol)
        # Benchmark ebenfalls auf die gleichen Tage beschränken
        benchmark = benchmark[equity_daily.index.min():equity_daily.index.max()]

    # Suppress noisy zero-variance KDE warning from quantstats/seaborn

    qs.reports.html(returns, benchmark=benchmark, output=str(output_path) if output_path else None)

def _clear_directory(path: Path):
    """Löscht sämtliche Inhalte eines Verzeichnisses ohne das Verzeichnis selbst zu entfernen."""
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except Exception:
                pass


def load_qs(run_dirs, run_ids, benchmark_symbol=None, open_browser=False):
    """
    Generate QuantStats reports for all runs using existing total_equity.csv files:
      results/<run_id>/general/indicators/total_equity.csv
    Produces quantstats_report.html inside each run directory.
    Set open_browser=True to open reports automatically (default system browser).
    """
    print("Generating QuantStats reports...")
    def _open_html(path_obj):
        if not open_browser:
            return
        try:
            import webbrowser
            webbrowser.open_new_tab(path_obj.as_uri())
        except Exception as e:
            print(f"[QuantStats] Auto-open failed: {e}")
    for run_dir, run_id in zip(run_dirs, run_ids):
        try:
            equity_csv = run_dir / "general" / "indicators" / "total_equity.csv"
            if not equity_csv.exists():
                print(f"[QuantStats] total_equity.csv missing for {run_id} -> skipped")
                continue
            out_file = run_dir / "quantstats_report.html"
            show_quantstats_report_from_equity_csv(
                equity_csv,
                benchmark_symbol=benchmark_symbol,
                output_path=out_file
            )
            print(f"[QuantStats] Report written: {out_file}")
            _open_html(out_file)
        except Exception as e:
            print(f"[QuantStats] Failed for {run_id}: {e}")

def compute_missing_trade_metrics(run_ids, results_dir: Path, instrument_ids):
    """
    Create trade_metrics.csv for each run/instrument if it does not exist,
    derived purely from trades.csv.
    """
    import pandas as _pd
    import re

    def _parse_number(val):
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val)
        m = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', s)
        return float(m.group(0)) if m else 0.0

    def _max_streak(mask_iterable):
        mx = cur = 0
        for v in mask_iterable:
            if v:
                cur += 1
                mx = cur if cur > mx else mx
            else:
                cur = 0
        return mx

    def _compute_metrics(df_tr: _pd.DataFrame) -> dict:
        if df_tr.empty:
            return {}
        for col in ["realized_pnl", "fee", "tradesize"]:
            if col in df_tr.columns:
                df_tr[col] = df_tr[col].apply(_parse_number)
            else:
                df_tr[col] = 0.0
        if "action" in df_tr.columns:
            act = df_tr["action"].astype(str).str.upper()
            is_long = act.eq("BUY")
            is_short = act.eq("SHORT")
        else:
            is_long = df_tr["tradesize"] > 0
            is_short = df_tr["tradesize"] < 0
        sort_col = "closed_timestamp" if "closed_timestamp" in df_tr.columns else "timestamp"
        if sort_col in df_tr.columns:
            df_tr = df_tr.sort_values(sort_col)
        realized = df_tr["realized_pnl"].astype(float)
        fees = df_tr["fee"].astype(float)
        wins = realized > 0
        losses = realized < 0
        n_trades = len(df_tr)
        n_long = int(is_long.sum())
        n_short = int(is_short.sum())
        long_realized = realized[is_long]
        short_realized = realized[is_short]
        long_wins = (long_realized > 0).sum()
        short_wins = (short_realized > 0).sum()
        return {
            "final_realized_pnl": float(realized.sum()),
            "winrate": float(wins.sum() / n_trades) if n_trades else 0.0,
            "winrate_long": float(long_wins / n_long) if n_long else 0.0,
            "winrate_short": float(short_wins / n_short) if n_short else 0.0,
            "pnl_long": float(long_realized.sum()),
            "pnl_short": float(short_realized.sum()),
            "n_trades": int(n_trades),
            "n_long_trades": int(n_long),
            "n_short_trades": int(n_short),
            "avg_win": float(realized[wins].mean() if wins.any() else 0.0),
            "avg_loss": float(realized[losses].mean() if losses.any() else 0.0),
            "max_win": float(realized.max() if not realized.empty else 0.0),
            "max_loss": float(realized.min() if not realized.empty else 0.0),
            "max_consecutive_wins": int(_max_streak(wins)),
            "max_consecutive_losses": int(_max_streak(losses)),
            "commissions": float(fees.sum()),
        }

    for run_id in run_ids:
        run_path = results_dir / run_id
        if not run_path.exists():
            continue
        for inst in instrument_ids:
            inst_dir = run_path / str(inst)
            trades_csv = inst_dir / "trades.csv"
            metrics_csv = inst_dir / "trade_metrics.csv"
            if metrics_csv.exists():
                continue
            if not trades_csv.exists():
                continue
            try:
                df_tr = _pd.read_csv(trades_csv)
                if df_tr.empty:
                    continue
                metrics = _compute_metrics(df_tr)
                if metrics:
                    inst_dir.mkdir(parents=True, exist_ok=True)
                    _pd.DataFrame([metrics]).to_csv(metrics_csv, index=False)
                    print(f"[compute_missing_trade_metrics] Created {metrics_csv}")
            except Exception as e:
                print(f"[compute_missing_trade_metrics] Failed for {trades_csv}: {e}")

def add_trade_metrics(run_ids, results_dir: Path, summary_csv_path: Path, instrument_ids):
    """
    Aggregates per-instrument trade_metrics.csv files into global per-run metrics
    and appends them as new columns to all_backtest_results.csv.

    For each run:
      Expects files at: results_dir / run_id / <instrument_id_str> / trade_metrics.csv
    New columns (prefixed with global_):
      final_realized_pnl, winrate, winrate_long, winrate_short,
      pnl_long, pnl_short, long_short_ratio, n_trades, n_long_trades, n_short_trades,
      avg_win, avg_loss, max_win, max_loss, max_consecutive_wins, max_consecutive_losses,
      commissions
    """
    import pandas as _pd
    import re  # NEW

    # NEW: proactively create missing trade_metrics.csv first
    compute_missing_trade_metrics(run_ids, results_dir, instrument_ids)

    if not summary_csv_path.exists():
        print("[add_trade_metrics] summary CSV not found -> skipped")
        return

    df_all = _pd.read_csv(summary_csv_path)

    # Ensure run_id column exists
    if "run_id" not in df_all.columns:
        print("[add_trade_metrics] run_id column missing in summary CSV -> skipped")
        return

    # Pre-create column names
    cols = [
        "global_final_realized_pnl",
        "global_winrate",
        "global_winrate_long",
        "global_winrate_short",
        "global_pnl_long",
        "global_pnl_short",
        "global_long_short_ratio",
        "global_n_trades",
        "global_n_long_trades",
        "global_n_short_trades",
        "global_avg_win",
        "global_avg_loss",
        "global_max_win",
        "global_max_loss",
        "global_max_consecutive_wins",
        "global_max_consecutive_losses",
        "global_commissions",
    ]
    for c in cols:
        if c not in df_all.columns:
            df_all[c] = None

    def _parse_number(val):
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val)
        m = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', s)
        return float(m.group(0)) if m else 0.0

    def _max_streak(mask_iterable):
        mx = cur = 0
        for v in mask_iterable:
            if v:
                cur += 1
                if cur > mx:
                    mx = cur
            else:
                cur = 0
        return mx

    def _compute_trade_metrics_from_trades(df_tr: _pd.DataFrame) -> dict:
        if df_tr.empty:
            return {}
        # Normalize numeric columns
        for col in ["realized_pnl", "fee", "tradesize"]:
            if col in df_tr.columns:
                df_tr[col] = df_tr[col].apply(_parse_number)
            else:
                df_tr[col] = 0.0

        # Direction detection: prefer 'action' (LONG/SHORT); fallback to tradesize sign
        if "action" in df_tr.columns:
            actions = df_tr["action"].astype(str).str.upper()
            is_long = actions.eq("LONG")
            is_short = actions.eq("SHORT")
        else:
            is_long = df_tr["tradesize"] > 0
            is_short = df_tr["tradesize"] < 0

        # Sort for streak calculation (prefer closed_timestamp)
        sort_col = "closed_timestamp" if "closed_timestamp" in df_tr.columns else "timestamp"
        if sort_col in df_tr.columns:
            df_tr = df_tr.sort_values(sort_col)

        realized = df_tr["realized_pnl"].astype(float)
        fees = df_tr["fee"].astype(float)

        wins = realized > 0
        losses = realized < 0

        n_trades = len(df_tr)
        n_long = int(is_long.sum())
        n_short = int(is_short.sum())

        long_realized = realized[is_long]
        short_realized = realized[is_short]

        long_wins = (long_realized > 0).sum()
        short_wins = (short_realized > 0).sum()

        metrics = {
            "final_realized_pnl": float(realized.sum()),
            "winrate": float((wins.sum() / n_trades) if n_trades else 0.0),
            "winrate_long": float((long_wins / n_long) if n_long else 0.0),
            "winrate_short": float((short_wins / n_short) if n_short else 0.0),
            "pnl_long": float(long_realized.sum()),
            "pnl_short": float(short_realized.sum()),
            "n_trades": int(n_trades),
            "n_long_trades": int(n_long),
            "n_short_trades": int(n_short),
            "avg_win": float(realized[wins].mean() if wins.any() else 0.0),
            "avg_loss": float(realized[losses].mean() if losses.any() else 0.0),
            "max_win": float(realized.max() if not realized.empty else 0.0),
            "max_loss": float(realized.min() if not realized.empty else 0.0),
            "max_consecutive_wins": int(_max_streak(wins)),
            "max_consecutive_losses": int(_max_streak(losses)),
            "commissions": float(fees.sum()),
        }
        return metrics

    for run_id in run_ids:
        run_path = results_dir / run_id
        if not run_path.exists():
            continue

        # Aggregators
        total_final_realized = 0.0
        total_pnl_long = 0.0
        total_pnl_short = 0.0
        total_trades = 0
        total_long_trades = 0
        total_short_trades = 0
        total_commissions = 0.0

        # For weighted averages
        total_wins = 0.0      # count wins
        total_long_wins = 0.0
        total_short_wins = 0.0

        sum_wins_amount = 0.0    # sum of winning trade PnL for avg_win computation
        sum_losses_amount = 0.0  # sum of losing trade PnL for avg_loss computation (negative)
        est_total_losses = 0.0   # count of losing trades (estimated, see note)

        global_max_win = None
        global_max_loss = None
        global_max_consec_wins = 0
        global_max_consec_losses = 0

        any_file = False

        # NEW: collect all trades across instruments for this run
        combined_trades_dfs = []

        for inst in instrument_ids:
            inst_str = str(inst)
            inst_dir = run_path / inst_str
            metrics_csv = inst_dir / "trade_metrics.csv"
            trades_csv = inst_dir / "trades.csv"

            # Collect trades for combined file & create metrics if missing
            df_tr = None
            if trades_csv.exists():
                try:
                    df_tr = _pd.read_csv(trades_csv)
                    if not df_tr.empty:
                        df_tr["instrument"] = inst_str
                        combined_trades_dfs.append(df_tr.copy())
                        if not metrics_csv.exists():
                            metrics_dict = _compute_trade_metrics_from_trades(df_tr.copy())
                            if metrics_dict:
                                _pd.DataFrame([metrics_dict]).to_csv(metrics_csv, index=False)
                                print(f"[add_trade_metrics] Created {metrics_csv}")
                except Exception as e:
                    print(f"[add_trade_metrics] Failed reading {trades_csv}: {e}")

            if not metrics_csv.exists():
                continue  # still no metrics -> skip

            try:
                dfm = _pd.read_csv(metrics_csv)
                if dfm.empty:
                    continue
                row = dfm.iloc[0]
                any_file = True

                frp = float(row.get("final_realized_pnl", 0) or 0)
                wl = float(row.get("winrate_long", 0) or 0)
                ws = float(row.get("winrate_short", 0) or 0)
                wr = float(row.get("winrate", 0) or 0)
                pnl_l = float(row.get("pnl_long", 0) or 0)
                pnl_s = float(row.get("pnl_short", 0) or 0)
                n_tr = int(row.get("n_trades", 0) or 0)
                n_long = int(row.get("n_long_trades", 0) or 0)
                n_short = int(row.get("n_short_trades", 0) or 0)
                avg_win_inst = float(row.get("avg_win", 0) or 0)
                avg_loss_inst = float(row.get("avg_loss", 0) or 0)
                max_win_inst = float(row.get("max_win", 0) or 0)
                max_loss_inst = float(row.get("max_loss", 0) or 0)
                cons_w = int(row.get("max_consecutive_wins", 0) or 0)
                cons_l = int(row.get("max_consecutive_losses", 0) or 0)
                commissions_inst = float(row.get("commissions", 0) or 0)

                # Derived counts
                wins_inst = wr * n_tr  # includes assumption: winrate = wins / total trades
                # Loss count approximation (ignores breakeven trades if any)
                losses_inst = max(n_tr - wins_inst, 0)

                # Weighted sums
                sum_wins_amount += avg_win_inst * wins_inst
                sum_losses_amount += avg_loss_inst * losses_inst
                total_wins += wins_inst
                est_total_losses += losses_inst

                # Long / short wins
                long_wins_inst = wl * n_long if n_long > 0 else 0
                short_wins_inst = ws * n_short if n_short > 0 else 0
                total_long_wins += long_wins_inst
                total_short_wins += short_wins_inst

                # Simple sums
                total_final_realized += frp
                total_pnl_long += pnl_l
                total_pnl_short += pnl_s
                total_trades += n_tr
                total_long_trades += n_long
                total_short_trades += n_short
                total_commissions += commissions_inst

                # Extremes
                if global_max_win is None or max_win_inst > global_max_win:
                    global_max_win = max_win_inst
                if global_max_loss is None or max_loss_inst < global_max_loss:
                    global_max_loss = max_loss_inst
                if cons_w > global_max_consec_wins:
                    global_max_consec_wins = cons_w
                if cons_l > global_max_consec_losses:
                    global_max_consec_losses = cons_l

            except Exception as e:
                print(f"[add_trade_metrics] Failed reading {metrics_csv}: {e}")

        # After instrument loop: write combined trades.csv for this run
        if combined_trades_dfs:
            try:
                combined_trades = _pd.concat(combined_trades_dfs, ignore_index=True, sort=False)
                if "timestamp" in combined_trades.columns:
                    combined_trades = combined_trades.sort_values("timestamp")
                out_path = run_path / "all_trades.csv"  # renamed
                combined_trades.to_csv(out_path, index=False)
                print(f"[add_trade_metrics] Combined trades saved: {out_path}")
            except Exception as e:
                print(f"[add_trade_metrics] Failed writing combined trades for {run_id}: {e}")

        if not any_file:
            continue

        # Aggregated winrates (avoid division by zero)
        global_winrate = (total_wins / total_trades) if total_trades > 0 else 0.0
        global_winrate_long = (total_long_wins / total_long_trades) if total_long_trades > 0 else 0.0
        global_winrate_short = (total_short_wins / total_short_trades) if total_short_trades > 0 else 0.0

        # Weighted averages
        global_avg_win = (sum_wins_amount / total_wins) if total_wins > 0 else 0.0
        global_avg_loss = (sum_losses_amount / est_total_losses) if est_total_losses > 0 else 0.0

        # Ratio
        if total_short_trades > 0:
            global_long_short_ratio = total_long_trades / total_short_trades
        else:
            global_long_short_ratio = float("inf") if total_long_trades > 0 else 0.0

        # Assign into df_all row
        mask = df_all["run_id"] == run_id
        df_all.loc[mask, "global_final_realized_pnl"] = total_final_realized
        df_all.loc[mask, "global_winrate"] = global_winrate
        df_all.loc[mask, "global_winrate_long"] = global_winrate_long
        df_all.loc[mask, "global_winrate_short"] = global_winrate_short
        df_all.loc[mask, "global_pnl_long"] = total_pnl_long
        df_all.loc[mask, "global_pnl_short"] = total_pnl_short
        df_all.loc[mask, "global_long_short_ratio"] = global_long_short_ratio
        df_all.loc[mask, "global_n_trades"] = total_trades
        df_all.loc[mask, "global_n_long_trades"] = total_long_trades
        df_all.loc[mask, "global_n_short_trades"] = total_short_trades
        df_all.loc[mask, "global_avg_win"] = global_avg_win
        df_all.loc[mask, "global_avg_loss"] = global_avg_loss
        df_all.loc[mask, "global_max_win"] = global_max_win
        df_all.loc[mask, "global_max_loss"] = global_max_loss
        df_all.loc[mask, "global_max_consecutive_wins"] = global_max_consec_wins
        df_all.loc[mask, "global_max_consecutive_losses"] = global_max_consec_losses
        df_all.loc[mask, "global_commissions"] = total_commissions

    df_all.to_csv(summary_csv_path, index=False)
    print("[add_trade_metrics] Global trade metrics appended.")

def _resolve_data_cls(value):
    """
    Accepts:
      - already-imported class
      - "module:Class"
      - "module.Class"
    Returns class if importable, else returns original value (string).
    """
    try:
        if isinstance(value, type):
            return value
        if not isinstance(value, str):
            return value

        if ":" in value:
            mod_path, cls_name = value.split(":", 1)
            try:
                mod = importlib.import_module(mod_path)
                return getattr(mod, cls_name)
            except Exception:
                return value
        if "." in value:
            mod_path, cls_name = value.rsplit(".", 1)
            try:
                mod = importlib.import_module(mod_path)
                return getattr(mod, cls_name)
            except Exception:
                return value
        return value
    except Exception:
        return value

def _is_standard_nautilus_data_cls(value) -> bool:
    """
    True for classes in nautilus_trader.model.data (e.g. Bar, TradeTick, QuoteTick, etc.).
    Accepts either an imported class or a string ("module:Class" or "module.Class").
    """
    try:
        if isinstance(value, type):
            return getattr(value, "__module__", "").startswith("nautilus_trader.model.data")
        if isinstance(value, str):
            return value.startswith("nautilus_trader.model.data")
        return False
    except Exception:
        return False

def build_data_configs(
    data_sources_normalized: List[Dict[str, Any]],
    all_instrument_ids: List[str],
    all_bar_types: List[str],
    catalog_path: str,
) -> List[BacktestDataConfig]:
    """
    Builds BacktestDataConfig list from normalized 'data_sources'.
    Falls back to standard Bar config if none provided.
    Sets client_id = "my client id" for custom (non-nautilus) data classes when missing.
    """
    data_configs: List[BacktestDataConfig] = []

    if data_sources_normalized:
        for ds in data_sources_normalized:
            data_cls = _resolve_data_cls(ds["data_cls"])
            kwargs = dict(ds.get("kwargs", {}))
            if "catalog_path" not in kwargs:
                kwargs["catalog_path"] = catalog_path
            kwargs["instrument_ids"] = ds["instrument_ids"]
            if ds.get("bar_types"):
                kwargs["bar_types"] = ds["bar_types"]
            if "client_id" not in kwargs and not _is_standard_nautilus_data_cls(data_cls):
                kwargs["client_id"] = "my client id"
            data_configs.append(BacktestDataConfig(data_cls=data_cls, **kwargs))
        return data_configs

    # Fallback: Standard Bars from instrument definitions
    data_configs.append(
        BacktestDataConfig(
            data_cls="nautilus_trader.model.data:Bar",
            catalog_path=catalog_path,
            bar_types=all_bar_types,
            instrument_ids=all_instrument_ids,
        )
    )
    return data_configs