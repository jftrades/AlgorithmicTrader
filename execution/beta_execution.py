import itertools
import pandas as pd
import uuid
from pathlib import Path
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from tools.help_funcs.help_funcs_execution import (
    run_backtest, extract_metrics, visualize_existing_run, load_and_split_params, show_quantstats_report_from_equity_csv
)
import shutil
import yaml
import copy
from glob import glob
import os
import webbrowser

# Parameter laden und aufteilen
yaml_path = str(Path(__file__).resolve().parents[1] / "config" / "beta.yaml")
params, param_grid, keys, values, static_params = load_and_split_params(yaml_path)

start_date = params["start_date"]
end_date = params["end_date"]

# Parameter
symbol = Symbol(params["symbol"])
venue = Venue(params["venue"])
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = params["instrument_id"]
bar_type = params["bar_type"]
risk_percent = params["risk_percent"]
max_leverage = params["max_leverage"]
min_account_balance = params["min_account_balance"]

catalog_path = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar",
    catalog_path=catalog_path,
    bar_types=[bar_type],
    instrument_ids=[instrument_id_str]
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
tmp_runs_dir.mkdir(parents=True, exist_ok=True)

def run_and_collect(i, combination, keys, static_params, params, results_dir, tmp_runs_dir, data_config, venue_config, start_date, end_date):
    run_params = dict(zip(keys, combination))
    config_params = {**run_params, **static_params}
    run_id = f"run_{i}_{uuid.uuid4().hex[:6]}"
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
        strategy_path="strategies.beta_strat:RSISimpleStrategy",
        config_path="strategies.beta_strat:RSISimpleStrategyConfig",
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

    # Copy run data
    indicators_src = results_dir / "indicators"
    indicators_dst = tmp_run_dir / "indicators"
    if indicators_src.exists():
        shutil.copytree(indicators_src, indicators_dst, dirs_exist_ok=True)
    for fname in ["bars.csv", "trades.csv"]:
        src = results_dir / fname
        dst = tmp_run_dir / fname
        if src.exists():
            shutil.copy2(src, dst)

    # QuantStats report (nur wenn visualise_qs true)
    equity_path = tmp_run_dir / "indicators" / "equity.csv"
    qs_report_path = tmp_run_dir / "quantstats_report.html"
    if params.get("visualise_qs", False) and equity_path.exists():
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
    if tmp_runs_dir.exists():
        shutil.rmtree(tmp_runs_dir, ignore_errors=True)
    # Remove central files
    for fname in ["indicators", "bars.csv", "trades.csv"]:
        fpath = results_dir / fname
        if fpath.exists():
            if fpath.is_dir():
                shutil.rmtree(fpath)
            else:
                fpath.unlink()
    print("Aufräumen abgeschlossen. Nur Run-Ordner und all_backtest_results.csv bleiben erhalten.")

def visualize_best_run(df, results_dir, sharpe_col, params):
    if sharpe_col in df.columns:
        best_idx = df[sharpe_col].astype(float).idxmax()
        run_prefix = f"run_{best_idx}_"
        candidates = [f for f in os.listdir(results_dir) if f.startswith(run_prefix) and os.path.isdir(results_dir / f)]
        if candidates:
            best_run_dir = results_dir / candidates[0]
            print(f"Starte Visualisierung für besten Run-Ordner: {best_run_dir} (Sharpe: {df.loc[best_idx, sharpe_col]})")
            equity_path = best_run_dir / "indicators" / "equity.csv"
            qs_report_path = best_run_dir / "quantstats_report.html"
            if params.get("visualise_qs", False) and equity_path.exists():
                show_quantstats_report_from_equity_csv(
                    equity_csv=equity_path,
                    benchmark_symbol="BTC-USD",
                    output_path=qs_report_path
                )
                if qs_report_path.exists():
                    webbrowser.open_new_tab(str(qs_report_path.resolve()))
            visualize_existing_run(best_run_dir)
        else:
            print(f"FEHLER: Kein passender Run-Ordner mit Prefix {run_prefix} gefunden!")
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