# hier rein kommt die execution Datei der ersten simplen RSI strategie nur mit tick-Daten.
# Standard Library Importe
import sys
from pathlib import Path
from decimal import Decimal

# Nautilus Kern Importe
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, AccountId
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.backtest.config import (BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig)
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.test_kit.providers import TestDataProvider
from nautilus_trader.persistence.loaders import CSVTickDataLoader

# Nautilus Strategie spezifische Importe
from nautilus_trader.trading.config import ImportableStrategyConfig

# Execution Helper Funktionen
from help_funcs_exe import run_backtest_and_visualize, setup_visualizer

# Pre-Visualizer Aktivierung
TradingDashboard = setup_visualizer()

# TICK-DATEN CATALOG PATH (Ihre lokalen Tick-Daten!)
# catalogPath = str(Path(__file__).resolve().parent.parent / "data" / "DATA_STORAGE" / "data_catalog_wrangled")
# catalog = ParquetDataCatalog(catalogPath)

start_date = "2024-01-01T00:00:00Z"
end_date = "2024-01-1T02:00:00Z"

# Parameter 
symbol = Symbol("BTCUSDT")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT-PERP.BINANCE"
trade_size = Decimal("0.01")
tick_buffer_size = 1000
rsi_period = 14
rsi_overbought = 0.8
rsi_oversold = 0.2
close_positions_on_stop = True

# Strategien-Ordner hinzufügen (catalogPath nach Daten anpassen)
STRATEGY_PATH = Path(__file__).resolve().parents[1] / "strategies"
if str(STRATEGY_PATH) not in sys.path:
    sys.path.insert(0, str(STRATEGY_PATH))

catalogPath = str(Path(__file__).resolve().parent.parent / "data" / "DATA_STORAGE" / "data_catalog_wrangled")



data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:TradeTick",
    instrument_id="BTCUSDT-PERP.BINANCE",
    catalog_path=catalogPath,
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
    account_type="MARGIN",
    base_currency="USDT",
    starting_balances=["100000 USDT"],
)

# StrategyConfig
strategy_config = ImportableStrategyConfig(
    strategy_path="RSI_tick_simple_strategy:RSITickSimpleStrategy",
    config_path="RSI_tick_simple_strategy:RSITickSimpleStrategyConfig",
    config={
        "instrument_id": instrument_id_str,
        "trade_size": str(trade_size),
        "tick_buffer_size": tick_buffer_size,
        "rsi_period": 14,
        "rsi_overbought": 0.8,
        "rsi_oversold": 0.2,
        "close_positions_on_stop": close_positions_on_stop,
    }
)

# EngineConfig
engine_config = BacktestEngineConfig(
    strategies=[strategy_config],
)


run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)

results = run_backtest_and_visualize(run_config, TradingDashboard)