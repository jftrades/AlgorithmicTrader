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

# --- Konfigurationen ---
# Diese Strings müssen exakt zu dem passen, was der Transformer geschrieben hat
# und was die Strategie erwartet.
# Der Transformer schreibt jetzt für "...-EXTERNAL" aufgrund des letzten Fehlers.
instrument_id_str = "BTCUSDT.BINANCE"
bar_type_str_for_configs = "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL"

print(f"INFO: Backtest: Angeforderte InstrumentId: '{instrument_id_str}'")
print(f"INFO: Backtest: Angeforderter BarType: '{bar_type_str_for_configs}'")

# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar", # Traditioneller Pfad, der für Deserialisierung funktionierte
    catalog_path="./DATA_STORAGE/data_catalog_wrangled",
    bar_types=[bar_type_str_for_configs],
    instrument_ids=[instrument_id_str],
)

# VenueConfig
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING", account_type="CASH",
    starting_balances=[Money(Decimal("5000"), USDT), Money(Decimal("0.1"), BTC)],
)

# StrategyConfig (Importable)
strategy_config = ImportableStrategyConfig(
    strategy_path="nautilus_trader.examples.strategies.ema_cross_twap:EMACrossTWAP",
    config_path="nautilus_trader.examples.strategies.ema_cross_twap:EMACrossTWAPConfig",
    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": "0.10", "fast_ema_period": 10, "slow_ema_period": 20,
        "twap_horizon_secs": 10.0, "twap_interval_secs": 2.5,
    }
)

# EngineConfig
engine_config = BacktestEngineConfig(strategies=[strategy_config])

# RunConfig
run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config)

# Launch Node
try:
    node = BacktestNode(configs=[run_config])
    print(f"INFO: Backtest: Starte Backtest-Node...")
    node.run()
except Exception as e:
    print(f"FATAL: Backtest: Ein Fehler ist im Backtest-Node aufgetreten: {e}")
    import traceback
    traceback.print_exc()
else:
    print(f"INFO: Backtest: Backtest-Node erfolgreich beendet.") 
    