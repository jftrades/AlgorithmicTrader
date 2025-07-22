# Standard Library Importe
import sys
import time
import pandas as pd
import re
import numpy as np
from pathlib import Path
# import quantstats as qs
import webbrowser, os

# Nautilus Kern Importe
from nautilus_trader.backtest.node import BacktestNode
from core.visualizing.dashboard import TradingDashboard

def run_backtest(run_config):
    node = BacktestNode([run_config])  # Übergib eine Liste!
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
    if result and hasattr(result, "__getitem__"):
        result_obj = result[0]
        # Standard-Infos
        metrics.update(run_params)
        metrics["run_id"] = getattr(result_obj, "run_id", None)
        metrics["backtest_start"] = getattr(result_obj, "backtest_start", None)
        metrics["backtest_end"] = getattr(result_obj, "backtest_end", None)
        metrics["elapsed_time"] = getattr(result_obj, "elapsed_time", None)
        metrics["iterations"] = getattr(result_obj, "iterations", None)
        metrics["total_events"] = getattr(result_obj, "total_events", None)
        metrics["total_orders"] = getattr(result_obj, "total_orders", None)
        metrics["total_positions"] = getattr(result_obj, "total_positions", None)
        # PnL/Return-Metriken (z.B. nur USDT)
        if hasattr(result_obj, "stats_pnls") and "USDT" in result_obj.stats_pnls:
            for k, v in result_obj.stats_pnls["USDT"].items():
                metrics[f"USDT_{k}"] = v
        if hasattr(result_obj, "stats_returns"):
            for k, v in result_obj.stats_returns.items():
                metrics[f"RET_{k}"] = v
    else:
        # Fallback: nur Parameter speichern
        metrics.update(run_params)
        metrics["run_id"] = run_id
    return metrics

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


# def quantstats_equity_curve_from_csv(balance_csv, realized_pnl_csv, unrealized_pnl_csv):
#     # Einlesen
#     balance = pd.read_csv(balance_csv, usecols=["timestamp", "value"])
#     realized = pd.read_csv(realized_pnl_csv, usecols=["timestamp", "value"])
#     unrealized = pd.read_csv(unrealized_pnl_csv, usecols=["timestamp", "value"])
#
#     # Alle Zeitstempel vereinheitlichen (Union statt Intersection)
#     all_timestamps = pd.Index(sorted(set(balance["timestamp"]) | set(realized["timestamp"]) | set(unrealized["timestamp"])))
#     balance_series = pd.Series(balance["value"].values, index=balance["timestamp"].values).reindex(all_timestamps, fill_value=0)
#     realized_series = pd.Series(realized["value"].fillna(0).values, index=realized["timestamp"].values).reindex(all_timestamps, fill_value=0)
#     unrealized_series = pd.Series(unrealized["value"].fillna(0).values, index=unrealized["timestamp"].values).reindex(all_timestamps, fill_value=0)
#
#     # Equity berechnen
#     equity = balance_series.astype(float) + realized_series.astype(float) + unrealized_series.astype(float)
#     equity.index = pd.to_datetime(equity.index, unit="ns")
#     equity.name = "equity"
#     return equity
#
# def show_quantstats_report_from_csv(balance_csv, realized_pnl_csv, unrealized_pnl_csv, title="QuantStats Report", output_path="quantstats_report.html"):
#     equity = quantstats_equity_curve_from_csv(balance_csv, realized_pnl_csv, unrealized_pnl_csv)
#     equity = equity[~equity.index.duplicated(keep='first')]
#     if isinstance(equity, pd.DataFrame):
#         equity = equity.iloc[:, 0]
#     returns = equity.pct_change().dropna().astype(float)
#     returns.index.name = None
#     returns.name = None
#
#     # Check: Returns dürfen nicht leer oder konstant sein!
#     if returns.empty or (returns == 0).all():
#         print("WARNUNG: Die Returns-Serie ist leer oder konstant. Kein QuantStats-Report möglich.")
#         return
#
#     if not isinstance(returns.index, pd.DatetimeIndex):
#         raise ValueError("Index von returns ist kein DatetimeIndex!")
#     if not returns.index.is_unique:
#         raise ValueError("Index von returns ist nicht eindeutig!")
#
#     try:
#         dummy_returns = pd.Series(np.random.normal(0, 0.01, 100), index=pd.date_range("2020-01-01", periods=100))
#         qs.reports.full(dummy_returns, title="Dummy Report", output="dummy_report.html")
#         abs_path = os.path.abspath(str(output_path))
#         if os.path.exists(abs_path):
#             webbrowser.open_new_tab('file://' + abs_path)
#     except Exception as e:
#         print("FEHLER beim Erstellen des QuantStats-Reports:", e)