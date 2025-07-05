# Standard Library Importe
import sys
from pathlib import Path
from decimal import Decimal

# Nautilus Kern Importe
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, AccountId
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.backtest.config import (BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig)
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.persistence.catalog import ParquetDataCatalog

# Nautilus Strategie spezifische Importe
from nautilus_trader.trading.config import ImportableStrategyConfig

# Execution Helper Funktionen
from help_funcs_exe import run_backtest_and_visualize, setup_visualizer

# Pre-Visualizer Aktivierung
TradingDashboard = setup_visualizer()  # ← () ausführen, nicht nur zuweisen!

catalogPath = str(Path(__file__).resolve().parent.parent / "data" / "DATA_STORAGE" / "data_catalog_wrangled")
catalog = ParquetDataCatalog(catalogPath)

# Parameter - anpassen für deine Strategie
symbol = Symbol("BTCUSDT-PERP")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT-PERP.BINANCE"
bar_type_str_for_configs = "BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"
trade_size = Decimal("0.01")
start_date = "2024-10-01T00:00:00Z"
end_date = "2024-10-31T00:00:00Z"
close_positions_on_stop = True

# Strategien-Ordner hinzufügen (catalogPath nach Daten anpassen)
STRATEGY_PATH = Path(__file__).resolve().parents[1] / "strategies"
if str(STRATEGY_PATH) not in sys.path:
    sys.path.insert(0, str(STRATEGY_PATH))

# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar",
    catalog_path=catalogPath,
    bar_types=[bar_type_str_for_configs],
    start_time="2021-01-01",
    end_time="2021-03-01",
    # Optional: start_time, end_time, instrument_ids, filter_expr, etc.
)

# VenueConfig - MARGIN für Futures/Crypto Trading
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING",
    account_type="MARGIN",  # MARGIN für Futures/Crypto mit Hebel
    base_currency="USDT",
    starting_balances=["100000 USDT"],  # Nur USDT für MARGIN Account
    # Optional: base_currency, default_leverage, leverages, book_type, etc.
)

# StrategyConfig - ANPASSEN für deine Strategie!
strategy_config = ImportableStrategyConfig(
    strategy_path="Name_Der_Strategy:NameDerStrategy",  # <--- ANPASSEN!
    config_path="Name_Der_Strategy:NameDerStrategyConfig",  # <--- ANPASSEN!
    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": str(trade_size),
        #...
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