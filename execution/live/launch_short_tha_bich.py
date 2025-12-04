import os
import time
import requests
import pandas as pd
import threading
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

from nautilus_trader.adapters.bybit import BYBIT, BybitDataClientConfig, BybitExecClientConfig
from nautilus_trader.adapters.bybit import BybitLiveDataClientFactory, BybitLiveExecClientFactory, BybitProductType
from nautilus_trader.config import InstrumentProviderConfig, LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.live.config import LiveRiskEngineConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId, TraderId
from nautilus_trader.portfolio.config import PortfolioConfig
from strategies.short_tha_bich_strat import ShortThaBitchStrat, ShortThaBitchStratConfig

load_dotenv()


class ShortThaBitchLiveTrader:
    def __init__(
        self,
        check_interval: int = 300,
        max_coins: int = 50,
        days_back: int = 30,
        use_testnet: bool = True,
        use_demo: bool = False,
    ):
        self.check_interval = check_interval
        self.max_coins = max_coins
        self.days_back = days_back
        self.use_testnet = use_testnet
        self.use_demo = use_demo

        self.csv_path = (
            Path(__file__).parent.parent.parent
            / "data"
            / "DATA_STORAGE"
            / "project_future_scraper"
            / "bybit_live_linear_perpetual_futures.csv"
        )
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        self._validate_api_keys()
        self.known_symbols = self._initialize_known_symbols()

        mode = "TESTNET" if use_testnet else ("DEMO" if use_demo else "LIVE")
        print(f"ShortThaBitch Live | Mode: {mode} | Interval: {check_interval}s | Max: {max_coins} | Days: {days_back}")

    def _validate_api_keys(self):
        if self.use_testnet:
            api_key = os.getenv("BYBIT_TESTNET_API_KEY")
            api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")
            key_type = "TESTNET"
        elif self.use_demo:
            api_key = os.getenv("BYBIT_DEMO_API_KEY")
            api_secret = os.getenv("BYBIT_DEMO_API_SECRET")
            key_type = "DEMO"
        else:
            api_key = os.getenv("BYBIT_API_KEY")
            api_secret = os.getenv("BYBIT_API_SECRET")
            key_type = "LIVE"

        if not api_key or not api_secret:
            raise ValueError(f"BYBIT_{key_type}_API_KEY and BYBIT_{key_type}_API_SECRET required in .env")

    def _initialize_known_symbols(self):
        current_perpetuals = self._get_bybit_perpetuals()

        if not self.csv_path.exists() and current_perpetuals:
            self._create_initial_csv(current_perpetuals)

        if current_perpetuals:
            return {p["symbol"] for p in current_perpetuals}
        return set()

    def _create_initial_csv(self, perpetuals):
        df = pd.DataFrame(perpetuals)
        df = df.rename(columns={"launchTime": "onboardDate"})

        df["onboardDate"] = df["onboardDate"].apply(
            lambda x: datetime.fromtimestamp(int(x) / 1000) if int(x) > 0 else datetime.now()
        )

        cutoff_date = datetime.now() - timedelta(days=self.days_back)
        df = df[df["onboardDate"] >= cutoff_date]

        df["onboardDate"] = df["onboardDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
        df = df.sort_values("onboardDate", ascending=False)
        df.to_csv(self.csv_path, index=False)
        print(f"Created initial CSV with {len(df)} instruments from last {self.days_back} days")

    def _get_bybit_perpetuals(self):
        try:
            resp = requests.get(
                "https://api.bybit.com/v5/market/instruments-info",
                params={"category": "linear", "status": "Trading", "limit": 1000},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data["retCode"] != 0:
                return []

            perpetuals = []
            for inst in data["result"]["list"]:
                if inst["symbol"].endswith("USDT") and inst["contractType"] == "LinearPerpetual":
                    perpetuals.append(
                        {
                            "symbol": inst["symbol"],
                            "launchTime": inst.get("launchTime", "0"),
                            "status": inst.get("status", "Trading"),
                        }
                    )
            return perpetuals
        except Exception as e:
            print(f"Error fetching perpetuals: {e}")
            return []

    def _detect_new_listings(self):
        current_perpetuals = self._get_bybit_perpetuals()
        if not current_perpetuals:
            return []

        current_symbols = {p["symbol"] for p in current_perpetuals}
        new_symbols = current_symbols - self.known_symbols

        if not new_symbols:
            return []

        new_listings = []
        for perp in current_perpetuals:
            if perp["symbol"] in new_symbols:
                launch_ts = int(perp["launchTime"])
                onboard_date = datetime.fromtimestamp(launch_ts / 1000) if launch_ts > 0 else datetime.now()
                new_listings.append(
                    {
                        "symbol": perp["symbol"],
                        "onboardDate": onboard_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": perp["status"],
                    }
                )

        if new_listings:
            self._update_csv(new_listings)
            self.known_symbols.update(new_symbols)
            print(f"NEW LISTINGS: {', '.join([listing['symbol'] for listing in new_listings])}")

        return new_listings

    def _update_csv(self, new_listings):
        new_df = pd.DataFrame(new_listings)

        if self.csv_path.exists():
            existing_df = pd.read_csv(self.csv_path)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        combined_df["onboardDate"] = pd.to_datetime(combined_df["onboardDate"])

        cutoff_date = datetime.now() - timedelta(days=50)
        combined_df = combined_df[combined_df["onboardDate"] >= cutoff_date]

        combined_df = combined_df.sort_values("onboardDate", ascending=False)
        combined_df["onboardDate"] = combined_df["onboardDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
        combined_df.to_csv(self.csv_path, index=False)

    def _load_recent_listings(self):
        if not self.csv_path.exists():
            return []

        df = pd.read_csv(self.csv_path)
        df["onboardDate"] = pd.to_datetime(df["onboardDate"])

        cutoff_date = datetime.now() - timedelta(days=self.days_back)
        recent_df = df[df["onboardDate"] >= cutoff_date]
        recent_df = recent_df.sort_values("onboardDate", ascending=False).head(self.max_coins)

        instruments = []
        
        instruments.append(
            {
                "instrument_id": "BTCUSDT-LINEAR.BYBIT",
                "bar_types": ["BTCUSDT-LINEAR.BYBIT-15-MINUTE-LAST-EXTERNAL"],
                "trade_size_usdt": "0",
            }
        )
        
        for _, row in recent_df.iterrows():
            symbol = row["symbol"]
            instruments.append(
                {
                    "instrument_id": f"{symbol}-LINEAR.BYBIT",
                    "bar_types": [f"{symbol}-LINEAR.BYBIT-15-MINUTE-LAST-EXTERNAL"],
                    "trade_size_usdt": "150",
                }
            )

        return instruments

    def _build_strategy_config(self, instruments):
        return {
            "instruments": instruments,
            "min_account_balance": 1000,
            "run_id": "live_short_tha_bich",
            "sl_atr_multiple": 3.0,
            "atr_period": 30,
            "time_after_listing_close": 20,
            "log_growth_atr_risk": {
                "enabled": True,
                "atr_period": 30,
                "atr_multiple": 3.0,
                "risk_percent": 0.05,
            },
            "exp_growth_atr_risk": {
                "enabled": False,
                "atr_period": 14,
                "atr_multiple": 2.0,
                "risk_percent": 0.04,
            },
            "use_macd_simple_reversion_system": {
                "enabled": True,
                "macd_fast_period": 20,
                "macd_slow_period": 35,
                "macd_signal_period": 15,
            },
            "use_rsi_simple_reversion_system": {
                "enabled": False,
                "usage_method": "condition",
                "rsi_period": 15,
                "rsi_overbought": 0.55,
                "rsi_oversold": 0.45,
            },
            "atr_burst_entry": {
                "enabled": False,
                "atr_period_calc": 50,
                "tr_lb": 5,
                "atr_burst_threshold": 4,
                "waiting_bars_after_burst": 10,
            },
            "use_htf_ema_bias_filter": {
                "enabled": True,
                "ema_period": 150,
            },
            "use_macd_exit_system": {
                "enabled": True,
                "macd_fast_exit_period": 65,
                "macd_slow_exit_period": 100,
                "macd_signal_exit_period": 50,
            },
            "btc_regime_filter": {
                "enabled": True,
                "ema_period": 200,
                "only_short_below_ema": True,
            },
            "only_execute_short": True,
            "hold_profit_for_remaining_days": False,
            "close_positions_on_stop": True,
            "max_leverage": 1.0,
            "max_concurrent_positions": 50,
        }

    def _create_node(self, instruments):
        strategy_config_dict = self._build_strategy_config(instruments)

        log_growth = strategy_config_dict["log_growth_atr_risk"]
        htf_ema = strategy_config_dict["use_htf_ema_bias_filter"]
        macd_entry = strategy_config_dict["use_macd_simple_reversion_system"]
        macd_exit = strategy_config_dict["use_macd_exit_system"]

        max_lookback = max(
            log_growth["atr_period"],
            htf_ema["ema_period"],
            macd_entry["macd_slow_period"],
            macd_exit["macd_slow_exit_period"],
        )

        print(f"Max indicator lookback: {max_lookback} bars")

        reconciliation_ids = [InstrumentId.from_str(inst["instrument_id"]) for inst in instruments[:10]]

        config_node = TradingNodeConfig(
            trader_id=TraderId("SHORT-THA-BICH-LIVE"),
            logging=LoggingConfig(log_level="INFO", use_pyo3=True),
            exec_engine=LiveExecEngineConfig(
                reconciliation=True,
                reconciliation_lookback_mins=2880,
                reconciliation_instrument_ids=reconciliation_ids,
                open_check_interval_secs=5.0,
                graceful_shutdown_on_exception=True,
            ),
            risk_engine=LiveRiskEngineConfig(bypass=True),
            portfolio=PortfolioConfig(min_account_state_logging_interval_ms=1000),
            data_clients={
                BYBIT: BybitDataClientConfig(
                    api_key=None,
                    api_secret=None,
                    base_url_http=None,
                    instrument_provider=InstrumentProviderConfig(load_all=True),
                    product_types=[BybitProductType.LINEAR],
                    demo=self.use_demo,
                    testnet=self.use_testnet,
                    recv_window_ms=5000,
                ),
            },
            exec_clients={
                BYBIT: BybitExecClientConfig(
                    api_key=None,
                    api_secret=None,
                    base_url_http=None,
                    base_url_ws_private=None,
                    use_ws_trade_api=True,
                    instrument_provider=InstrumentProviderConfig(load_all=True),
                    product_types=[BybitProductType.LINEAR],
                    demo=self.use_demo,
                    testnet=self.use_testnet,
                    max_retries=3,
                    retry_delay_initial_ms=1000,
                    retry_delay_max_ms=10000,
                    recv_window_ms=5000,
                ),
            },
            timeout_connection=20.0,
            timeout_reconciliation=10.0,
            timeout_portfolio=10.0,
            timeout_disconnection=10.0,
            timeout_post_stop=5.0,
        )

        node = TradingNode(config=config_node)
        config = ShortThaBitchStratConfig(**strategy_config_dict)
        strategy = ShortThaBitchStrat(config=config)

        node.trader.add_strategy(strategy)
        node.add_data_client_factory(BYBIT, BybitLiveDataClientFactory)
        node.add_exec_client_factory(BYBIT, BybitLiveExecClientFactory)
        node.build()

        return node

    def _monitor_loop(self):
        while True:
            try:
                self._detect_new_listings()
                time.sleep(self.check_interval)
            except Exception as e:
                print(f"Monitor error: {e}")
                time.sleep(60)

    def run(self):
        instruments = self._load_recent_listings()

        if not instruments:
            print("No recent listings found, using default instrument")
            instruments = [
                {
                    "instrument_id": "ETHUSDT-LINEAR.BYBIT",
                    "bar_types": ["ETHUSDT-LINEAR.BYBIT-15-MINUTE-LAST-EXTERNAL"],
                    "trade_size_usdt": "150",
                }
            ]

        print(f"Starting with {len(instruments)} instruments")

        threading.Thread(target=self._monitor_loop, daemon=True).start()

        node = self._create_node(instruments)

        try:
            node.run()
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            node.dispose()


if __name__ == "__main__":
    trader = ShortThaBitchLiveTrader(
        check_interval=300,
        max_coins=50,
        days_back=30,
        use_testnet=True,
        use_demo=False,
    )
    trader.run()
