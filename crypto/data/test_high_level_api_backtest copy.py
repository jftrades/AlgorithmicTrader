from pathlib import Path
from decimal import Decimal

from nautilus_trader.backtest.node import BacktestNode, BacktestRunConfig
from nautilus_trader.backtest.config import (
    BacktestDataConfig,
    BacktestVenueConfig,
    BacktestEngineConfig,
)
from nautilus_trader.trading.config import ImportableStrategyConfig
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.core.datetime import dt_to_unix_nanos
import pandas as pd

# === Instrument & BarType ===
instrument_id = InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE"))
bar_type = BarType.from_str("BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL")

start = dt_to_unix_nanos(pd.Timestamp("2024-04-05", tz="UTC"))
end = dt_to_unix_nanos(pd.Timestamp("2024-04-10", tz="UTC"))

# === DataConfig ===
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar",
    catalog_path="./DATA_STORAGE/data_catalog_wrangled",
    bar_types=[bar_type],
    instrument_id=instrument_id,
    #start_time=start,
    #end_time=end,
)

# === VenueConfig ===
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING",           # oder "HEDGING" wenn du Hedging brauchst
    account_type="CASH",
    starting_balances=[
        Money(Decimal("5000"), USDT),
        Money(Decimal("0.1"), BTC),
    ],
)

# === StrategyConfig (Importable) ===
strategy_config = ImportableStrategyConfig(
    strategy_path="nautilus_trader.examples.strategies.ema_cross_twap:EMACrossTWAP",
    config_path="nautilus_trader.examples.strategies.ema_cross_twap:EMACrossTWAPConfig",
    config={
        "instrument_id": "BTCUSDT.BINANCE",
        "bar_type": "BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL",
        "trade_size": "0.10",
        "fast_ema_period": 10,
        "slow_ema_period": 20,
        "twap_horizon_secs": 10.0,
        "twap_interval_secs": 2.5,
    }
)

# === EngineConfig ===
engine_config = BacktestEngineConfig(
    strategies=[strategy_config],
)

# === RunConfig ===
run_config = BacktestRunConfig(
    data=[data_config],
    venues=[venue_config],
    engine=engine_config,
)

# === Launch Node ===
node = BacktestNode(configs=[run_config])
node.run()
