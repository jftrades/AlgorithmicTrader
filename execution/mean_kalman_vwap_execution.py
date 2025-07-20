###
import itertools
import pandas as pd
import uuid
from pathlib import Path
from tools.help_funcs.yaml_loader import load_params
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from tools.help_funcs.help_funcs_execution import run_backtest, extract_metrics, visualize_existing_run
import shutil
import yaml
import copy
from glob import glob
import os

# Parameter laden
yaml_path = str(Path(__file__).resolve().parents[1] / "config" / "mean_kalman_vwap.yaml")
params = load_params(yaml_path)

param_grid = {k: v for k, v in params.items() if isinstance(v, list)}
keys, values = zip(*param_grid.items()) if param_grid else ([], [])

static_params = {k: v for k, v in params.items() if not isinstance(v, list)}

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
    base_currency=params.get("base_currency", "USD"),
    starting_balances=[params.get("starting_account_balance", "100000 USD")]
)

results_dir = Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "results"
results_dir.mkdir(parents=True, exist_ok=True)
tmp_runs_dir = results_dir.parent / "_tmp_runs"
tmp_runs_dir.mkdir(parents=True, exist_ok=True)

run_dirs = []
all_results = []
for i, combination in enumerate(itertools.product(*values)):
    run_params = dict(zip(keys, combination))
    config_params = {**run_params, **static_params}
    print(f"Run {i}: {config_params}")
    run_id = f"run_{i}_{uuid.uuid4().hex[:6]}"

    # config im run-ordner speichern
    run_config_dict = copy.deepcopy(params)
    for k, v in run_params.items():
        run_config_dict[k] = v
    for k, v in static_params.items():
        run_config_dict[k] = v
    tmp_run_dir = tmp_runs_dir / run_id
    tmp_run_dir.mkdir(parents=True, exist_ok=True)
    with open(tmp_run_dir / "run_config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(run_config_dict, f, allow_unicode=True, sort_keys=False)


    # StrategyConfig 
    strategy_config = ImportableStrategyConfig(
        strategy_path="strategies.mean_kalman_vwap_strategy:MeankalmanvwapStrategy",
        config_path="strategies.mean_kalman_vwap_strategy:MeankalmanvwaptrategyConfig",
        config=config_params
    )

    # EnigneConfig
    engine_config = BacktestEngineConfig(strategies=[strategy_config])

    # RunConfig  
    run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)

    result = run_backtest(run_config)
    tmp_run_dir = tmp_runs_dir / run_id
    tmp_run_dir.mkdir(parents=True, exist_ok=True)
    run_dirs.append((run_id, tmp_run_dir))

    metrics = extract_metrics(result, run_params, run_id)
    all_results.append(metrics)
    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv(tmp_run_dir / "performance_metrics.csv", index=False)

    try:
        # Kopiere Indikatoren
        indicators_src = results_dir / "indicators"
        indicators_dst = tmp_run_dir / "indicators"
        if indicators_src.exists():
            shutil.copytree(indicators_src, indicators_dst, dirs_exist_ok=True)
        # Kopiere Bars und Trades
        for fname in ["bars.csv", "trades.csv"]:
            src = results_dir / fname
            dst = tmp_run_dir / fname
            if src.exists():
                shutil.copy2(src, dst)
    except Exception as e:
        print(f"Fehler beim Kopieren der Run-Daten: {e}")

# Nach allen Runs:
for run_id, tmp_run_dir in run_dirs:
    final_run_dir = results_dir / run_id
    if final_run_dir.exists():
        shutil.rmtree(final_run_dir)
    if tmp_run_dir.exists():
        shutil.move(str(tmp_run_dir), str(final_run_dir))
    else:
        print(f"Warnung: Quellordner {tmp_run_dir} existiert nicht und kann nicht verschoben werden.")

# Optional: temporären Ordner löschen
if tmp_runs_dir.exists():
    shutil.rmtree(tmp_runs_dir, ignore_errors=True)

if (tmp_run_dir / "performance_metrics.csv").exists():
    shutil.move(str(tmp_run_dir / "performance_metrics.csv"), str(final_run_dir / "performance_metrics.csv"))

df = pd.DataFrame(all_results)

df.to_csv(results_dir / "all_backtest_results.csv", index=False)
print(df)

# Lösche zentrale Indikatoren, Bars und Trades nach dem Verschieben der Runs
indicators_dir = results_dir / "indicators"
bars_file = results_dir / "bars.csv"
trades_file = results_dir / "trades.csv"

if indicators_dir.exists() and indicators_dir.is_dir():
    shutil.rmtree(indicators_dir)
if bars_file.exists():
    bars_file.unlink()
if trades_file.exists():
    trades_file.unlink()

print("Aufräumen abgeschlossen. Nur Run-Ordner und all_backtest_results.csv bleiben erhalten.")

# --- NEU: Bestes Sharpe Ratio finden und visualisieren ---
sharpe_col = "RET_Sharpe Ratio (252 days)"
if sharpe_col in df.columns:
    best_idx = df[sharpe_col].astype(float).idxmax()
    run_prefix = f"run_{best_idx}_"
    candidates = [f for f in os.listdir(results_dir) if f.startswith(run_prefix) and os.path.isdir(results_dir / f)]
    if candidates:
        best_run_dir = results_dir / candidates[0]
        print(f"Starte Visualisierung für besten Run-Ordner: {best_run_dir} (Sharpe: {df.loc[best_idx, sharpe_col]})")
        from tools.help_funcs.help_funcs_execution import visualize_existing_run
        visualize_existing_run(best_run_dir)
    else:
        print(f"FEHLER: Kein passender Run-Ordner mit Prefix {run_prefix} gefunden!")
else:
    print(f"Spalte '{sharpe_col}' nicht gefunden, keine Visualisierung gestartet.")