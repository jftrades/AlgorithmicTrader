import itertools
import pandas as pd
import uuid
from pathlib import Path
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from tools.help_funcs.help_funcs_execution import (run_backtest, extract_metrics, visualize_existing_run, show_quantstats_report_from_equity_csv)
from tools.help_funcs.yaml_loader import load_and_split_params
import shutil
import yaml
import copy
from glob import glob
import os
import webbrowser


# Parameter laden und aufteilen
yaml_path = str(Path(__file__).resolve().parents[1] / "config" / "alpha_meme.yaml")
params, param_grid, keys, values, static_params, all_instrument_ids, all_bar_types = load_and_split_params(yaml_path)

start_date = params["start_date"]
end_date = params["end_date"]
venue = params["venue"]
print(params)

#----------------

catalog_path = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar",
    catalog_path=catalog_path,
    bar_types=all_bar_types,
    instrument_ids=all_instrument_ids,
)

# VenueConfig 
venue_config = BacktestVenueConfig(
    name=str(venue), 
    oms_type=params.get("oms_type", "NETTING"),
    account_type=params.get("account_type", "MARGIN"),
    base_currency=params.get("base_currency", "USDT"),
    starting_balances=[params.get("starting_account_balance", "100000 USDT")]
)

results_dir = Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "results"
results_dir.mkdir(parents=True, exist_ok=True)
tmp_runs_dir = results_dir.parent / "_tmp_runs"

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

# Frischer Zustand zu Beginn (entfernt alte runs und alte Collector-Ordner)
_clear_directory(results_dir)
if tmp_runs_dir.exists():
    shutil.rmtree(tmp_runs_dir, ignore_errors=True)
tmp_runs_dir.mkdir(parents=True, exist_ok=True)

def _gather_collectors(results_root: Path):
    """Nur aktuelle Collector-Ordner auswählen (keine run*-Verzeichnisse, kein _tmp_runs)."""
    collectors = []
    for p in results_root.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name.startswith("run"):      # ausschließen: run0, run1, ...
            continue
        if name == "_tmp_runs":
            continue
        collectors.append(p)
    return collectors

def _copy_collectors_into_run(collectors, run_dir: Path):
    """Kopiert jeden Collector-Ordner direkt in das Run-Verzeichnis."""
    for c in collectors:
        dst = run_dir / c.name
        shutil.copytree(c, dst, dirs_exist_ok=True)

def _find_equity_csv(run_dir: Path):
    """Sucht indicators/equity.csv im Collector 'general' oder erstem Collector."""
    general_path = run_dir / "general" / "indicators" / "equity.csv"
    if general_path.exists():
        return general_path
    # Fallback: erster Collector mit equity.csv
    for c in run_dir.iterdir():
        if c.is_dir() and c.name.startswith("run") is False:
            candidate = c / "indicators" / "equity.csv"
            if candidate.exists():
                return candidate
    return None

def run_and_collect(i, combination, keys, static_params, params, results_dir, tmp_runs_dir, data_config, venue_config, start_date, end_date):
    run_params = dict(zip(keys, combination))
    config_params = {**run_params, **static_params}

    run_id = f"run{i}"  # <--- vereinfacht
    tmp_run_dir = tmp_runs_dir / run_id
    tmp_run_dir.mkdir(parents=True, exist_ok=True)

    # Save config
    run_config_dict = copy.deepcopy(params)
    run_config_dict.update(run_params)
    run_config_dict.update(static_params)
    with open(tmp_run_dir / "run_config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(run_config_dict, f, allow_unicode=True, sort_keys=False)

    # Backtest
    strategy_config = ImportableStrategyConfig(
        strategy_path="strategies.alpha_meme_strat:AlphaMemeStrategy",
        config_path="strategies.alpha_meme_strat:AlphaMemeStrategyConfig",
        config=config_params
    )
    engine_config = BacktestEngineConfig(strategies=[strategy_config])
    run_config = BacktestRunConfig(
        data=[data_config], venues=[venue_config], engine=engine_config,
        start=start_date, end=end_date
    )
    result = run_backtest(run_config)

    metrics = extract_metrics(result, run_params, run_id)
    pd.DataFrame([metrics]).to_csv(tmp_run_dir / "performance_metrics.csv", index=False)

    # Collector-Verarbeitung
    collectors = _gather_collectors(results_dir)
    _copy_collectors_into_run(collectors, tmp_run_dir)

    # Optional: QuantStats
    equity_path = _find_equity_csv(tmp_run_dir)
    qs_report_path = tmp_run_dir / "quantstats_report.html"
    if params.get("visualise_qs", False) and equity_path:
        show_quantstats_report_from_equity_csv(
            equity_csv=equity_path,
            benchmark_symbol="BTC-USD",
            output_path=qs_report_path
        )
        if qs_report_path.exists():
            webbrowser.open_new_tab(str(qs_report_path.resolve()))

    return (run_id, tmp_run_dir, metrics)

def move_and_cleanup(run_dirs, results_dir, tmp_runs_dir):
    for run_id, tmp_run_dir, _ in run_dirs:
        final_run_dir = results_dir / run_id
        if final_run_dir.exists():
            shutil.rmtree(final_run_dir)
        if tmp_run_dir.exists():
            shutil.move(str(tmp_run_dir), str(final_run_dir))
    # Entferne Collector-Rohordner (wurden kopiert)
    for p in list(results_dir.iterdir()):
        if p.is_dir() and p.name.startswith("run") is False:
            shutil.rmtree(p, ignore_errors=True)
    if tmp_runs_dir.exists():
        shutil.rmtree(tmp_runs_dir, ignore_errors=True)
    print("Aufräumen abgeschlossen. Run-Ordner enthalten jetzt eigenständige Collector-Daten.")

def visualize_best_run(df, results_dir, sharpe_col, params):
    # Suche best run via run{i}
    if sharpe_col in df.columns:
        best_idx = df[sharpe_col].astype(float).idxmax()
        run_dir = results_dir / f"run{best_idx}"
        if run_dir.exists():
            print(f"Starte Visualisierung für {run_dir} (Sharpe: {df.loc[best_idx, sharpe_col]})")
            equity_path = _find_equity_csv(run_dir)
            qs_report_path = run_dir / "quantstats_report.html"
            if params.get("visualise_qs", False) and equity_path:
                show_quantstats_report_from_equity_csv(
                    equity_csv=equity_path,
                    benchmark_symbol="BTC-USD",
                    output_path=qs_report_path
                )
                if qs_report_path.exists():
                    webbrowser.open_new_tab(str(qs_report_path.resolve()))
            visualize_existing_run(run_dir)
        else:
            print(f"FEHLER: Run-Verzeichnis {run_dir} nicht gefunden.")
    else:
        print(f"Spalte '{sharpe_col}' nicht gefunden, keine Visualisierung gestartet.")

# Hauptablauf
run_dirs = []
all_metrics = []
for i, combination in enumerate(itertools.product(*values)):
    run_id, tmp_run_dir, metrics = run_and_collect(
        i, combination, keys, static_params, params, results_dir, tmp_runs_dir,
        data_config, venue_config, start_date, end_date
    )
    run_dirs.append((run_id, tmp_run_dir, metrics))
    all_metrics.append(metrics)

move_and_cleanup(run_dirs, results_dir, tmp_runs_dir)

df = pd.DataFrame(all_metrics)
df.to_csv(results_dir / "all_backtest_results.csv", index=False)
print(df)

visualize_best_run(df, results_dir, "RET_Sharpe Ratio (252 days)", params)