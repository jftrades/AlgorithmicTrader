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


# Nautilus Kern Importe
from nautilus_trader.backtest.node import BacktestNode
from core.visualizing.dashboard1 import TradingDashboard

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
        metrics["run_id"] = run_id
        metrics["run_started"] = getattr(result_obj, "run_started", None)
        metrics["run_finished"] = getattr(result_obj, "run_finished", None)
        metrics["backtest_start"] = getattr(result_obj, "backtest_start", None)
        metrics["backtest_end"] = getattr(result_obj, "backtest_end", None)
        metrics["elapsed_time"] = getattr(result_obj, "elapsed_time", None)
        metrics["total_orders"] = getattr(result_obj, "total_orders", None)
        metrics["total_positions"] = getattr(result_obj, "total_positions", None)
        
        # PnL/Return-Metriken (z.B. nur USDT)
        if hasattr(result_obj, "stats_pnls") and "USDT" in result_obj.stats_pnls:
            for k, v in result_obj.stats_pnls["USDT"].items():
                metrics[f"USDT_{k}"] = v
        if hasattr(result_obj, "stats_returns"):
            for k, v in result_obj.stats_returns.items():
                metrics[f"{k}"] = v
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

    qs.reports.html(returns, benchmark=benchmark, output=str(output_path) if output_path else None)