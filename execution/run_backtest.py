import itertools
import pandas as pd
import uuid
from pathlib import Path
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from tools.help_funcs.help_funcs_execution import (_clear_directory, run_backtest, extract_metrics, load_qs, add_trade_metrics, build_data_configs)
from tools.help_funcs.yaml_loader import load_and_split_params, set_nested_parameter
import shutil
import yaml
import copy
from glob import glob
import os
import webbrowser
from core.visualizing.dashboard.main import launch_dashbaord

#STRAT PARAMETER

yaml_name = "short_tha_bich.yaml"

yaml_path = str(Path(__file__).resolve().parents[1] / "config" / yaml_name)
params, param_grid, keys, values, static_params, all_instrument_ids, all_bar_types, data_sources_normalized = load_and_split_params(yaml_path)

strategy_path = params["strategy_path"]
config_path = params["config_path"]
start_date = params["start_date"]
end_date = params["end_date"]
venue = params["venue"]
visualize = params.get("visualize", True)
load_qs_flag = params.get("load_qs", False)  # renamed to avoid clash with function
bench_qs = params.get("qs_bench")

catalog_path = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

# Datenquellen aus YAML bauen (fallback auf Standard-Bar wenn nicht angegeben)
data_configs = build_data_configs(
    data_sources_normalized=data_sources_normalized,
    all_instrument_ids=all_instrument_ids,
    all_bar_types=all_bar_types,
    catalog_path=catalog_path,
)

from nautilus_trader.backtest.config import ImportableFillModelConfig

venue_config = BacktestVenueConfig(
    name=str(venue),
    oms_type=params.get("oms_type", "NETTING"),
    account_type=params.get("account_type", "MARGIN"),
    base_currency=params.get("base_currency", "USDT"),
    starting_balances=[params.get("starting_account_balance", "100000 USDT")],
    bar_adaptive_high_low_ordering=True,
)

results_dir = Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "results"
results_dir.mkdir(parents=True, exist_ok=True)
_clear_directory(results_dir)

run_configs = []
run_ids = []
run_params_list = []
run_dirs = []

for i, combination in enumerate(itertools.product(*values)):
    run_id = f"run{i}"
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_params = dict(zip(keys, combination))
    config_params = copy.deepcopy(static_params)
    
    for param_key, param_value in run_params.items():
        if "." in param_key:
            set_nested_parameter(config_params, param_key, param_value)
        else:
            config_params[param_key] = param_value
    
    config_params["run_id"] = run_id

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

    run_config_dict = copy.deepcopy(params)
    run_config_dict.update(run_params)
    run_config_dict.update(static_params)
    run_config_dict["run_id"] = run_id
    with open(run_dir / "run_config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(run_config_dict, f, allow_unicode=True, sort_keys=False)

    run_configs.append(run_config)
    run_ids.append(run_id)
    run_params_list.append(run_params)
    run_dirs.append(run_dir)

results = run_backtest(run_configs)

all_metrics = []
for result, run_id, run_params, run_dir in zip(results, run_ids, run_params_list, run_dirs):
    metrics = extract_metrics(result, run_params, run_id)
    pd.DataFrame([metrics]).to_csv(run_dir / "performance_metrics.csv", index=False)
    all_metrics.append(metrics)

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
