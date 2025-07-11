# hier rein kommt dann die HTF mean reversion execution basierend auf:
# RSI, vllt VWAP und breakout oder so in der richtigen Zone - rumprobieren
# diese strat wird dann gehedged mit einer nur trendfollowing strategie
# Standard Library Importe
import sys
import time
import pandas as pd
from pathlib import Path
from decimal import Decimal

# Nautilus Kern Importe
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, AccountId
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.backtest.config import (BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig)
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.persistence.catalog import ParquetDataCatalog

# Nautilus Strategie spezifische Importe
from nautilus_trader.trading.config import ImportableStrategyConfig

# Execution Helper Funktionen
from tools.help_funcs.help_funcs_execution import run_backtest_and_visualize, setup_visualizer
from core.visualizing.dashboard import TradingDashboard

start_date = "2024-01-01T00:00:00Z"
end_date = "2024-01-03T23:59:59Z"


# Parameter - anpassen für deine Strategie !!!!!!
symbol = Symbol("ES.c.0")
venue = Venue("GLBX")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "ES.FUT.GLBX"
bar_type_1h = "ES.FUT.GLBX-1-HOUR-LAST-EXTERNAL"
bar_type_1d = "ES.FUT.GLBX-1-DAY-LAST-EXTERNAL"
start_date = "2024-01-01T00:00:00Z"
end_date = "2024-01-03T23:59:59Z"
catalog_path = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar",
    catalog_path=catalog_path,
    bar_types=[bar_type_1h, bar_type_1d]
)

# VenueConfig 
venue_config = BacktestVenueConfig(
    name="GLBX",
    oms_type="NETTING",
    account_type="MARGIN", 
    base_currency="USD",
    starting_balances=["100000 USD"]
)

# StrategyConfig 
strategy_config = ImportableStrategyConfig(
    strategy_path="strategies.mean_reversion_HTF_strategy:MeanReversionHTFStrategy",
    config_path="strategies.mean_reversion_HTF_strategy:MeanReversionHTFStrategyConfig",
    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_1h,
        "bar_type_1h": bar_type_1h,
        "bar_type_1d": bar_type_1d,
        "trade_size": "0.5",
        "rsi_period": 14,
        "rsi_overbought": 0.75,
        "rsi_oversold": 0.25,
        "close_positions_on_stop": True
    }
)
 
# EngineConfig
engine_config = BacktestEngineConfig(strategies=[strategy_config])

# RunConfig
run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)

# Backtest ausführen
results = run_backtest_and_visualize(run_config, TradingDashboard)
