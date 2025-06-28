# der Unterschied zu FVG_simple_strategy und FVG_simple_execution ist:
# in FVG Strategie probieren wir mal mit Bedingungen, Fees, RiskManagement etc rum um 
# das zukünftig for weitere Strategien schon mal gemacht zu haben einfach

# Standard Library Importe
import sys
import time
from pathlib import Path
from decimal import Decimal

# Nautilus Kern Importe
from nautilus_trader.core.nautilus_pyo3 import InstrumentId, Symbol, Venue
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.backtest.config import (BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig)
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.persistence.catalog import ParquetDataCatalog

# Nautilus Strategie spezifische Importe
from nautilus_trader.trading.config import ImportableStrategyConfig

catalogPath = str(Path(__file__).resolve().parent.parent / "data" / "DATA_STORAGE" / "data_catalog_wrangled")
catalog = ParquetDataCatalog(catalogPath)

# Hier die gleichen Parameter wie aus strategy aber halt anpassen
symbol = Symbol("BTCUSDT-PERP")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT-PERP.BINANCE"
bar_type_str_for_configs = "BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"
trade_size = Decimal("0.01") # Wird von der Strategie ignoriert, da dynamisches Risk-Management!
#...
close_positions_on_stop = True

# Strategien-Ordner liegt parallel zu AlgorithmicTrader (catalogPath ja nach Daten anpassen)
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
    # optional: instrument_ids, filter_expr, etc.
)

# VenueConfig
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING",
    account_type="MARGIN",
    base_currency="USDT",
    starting_balances=["100000 USDT"],
    # Optional: base_currency, default_leverage, leverages, book_type, etc.
)

# StrategyConfig - IMMER anpassen!!
strategy_config = ImportableStrategyConfig(
    strategy_path="FVG_strategy:FVGStrategy",        
    config_path="FVG_strategy:FVGStrategyConfig",     
    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": str(trade_size),
        "close_positions_on_stop": close_positions_on_stop,
    }
)
 
# EngineConfig -> welche Strategien bei diesem Backtest laufen sollen
engine_config = BacktestEngineConfig(
    strategies=[strategy_config],
    # Optional: weitere Engine-Parameter (debug, load_cache, etc.)
)

# RunConfig -> hier wird data, venues und engine zusammengeführt
run_config = BacktestRunConfig(
    data=[data_config],
    venues=[venue_config],
    engine=engine_config,
    # Optional: start, end, etc.
)

# Backtest starten mit mit node.run()try
try:
    node = BacktestNode(configs=[run_config])
    print(f"INFO: Backtest: Starte Backtest-Node...")
    results = node.run()
except Exception as e:
    print(f"FATAL: Backtest: Ein Fehler ist im Backtest-Node aufgetreten: {e}")
    import traceback
    traceback.print_exc()

# Ergebnisse auswerten
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
    print("\nReturn Statistics:")
    for key, val in result.stats_returns.items():
        print(f"  {key.replace('_', ' ').title()}: {val:.4f}")
    print("=" * 60)

if results:
    print_backtest_summary(results[0])
else:
    print("No results to display.")

# === OPTIONAL: Platzhalter für weitere Auswertungen, Visualisierung, Export etc. ===
# z.B. Export als CSV, Plotten, weitere Metriken, etc.