# Standard Library Importe
import sys
import time
import pandas as pd
from pathlib import Path
from decimal import Decimal 


# === DELAYED IMPORTS für NautilusTrader v2.18 ===
# Workaround für circular import Problem

def get_nautilus_imports():
    """Delayed import function to avoid circular imports in v2.18"""
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, AccountId
    from nautilus_trader.model.data import BarType
    from nautilus_trader.model.objects import Money
    from nautilus_trader.model.currencies import USDT, BTC
    from nautilus_trader.trading.config import ImportableStrategyConfig
    from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
    from nautilus_trader.backtest.node import BacktestNode
    from nautilus_trader.backtest.results import BacktestResult
    
    return {
        'InstrumentId': InstrumentId,
        'Symbol': Symbol,
        'Venue': Venue,
        'AccountId': AccountId,
        'BarType': BarType,
        'Money': Money,
        'USDT': USDT,
        'BTC': BTC,
        'ImportableStrategyConfig': ImportableStrategyConfig,
        'BacktestDataConfig': BacktestDataConfig,
        'BacktestVenueConfig': BacktestVenueConfig,
        'BacktestEngineConfig': BacktestEngineConfig,
        'BacktestRunConfig': BacktestRunConfig,
        'BacktestNode': BacktestNode,
        'BacktestResult': BacktestResult
    }

# Import everything
nt = get_nautilus_imports()
InstrumentId = nt['InstrumentId']
Symbol = nt['Symbol'] 
Venue = nt['Venue']
AccountId = nt['AccountId']
BarType = nt['BarType']
Money = nt['Money']
USDT = nt['USDT']
BTC = nt['BTC']
ImportableStrategyConfig = nt['ImportableStrategyConfig']
BacktestDataConfig = nt['BacktestDataConfig']
BacktestVenueConfig = nt['BacktestVenueConfig']
BacktestEngineConfig = nt['BacktestEngineConfig']
BacktestRunConfig = nt['BacktestRunConfig']
BacktestNode = nt['BacktestNode']
BacktestResult = nt['BacktestResult']

################
import sys
from pathlib import Path

# Pfad zum visualizing-Ordner hinzufügen
VIS_PATH = Path(__file__).resolve().parent.parent / "data" / "visualizing"
if str(VIS_PATH) not in sys.path:
    sys.path.insert(0, str(VIS_PATH))

from dashboard import TradingDashboard
###################

# === REST DES CODES BLEIBT GLEICH ===

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
    data_cls="nautilus_trader.model.data:Bar",
    catalog_path=catalogPath,
    bar_types=[bar_type_str_for_configs]
)


# VenueConfig - CHANGED TO CASH for automatic PnL balance updates
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING", 
    account_type="CASH",  # FIXED: CASH automatically updates balance with realized PnL
    starting_balances=["100000 USDT"]
)


# StrategyConfig
strategy_config = ImportableStrategyConfig(
    strategy_path = "RSI_simple_strategy:RSISimpleStrategy",
    config_path = "RSI_simple_strategy:RSISimpleStrategyConfig",

    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": "0.5",
        "rsi_period": 14,
        "rsi_overbought": 0.8, 
        "rsi_oversold": 0.2,
        "close_positions_on_stop": True
    }
)


# EngineConfig
engine_config = BacktestEngineConfig(strategies=[strategy_config])


# RunConfig
run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)


# Launch Node
try:
    node = BacktestNode(configs=[run_config])
    print(f"INFO: Backtest: Starte Backtest-Node...")
    results = node.run()
except Exception as e:
    print(f"FATAL: Backtest: Ein Fehler ist im Backtest-Node aufgetreten: {e}")
    import traceback
    traceback.print_exc()

# Rest des Codes bleibt gleich...
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
    print("✅ Backtest completed successfully!")
else:
    print("❌ No results to display.")

print("INFO: Starting Dashboard...")
time.sleep(1)

try:
    visualizer = TradingDashboard()
    visualizer.collect_results(results)
    visualizer.load_data_from_csv()
    visualizer.visualize(visualize_after_backtest=True)
except Exception as e:
    print(f"Dashboard error: {e}")
