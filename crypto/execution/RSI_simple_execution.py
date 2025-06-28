
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

################
import sys
from pathlib import Path

# Pfad zum visualizing-Ordner hinzufügen
VIS_PATH = Path(__file__).resolve().parent.parent / "data" / "visualizing"
if str(VIS_PATH) not in sys.path:
    sys.path.insert(0, str(VIS_PATH))

from dashboard import TradingDashboard
###################

# Hier die gleichen Parameter wie aus strategy aber halt anpassen
symbol = Symbol("BTCUSDT")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT.BINANCE"
bar_type_str_for_configs = "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL"
trade_size = Decimal("0.5")
rsi_period = 14
rsi_overbought = 0.8
rsi_oversold = 0.2
close_positions_on_stop = True

start_date = "2024-10-01T00:00:00Z"
end_date = "2024-10-31T00:00:00Z"


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
        "trade_size": "0.5", # Trade Size in BTC
        #hier kommen jetzt die Strategie spezifischen Parameter
        "rsi_period": 14,
        "rsi_overbought": 0.8, 
        "rsi_oversold": 0.2,
        "close_positions_on_stop": True # Positionen werden beim Stop der Strategie geschlossen

    }
)


# EngineConfig -> welche Strategien bei diesem Backtest laufen sollen
engine_config = BacktestEngineConfig(strategies=[strategy_config])


# RunConfig -> hier wird data, venues und engine zusammengeführt
run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)



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

    time.sleep(1)


visualizer = TradingDashboard()
visualizer.collect_results(results)
visualizer.load_data_from_csv()

if visualizer.bars_df is not None:
    print(f"  - Bars geladen: {len(visualizer.bars_df)} Einträge")
else:
    print("  - Keine Bars gefunden!")

if visualizer.trades_df is not None:
    print(f"  - Trades geladen: {len(visualizer.trades_df)} Einträge")
else:
    print("  - Keine Trades gefunden!")

print(f"  - Indikatoren geladen: {len(visualizer.indicators_df)} Indikatoren")
print(f"  - Metriken geladen: {len(visualizer.metrics) if visualizer.metrics else 0} Metriken")
print("INFO: Starte Dashboard...")
visualizer.visualize(visualize_after_backtest=True)