# In high_level_api_backtest.py (Bereinigte Version)

from pathlib import Path
from decimal import Decimal

# KERN IMPORTE
from nautilus_trader.core.nautilus_pyo3 import InstrumentId, Symbol, Venue
# Bar, BarType etc. werden hier nicht direkt für Objekt-Erstellung benötigt,
# da wir Strings in Configs verwenden und data_cls den Typ vorgibt.
from nautilus_trader.backtest.node import BacktestNode, BacktestRunConfig
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT, BTC
import time
from nautilus_trader.backtest.results import BacktestResult
import sys

from core.visualizing.dashboard import TradingDashboard

# --- Konfigurationen ---
# Diese Strings müssen exakt zu dem passen, was der Transformer geschrieben hat
# und was die Strategie erwartet.
# Der Transformer schreibt jetzt für "...-EXTERNAL" aufgrund des letzten Fehlers.
instrument_id_str = "BTCUSDT-PERP.BINANCE"
bar_type_str_for_configs = "BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"

start_date = "2024-10-01T00:00:00Z"
end_date = "2024-10-31T00:00:00Z"

print(f"INFO: Backtest: Angeforderte InstrumentId: '{instrument_id_str}'")
print(f"INFO: Backtest: Angeforderter BarType: '{bar_type_str_for_configs}'")
catalogPath = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar", # Traditioneller Pfad, der für Deserialisierung funktionierte
    catalog_path=catalogPath,
    bar_types=[bar_type_str_for_configs],
    instrument_ids=[instrument_id_str],
)

# VenueConfig
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING", account_type="MARGIN",
    starting_balances=["100000 USDT"]
)

# StrategyConfig (Importable)
strategy_config = ImportableStrategyConfig(
    strategy_path = "strategies.ema_cross_twap:EMACrossTWAP",
    config_path = "strategies.ema_cross_twap:EMACrossTWAPConfig",

    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": "0.010", "fast_ema_period": 10, "slow_ema_period": 20
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

#### das ist nochmal eine möglichkeit die metrics zu printen.. Wird aber terilweise auch autoamtisch von der backtest node gemacht.
time.sleep(5)

print(f"FINISHED: Backtest: Starte Backtest-Node...")

def print_backtest_summary(result: BacktestResult):
    print("=" * 60)
    print(f"Backtest Run-ID: {result.run_id}")
    print(f"Zeitraum: {result.backtest_start} bis {result.backtest_end}")
    print(f"Dauer (real): {result.elapsed_time:.2f}s")
    print(f"Iterationen: {result.iterations}")
    print(f"Events: {result.total_events}, Orders: {result.total_orders}, Positionen: {result.total_positions}")
    print("=" * 60)

    print("\ Performance (PnL pro Währung):")
    for currency, metrics in result.stats_pnls.items():
        print(f"\n🔸 {currency}")
        for key, val in metrics.items():
            print(f"  {key.replace('_', ' ').title()}: {val:.4f}")

    print("\n Return Statistics:")
    for key, val in result.stats_returns.items():
        print(f"  {key.replace('_', ' ').title()}: {val:.4f}")

    print("=" * 60)


print_backtest_summary(results[0])  # falls du mehrere BacktestResults hast
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