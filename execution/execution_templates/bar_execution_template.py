# ================================================================================
# BAR EXECUTION TEMPLATE - Nautilus Trader
# Minimales Template für Bar-basierte Backtests mit Nautilus Trader
# ================================================================================
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


# Parameter - anpassen für deine Tick-Strategie
symbol = Symbol("BTCUSDT-PERP")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT-PERP.BINANCE"
bar_type_str_for_configs = "BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"
trade_size = Decimal("0.01")
tick_buffer_size = 1000
close_positions_on_stop = True

catalogPath = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar", # Traditioneller Pfad, der für Deserialisierung funktionierte
    catalog_path=catalogPath,
    bar_types=[bar_type_str_for_configs]
)

# Passe die IDs und Parameter für BTCUSDT Perpetual Futures an
symbol = Symbol("BTCUSDT-PERP")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT-PERP.BINANCE"

# VenueConfig - MARGIN für Futures/Crypto Trading
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING",
    account_type="MARGIN",  # MARGIN für Futures/Crypto mit Hebel
    base_currency="USDT",
    starting_balances=["100000 USDT"],  # Nur USDT für MARGIN Account
    # Optional: base_currency, default_leverage, leverages, book_type, etc.
)

# StrategyConfig - ANPASSEN für deine Tick-Strategie!
strategy_config = ImportableStrategyConfig(
    strategy_path="bar_strategy_template:BarStrategy",  # <--- ANPASSEN!
    config_path="bar_strategy_template:BarStrategyConfig",  # <--- ANPASSEN!
    config={
        "instrument_id": instrument_id_str,
        "trade_size": str(trade_size),
        "tick_buffer_size": tick_buffer_size,
        "close_positions_on_stop": close_positions_on_stop,
    }
)
 
# EngineConfig
engine_config = BacktestEngineConfig(
    strategies=[strategy_config],
    # Optional: weitere Engine-Parameter
)

# RunConfig
run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)

# Backtest ausführen mit vorab initialisiertem Dashboard
results = run_backtest_and_visualize(run_config, TradingDashboard)