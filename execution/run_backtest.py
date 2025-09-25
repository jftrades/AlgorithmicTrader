import itertools
import pandas as pd
import uuid
from pathlib import Path
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from tools.help_funcs.help_funcs_execution import (_clear_directory, run_backtest, extract_metrics, load_qs, add_trade_metrics, build_data_configs)
from tools.help_funcs.yaml_loader import load_and_split_params
import shutil
import yaml
import copy
from glob import glob
import os
import webbrowser
from core.visualizing.dashboard.main import launch_dashbaord

#STRAT PARAMETER

yaml_name = "test_custom_data.yaml"

# ------------------------------------------------------------
# YAML laden & vorbereiten
# ------------------------------------------------------------
yaml_path = str(Path(__file__).resolve().parents[1] / "config" / yaml_name)
params, param_grid, keys, values, static_params, all_instrument_ids, all_bar_types, data_sources_normalized = load_and_split_params(yaml_path)

strategy_path = params["strategy_path"]
config_path = params["config_path"]
start_date = params["start_date"]
end_date = params["end_date"]
venue = params["venue"]
visualize = params.get("visualize", True)
load_qs_flag = params.get("load_qs", False)  # renamed to avoid clash with function
bench_qs = params.get("qs_bench")  # accept both YAML key variants

# ------------------------------------------------------------
# Daten-/Venue-Konfiguration
# ------------------------------------------------------------
catalog_path = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

# Datenquellen aus YAML bauen (fallback auf Standard-Bar wenn nicht angegeben)
data_configs = build_data_configs(
    data_sources_normalized=data_sources_normalized,
    all_instrument_ids=all_instrument_ids,
    all_bar_types=all_bar_types,
    catalog_path=catalog_path,
)

venue_config = BacktestVenueConfig(
    name=str(venue),
    oms_type=params.get("oms_type", "NETTING"),
    account_type=params.get("account_type", "MARGIN"),
    base_currency=params.get("base_currency", "USDT"),
    starting_balances=[params.get("starting_account_balance", "100000 USDT")],
)

# ------------------------------------------------------------
# Ordner vorbereiten
# ------------------------------------------------------------
results_dir = Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "results"
results_dir.mkdir(parents=True, exist_ok=True)
_clear_directory(results_dir)  # komplett leeren, wie bisherige Logik

# ------------------------------------------------------------
# Run-Konfigurationen erstellen (NICHT ausführen)
# ------------------------------------------------------------
run_configs = []            # Liste von BacktestRunConfig (Index i -> run_id f"run{i}")
run_ids = []                # ["run0", "run1", ...] gleiche Reihenfolge wie run_configs
run_params_list = []        # Liste der jeweiligen Grid-Parameter-Dicts (Index i passend zur run_id)
run_dirs = []               # Liste der Pfade zum jeweiligen Run-Ordner

# Wenn es keine Grid-Keys gibt, liefert itertools.product() über leere Sequenz genau 1 Kombination: ()
for i, combination in enumerate(itertools.product(*values)):
    run_id = f"run{i}"
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Grid-Parameter für diesen Lauf
    run_params = dict(zip(keys, combination))
    # Config-Parameter (Grid + statische)
    config_params = {**run_params, **static_params}
    # run_id als zusätzlicher Parameter in die Strategy-Config reinschreiben
    config_params["run_id"] = run_id

    # Strategy-/Engine-/Run-Config bauen
    strategy_config = ImportableStrategyConfig(
        strategy_path=strategy_path,
        config_path=config_path,
        config=config_params,
    )
    engine_config = BacktestEngineConfig(strategies=[strategy_config])
    run_config = BacktestRunConfig(
        data=data_configs,
        venues=[venue_config],
        engine=engine_config,
        start=start_date,
        end=end_date,
    )

    # YAML der effektiven Konfiguration speichern (inkl. run_id und Grid/Singles)
    run_config_dict = copy.deepcopy(params)
    run_config_dict.update(run_params)
    run_config_dict.update(static_params)
    run_config_dict["run_id"] = run_id  # zusätzlich auch oben rein, damit es eindeutig im YAML steht
    with open(run_dir / "run_config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(run_config_dict, f, allow_unicode=True, sort_keys=False)

    # Sammler füllen
    run_configs.append(run_config)
    run_ids.append(run_id)
    run_params_list.append(run_params)
    run_dirs.append(run_dir)

# ------------------------------------------------------------
# ALLE Backtests auf einmal starten
# Erwartung: run_backtest akzeptiert Liste[BacktestRunConfig] und liefert Liste[results]
# Reihenfolge: results[i] gehört zu run_id = f"run{i}"
# ------------------------------------------------------------
results = run_backtest(run_configs)

# ------------------------------------------------------------
# Metriken extrahieren & pro-Run speichern
# ------------------------------------------------------------
all_metrics = []
for result, run_id, run_params, run_dir in zip(results, run_ids, run_params_list, run_dirs):
    metrics = extract_metrics(result, run_params, run_id)
    pd.DataFrame([metrics]).to_csv(run_dir / "performance_metrics.csv", index=False)
    all_metrics.append(metrics)

# ------------------------------------------------------------
# Gesamtübersicht speichern
# ------------------------------------------------------------
df_all = pd.DataFrame(all_metrics)
file_path = results_dir / "all_backtest_results.csv"
df_all.to_csv(file_path, index=False)
add_trade_metrics(run_ids, results_dir, file_path, all_instrument_ids)
print("Finished Backtest runs. Results saved to:", results_dir)

if load_qs_flag:
    load_qs(run_dirs, run_ids, benchmark_symbol=bench_qs, open_browser=True)

if visualize:
    dash = launch_dashbaord()
    dash.run(debug=True, host="127.0.0.1", port=8050, use_reloader=False)
