#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  NautilusTrader - Binance Spot Testnet Live Node Example
#  Author: Nautech Systems Pty Ltd (adapted for local test use by Raphael)
#  License: GNU LGPL v3.0
# -------------------------------------------------------------------------------------------------

import os
from decimal import Decimal
from dotenv import load_dotenv

from nautilus_trader.adapters.binance import (
    BINANCE,
    BinanceAccountType,
    BinanceDataClientConfig,
    BinanceExecClientConfig,
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.config import (
    InstrumentProviderConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId, TraderId
from nautilus_trader.test_kit.strategies.tester_exec import ExecTester, ExecTesterConfig

# -------------------------------------------------------------------------------------------------
#  ENVIRONMENT SETUP
# -------------------------------------------------------------------------------------------------

# Load environment variables
load_dotenv()

# Get API credentials from .env
api_key = os.getenv("BINANCE_TESTNET_API_KEY")
api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")

if not api_key or not api_secret:
    raise ValueError("❌ Missing API credentials: set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET in .env")

# -------------------------------------------------------------------------------------------------
#  TRADING PARAMETERS
# -------------------------------------------------------------------------------------------------

symbol = "ETHUSDT"
instrument_id = InstrumentId.from_str(f"{symbol}.{BINANCE}")
order_qty = Decimal("0.01")

# Binance Spot Testnet Endpoints (✅ work in Germany)
HTTP_TESTNET = "https://testnet.binance.vision"
WS_TESTNET   = "wss://stream.testnet.binance.vision/ws"


# -------------------------------------------------------------------------------------------------
#  NODE CONFIGURATION
# -------------------------------------------------------------------------------------------------

config_node = TradingNodeConfig(
    trader_id=TraderId("TESTER-001"),
    logging=LoggingConfig(log_level="INFO"),
    exec_engine=LiveExecEngineConfig(
        reconciliation=True,
        reconciliation_lookback_mins=1440,
    ),
    data_clients={
        BINANCE: BinanceDataClientConfig(
            api_key=api_key,
            api_secret=api_secret,
            account_type=BinanceAccountType.SPOT,
            base_url_http=HTTP_TESTNET,
            base_url_ws=WS_TESTNET,
            us=False,
            testnet=True,
            instrument_provider=InstrumentProviderConfig(load_all=True),
        ),
    },
    exec_clients={
        BINANCE: BinanceExecClientConfig(
            api_key=api_key,
            api_secret=api_secret,
            account_type=BinanceAccountType.SPOT,
            base_url_http=HTTP_TESTNET,
            base_url_ws=WS_TESTNET,
            us=False,
            testnet=True,
            instrument_provider=InstrumentProviderConfig(load_all=True),
            max_retries=3,
            retry_delay_initial_ms=1_000,
            retry_delay_max_ms=10_000,
        ),
    },
    timeout_connection=30.0,
    timeout_reconciliation=10.0,
    timeout_portfolio=10.0,
    timeout_disconnection=10.0,
    timeout_post_stop=5.0,
)

# -------------------------------------------------------------------------------------------------
#  NODE + STRATEGY SETUP
# -------------------------------------------------------------------------------------------------

# Create trading node
node = TradingNode(config=config_node)

# Simple execution tester strategy
config_strat = ExecTesterConfig(
    instrument_id=instrument_id,
    external_order_claims=[instrument_id],
    order_qty=order_qty,
    open_position_on_start_qty=order_qty,
    use_post_only=True,
)

strategy = ExecTester(config=config_strat)
node.trader.add_strategy(strategy)

# Register Binance client factories
node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)

# Build node
node.build()

# -------------------------------------------------------------------------------------------------
#  RUN NODE
# -------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        node.run()
    finally:
        node.dispose()
