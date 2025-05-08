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

instrument_id = InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE"))

# Konfiguration der Datenquelle
data_config = BacktestDataConfig(
    data_cls="Bar",
    catalog_path=Path("DATA_STORAGE/data_catalog_wrangled/data/bar/BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL/part-0.parquet"),
    bar_types=[BarType.from_str("BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL")],
    instrument_ids=[instrument_id],
)

# Konfiguration des Handelsplatzes
venue_config = BacktestVenueConfig(
    name="BINANCE",
    account_type="spot",
    starting_balances = [
        Money(Decimal("5000"), USDT),
        Money(Decimal("0.1"), BTC),
    ])

# === Strategy Config
strategy_config = EMACrossTWAPConfig(
    instrument_id=instrument_id,
    bar_type=BarType.M_15,
    trade_size=Decimal("0.10"),
    fast_ema_period=10,
    slow_ema_period=20,
    twap_horizon_secs=10.0,
    twap_interval_secs=2.5,
)

engine_config = BacktestEngineConfig(
    strategies=[strategy_config],
)

# Zusammenstellung der Backtest-Konfiguration
run_config = BacktestRunConfig(
    data=[data_config],
    venues=[venue_config],
    strategy_configs=[strategy_config],
    engine=engine_config,
)

# Initialisierung und Ausführung des Backtests
node = BacktestNode()
node.run(run_config)
