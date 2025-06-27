
# Standard Library Importe
import sys
import time
from pathlib import Path
from decimal import Decimal 


# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.core.nautilus_pyo3 import InstrumentId, Symbol, Venue
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig,BacktestRunConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.results import BacktestResult


# Nautilus Strategie spezifische Importe
from nautilus_trader.trading.config import ImportableStrategyConfig


# Hier die gleichen Parameter wie aus strategy aber halt anpassen
symbol = Symbol("BTCUSDT")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT.BINANCE"
bar_type_str_for_configs = "BTCUSDT.BINANCE-5-MINUTE-LAST-EXTERNAL"
trade_size = Decimal("0.01")
rsi_period = 14
rsi_overbought = 0.7
rsi_oversold = 0.3
close_positions_on_stop = True


# Strategien-Ordner liegt parallel zu AlgorithmicTrader
STRATEGY_PATH = Path(__file__).resolve().parents[1] / "strategies"
if str(STRATEGY_PATH) not in sys.path:
    sys.path.insert(0, str(STRATEGY_PATH))

catalogPath = str(Path(__file__).resolve().parent.parent / "data" / "DATA_STORAGE" / "data_catalog_wrangled")


# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar", # Traditioneller Pfad, der für Deserialisierung funktionierte
    catalog_path=catalogPath,
    bar_types=[bar_type_str_for_configs]
)


# VenueConfig
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING", 
    account_type="CASH",
    starting_balances=["100000 USDT", "1 BTC"]
)


# StrategyConfig - IMMER anpassen!!
strategy_config = ImportableStrategyConfig(
    strategy_path = "RSI_simple_strategy:RSISimpleStrategy",
    config_path = "RSI_simple_strategy:RSISimpleStrategyConfig",

    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": "0.010", # Trade Size in BTC
        #hier kommen jetzt die Strategie spezifischen Parameter
        "rsi_period": 14,
        "rsi_overbought": 0.7, 
        "rsi_oversold": 0.3,
        "close_positions_on_stop": True # Positionen werden beim Stop der Strategie geschlossen

    }
)


# EngineConfig -> welche Strategien bei diesem Backtest laufen sollen
engine_config = BacktestEngineConfig(strategies=[strategy_config])


# RunConfig -> hier wird data, venues und engine zusammengeführt
run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config)


# Launch Node #-> startet den eigentlichen Backtest mit node.run()try:
try:
    node = BacktestNode(configs=[run_config])
    print(f"INFO: Backtest: Starte Backtest-Node...")
    results = node.run()
except Exception as e:
    print(f"FATAL: Backtest: Ein Fehler ist im Backtest-Node aufgetreten: {e}")
    import traceback
    traceback.print_exc()

# Ergebnisse auswerten:
def print_backtest_summary(result: BacktestResult):
    print("=" * 60)
    print(f"Backtest Run-ID: {result.run_id}")
    print(f"Zeitraum: {result.backtest_start} bis {result.backtest_end}")
    print(f"Dauer (real): {result.elapsed_time:.2f}s")
    print(f"Iterationen: {result.iterations}")
    print(f"Events: {result.total_events}, Orders: {result.total_orders}, Positionen: {result.total_positions}")
    print("=" * 60)
    print("Performance (PnL pro Währung):")
    for currency, metrics in result.stats_pnls.items():
        print(f"\n🔸 {currency}")
        for key, val in metrics.items():
            print(f"  {key.replace('_', ' ').title()}: {val:.4f}")
    print("\n Return Statistics:")
    for key, val in result.stats_returns.items():
        print(f"  {key.replace('_', ' ').title()}: {val:.4f}")
    print("=" * 60)

if results:
    print_backtest_summary(results[0])
else:
    print("No results to display.")