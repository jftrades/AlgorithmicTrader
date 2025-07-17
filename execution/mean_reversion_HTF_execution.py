import os
import json
import itertools
import pandas as pd
import shutil
import glob
import uuid
from pathlib import Path
from tools.help_funcs.yaml_loader import load_params
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from tools.help_funcs.help_funcs_execution import run_backtest, extract_metrics

# Parameter laden
yaml_path = str(Path(__file__).resolve().parents[1] / "config" / "mean_reversion_HTF.yaml")
params = load_params(yaml_path)

param_grid = {
    "trade_size": params["trade_size"],
    "rsi_period": params["rsi_period"],
    "rsi_overbought": params["rsi_overbought"],
    "rsi_oversold": params["rsi_oversold"],
    "ttt_lookback": params["ttt_lookback"],
    "ttt_atr_mult": params["ttt_atr_mult"],
    "ttt_max_counter": params["ttt_max_counter"],
    "close_positions_on_stop": params["close_positions_on_stop"],
}
keys, values = zip(*param_grid.items())

start_date = "2008-01-01T00:00:00Z"
end_date = "2024-12-30T23:59:59Z"

# Parameter - anpassen für deine Strategie !!!!!!
symbol = Symbol(params["symbol"])
venue = Venue(params["venue"])
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = params["instrument_id"]
bar_type = params["bar_type"]
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
    name="ARCA",
    oms_type="NETTING",
    account_type="MARGIN", 
    base_currency="USD",
    starting_balances=["100000 USD"]
)

start_date = "2008-01-01T00:00:00Z"
end_date = "2024-12-30T23:59:59Z"

results_dir = Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "results"
results_dir.mkdir(parents=True, exist_ok=True)

all_results = []
for i, combination in enumerate(itertools.product(*values)):
    run_params = dict(zip(keys, combination))
    print(f"Run {i}: {run_params}")
    # StrategyConfig 
    strategy_config = ImportableStrategyConfig(
        strategy_path="strategies.mean_reversion_HTF_strategy:MeanReversionHTFStrategy",
        config_path="strategies.mean_reversion_HTF_strategy:MeanReversionHTFStrategyConfig",
        config={
            "instrument_id": instrument_id_str,
            "bar_type": bar_type,    
            "trade_size": run_params["trade_size"],
            "rsi_period": run_params["rsi_period"],
            "rsi_overbought": run_params["rsi_overbought"],
            "rsi_oversold": run_params["rsi_oversold"],
            "ttt_lookback": run_params["ttt_lookback"],
            "ttt_atr_mult": run_params["ttt_atr_mult"],
            "ttt_max_counter": run_params["ttt_max_counter"],
            "close_positions_on_stop": run_params["close_positions_on_stop"],
        }
    )

    # EnigneConfig
    engine_config = BacktestEngineConfig(strategies=[strategy_config])

    # RunConfig  
    run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)

    result = run_backtest(run_config)
    run_id = f"run_{i}_{uuid.uuid4().hex[:6]}"
    run_dir = Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "results" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    metrics = extract_metrics(result, run_params, run_id)
    all_results.append(metrics)

# Nach allen Runs:
df = pd.DataFrame(all_results)

# Optional: Sortierung nach Sharpe Ratio (absteigend)
# sort_by = "RET_Sharpe Ratio (252 days)"  # oder eine andere Spalte
# if sort_by in df.columns:
    # df = df.sort_values(by=sort_by, ascending=False)

df.to_csv(results_dir / "all_backtest_results.csv", index=False)
print(df)