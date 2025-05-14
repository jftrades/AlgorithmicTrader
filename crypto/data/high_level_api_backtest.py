from nautilus_trader.backtest.node import BacktestNode, BacktestRunConfig
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.model.objects import Money, AccountBalance
from pathlib import Path
from decimal import Decimal
from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAPConfig
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.trading.config import ImportableStrategyConfig
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAPConfig

import pandas as pd

instrument_id = InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE"))

# Konfiguration der Datenquelle
data_config = BacktestDataConfig(
    data_cls = "nautilus_trader.model.data:Bar",
    catalog_path="DATA_STORAGE/data_catalog_wrangled/data",
    bar_types=[BarType.from_str("BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL")],
    instrument_ids=[instrument_id],
)

# Konfiguration des Handelsplatzes
venue_config = BacktestVenueConfig(
    name="BINANCE",
    account_type="CASH",
    starting_balances = [
        Money(Decimal("5000"), USDT),
        Money(Decimal("0.1"), BTC),
    ],
    oms_type="NETTING"

    )



from nautilus_trader.trading.config import ImportableStrategyConfig

strategy_importable = ImportableStrategyConfig(
    strategy_path="nautilus_trader.examples.strategies.ema_cross_twap:EMACrossTWAP",
    config_path="nautilus_trader.examples.strategies.ema_cross_twap:EMACrossTWAPConfig",
    config={
        "instrument_id": "BTCUSDT.BINANCE",
        "bar_type": "BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL",
        "trade_size": "0.10",
        "fast_ema_period": 10,
        "slow_ema_period": 20,
        "twap_horizon_secs": 10.0,
        "twap_interval_secs": 2.5
    }
)



engine_config = BacktestEngineConfig(
    strategies=[strategy_importable],
)

# Zusammenstellung der Backtest-Konfiguration
run_config = BacktestRunConfig(
    data=[data_config],
    venues=[venue_config],
    engine=engine_config,
)

# Initialisierung und Ausführung des Backtests
# Initialisierung und Ausführung des Backtests
node = BacktestNode(configs=[run_config])
node.run()

