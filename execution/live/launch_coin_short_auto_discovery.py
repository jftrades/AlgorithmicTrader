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
from nautilus_trader.trading.config import ImportableStrategyConfig
from strategies.coin_listing_short_strategy import CoinListingShortStrategy, CoinListingShortConfig

load_dotenv()

class AutoDiscoveryLiveTrader:
    def __init__(self, check_interval: int = 300, max_coins: int = 50, days_back: int = 30):
        self.check_interval = check_interval
        self.max_coins = max_coins
        self.days_back = days_back
        self.csv_path = Path(__file__).parent.parent.parent / "data" / "DATA_STORAGE" / "project_future_scraper" / "bybit_live_linear_perpetual_futures.csv"
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        api_key = os.getenv("BYBIT_TESTNET_API_KEY")
        api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")
        if not api_key or not api_secret:
            raise ValueError("BYBIT_TESTNET_API_KEY and BYBIT_TESTNET_API_SECRET required")
        
        self.known_symbols = self._initialize_known_symbols()
        print(f"Auto-Discovery Live | Interval: {check_interval}s | Max: {max_coins} | Days: {days_back}")
    
    def _initialize_known_symbols(self):
        current_perpetuals = self._get_bybit_perpetuals()
        
        if not self.csv_path.exists() and current_perpetuals:
            self._create_initial_csv(current_perpetuals)
        
        if current_perpetuals:
            return {p['symbol'] for p in current_perpetuals}
        return set()
    
    def _create_initial_csv(self, perpetuals):
        df = pd.DataFrame(perpetuals)
        df = df.rename(columns={'launchTime': 'onboardDate'})
        
        df['onboardDate'] = df['onboardDate'].apply(
            lambda x: datetime.fromtimestamp(int(x) / 1000) 
            if int(x) > 0 else datetime.now()
        )
        
        cutoff_date = datetime.now() - timedelta(days=self.days_back)
        df = df[df['onboardDate'] >= cutoff_date]
        
        df['onboardDate'] = df['onboardDate'].dt.strftime("%Y-%m-%d %H:%M:%S")
        df = df.sort_values('onboardDate', ascending=False)
        df.to_csv(self.csv_path, index=False)
        print(f"Created initial CSV with {len(df)} instruments from last {self.days_back} days")
    
    def _get_bybit_perpetuals(self):
        try:
            resp = requests.get(
                "https://api.bybit.com/v5/market/instruments-info",
                params={"category": "linear", "status": "Trading", "limit": 1000},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            if data['retCode'] != 0:
                return []
            
            perpetuals = []
            for inst in data['result']['list']:
                if inst['symbol'].endswith('USDT') and inst['contractType'] == 'LinearPerpetual':
                    perpetuals.append({
                        'symbol': inst['symbol'],
                        'launchTime': inst.get('launchTime', '0'),
                        'status': inst.get('status', 'Trading')
                    })
            return perpetuals
        except Exception:
            return []
    
    def _detect_new_listings(self):
        current_perpetuals = self._get_bybit_perpetuals()
        if not current_perpetuals:
            return []
        
        current_symbols = {p['symbol'] for p in current_perpetuals}
        new_symbols = current_symbols - self.known_symbols
        
        if not new_symbols:
            return []
        
        new_listings = []
        for perp in current_perpetuals:
            if perp['symbol'] in new_symbols:
                launch_ts = int(perp['launchTime'])
                onboard_date = datetime.fromtimestamp(launch_ts / 1000) if launch_ts > 0 else datetime.now()
                new_listings.append({
                    'symbol': perp['symbol'],
                    'onboardDate': onboard_date.strftime("%Y-%m-%d %H:%M:%S"),
                    'status': perp['status']
                })
        
        if new_listings:
            self._update_csv(new_listings)
            self.known_symbols.update(new_symbols)
            print(f"NEW: {', '.join([listing['symbol'] for listing in new_listings])}")
        
        return new_listings
    
    def _update_csv(self, new_listings):
        new_df = pd.DataFrame(new_listings)
        
        if self.csv_path.exists():
            existing_df = pd.read_csv(self.csv_path)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        
        combined_df['onboardDate'] = pd.to_datetime(combined_df['onboardDate'])
        
        cutoff_date = datetime.now() - timedelta(days=50)
        combined_df = combined_df[combined_df['onboardDate'] >= cutoff_date]
        
        combined_df = combined_df.sort_values('onboardDate', ascending=False)
        combined_df['onboardDate'] = combined_df['onboardDate'].dt.strftime("%Y-%m-%d %H:%M:%S")
        combined_df.to_csv(self.csv_path, index=False)
    
    def _load_recent_listings(self):
        if not self.csv_path.exists():
            return []
        
        df = pd.read_csv(self.csv_path)
        
        df['onboardDate'] = pd.to_datetime(df['onboardDate'])
        
        cutoff_date = datetime.now() - timedelta(days=self.days_back)
        recent_df = df[df['onboardDate'] >= cutoff_date]
        
        recent_df = recent_df.sort_values('onboardDate', ascending=False).head(self.max_coins)
        
        instruments = []
        for _, row in recent_df.iterrows():
            symbol = row['symbol']
            instruments.append({
                "instrument_id": f"{symbol}-LINEAR.BYBIT",
                "bar_types": [f"{symbol}-LINEAR.BYBIT-15-MINUTE-LAST-EXTERNAL"],
                "trade_size_usdt": "50"
            })
        
        return instruments
    
    def _create_node(self, instruments):
        strategy_config = ImportableStrategyConfig(
            strategy_path="strategies.coin_listing_short_strategy:CoinListingShortStrategy",
            config_path="strategies.coin_listing_short_strategy:CoinListingShortConfig",
            config={
                "instruments": instruments,
                "min_account_balance": 1000,
                "run_id": "live_auto_discovery",
                "sl_atr_multiple": 5.0,
                "atr_period": 50,
                "time_after_listing_close": 20,
                "log_growth_atr_risk": {"enabled": True, "atr_period": 50, "atr_multiple": 5.0, "risk_percent": 0.01},
                "exp_growth_atr_risk": {"enabled": False, "atr_period": 20, "atr_multiple": 2.0, "risk_percent": 0.04},
                "exp_fixed_trade_risk": {"enabled": False, "invest_percent": 0.05},
                "log_fixed_trade_risk": {"enabled": False, "investment_size": 50},
                "use_aroon_simple_trend_system": {"enabled": True, "aroon_period": 60, "aroon_osc_short_threshold": -40},
                "exit_scale_binance_metrics": {"enabled": True, "rolling_window_bars_binance": 2000, "upper_percentile_threshold_binance": 95, "lower_percentile_threshold_binance": 5},
                "entry_scale_binance_metrics": {"enabled": False, "rolling_window_bars_binance": 2000, "upper_percentile_threshold_binance": 95, "lower_percentile_threshold_binance": 5},
                "five_day_scaling_filters": {"enabled": False, "amount_change_scaled_values": 250, "oi_trade_threshold": 0.8, "oi_allow_entry_difference": 0.5},
                "exit_l3_metrics_in_profit": {"enabled": False, "exit_amount_change_scaled_values": 100, "exit_oi_threshold": -0.8, "exit_oi_allow_difference": 0.6, "only_check_thresholds_after_entry": True, "exit_signal_mode": "oi_only"},
                "use_close_ema": {"enabled": True, "exit_trend_ema_period": 80, "min_bars_over_ema": 28, "min_bars_under_ema": 28},
                "only_execute_short": True,
                "hold_profit_for_remaining_days": False,
                "close_positions_on_stop": True,
                "max_leverage": 2.0,
                "use_min_coin_filters": {"enabled": False, "min_price": 0.25, "min_24h_volume": 50000, "min_sum_open_interest_value": 1000000},
                "btc_performance_risk_scaling": {"enabled": False, "risk_scaling_method": "linear", "rolling_zscore": 200, "stop_executing_above_zscore": 2.8, "max_zscore": 4.0, "min_zscore": -4.0, "risk_multiplier_max_z_threshold": 0.4, "risk_multiplier_min_z_threshold": 2.0},
                "sol_performance_risk_scaling": {"enabled": False, "risk_scaling_method": "linear", "rolling_zscore": 200, "stop_executing_above_zscore": 2.8, "max_zscore": 4.0, "min_zscore": -4.0, "risk_multiplier_max_z_threshold": 0.4, "risk_multiplier_min_z_threshold": 2.0},
            }
        )
        
        # Calculate required historical bars dynamically from config
        atr_period = strategy_config.config["atr_period"]
        aroon_period = strategy_config.config["use_aroon_simple_trend_system"]["aroon_period"]
        exit_trend_ema_period = strategy_config.config["use_close_ema"]["exit_trend_ema_period"]
        max_lookback = max(atr_period, aroon_period, exit_trend_ema_period)
        
        print(f"Calculated lookback: ATR={atr_period}, Aroon={aroon_period}, EMA={exit_trend_ema_period}")
        print(f"Will fetch {max_lookback} historical 15-minute bars for strategy initialization")
        
        reconciliation_ids = [InstrumentId.from_str(inst["instrument_id"]) for inst in instruments[:10]]
        
        config_node = TradingNodeConfig(
            trader_id=TraderId("COIN-LISTING-AUTO"),
            logging=LoggingConfig(log_level="INFO", use_pyo3=True),
            exec_engine=LiveExecEngineConfig(
                reconciliation=True,
                reconciliation_lookback_mins=2880,
                reconciliation_instrument_ids=reconciliation_ids,
                open_check_interval_secs=5.0,
                graceful_shutdown_on_exception=True,
            ),
            risk_engine=LiveRiskEngineConfig(bypass=False),
            portfolio=PortfolioConfig(min_account_state_logging_interval_ms=1_000),
            data_clients={
                BYBIT: BybitDataClientConfig(
                    api_key=None,
                    api_secret=None,
                    base_url_http=None,
                    instrument_provider=InstrumentProviderConfig(load_all=True),
                    product_types=[BybitProductType.LINEAR],
                    demo=False,
                    testnet=True,
                    recv_window_ms=5_000,
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
                    demo=False,
                    testnet=True,
                    max_retries=3,
                    retry_delay_initial_ms=1_000,
                    retry_delay_max_ms=10_000,
                    recv_window_ms=5_000,
                ),
            },
            timeout_connection=20.0,
            timeout_reconciliation=10.0,
            timeout_portfolio=10.0,
            timeout_disconnection=10.0,
            timeout_post_stop=5.0,
        )
        
        node = TradingNode(config=config_node)
        config = CoinListingShortConfig(**strategy_config.config)
        strategy = CoinListingShortStrategy(config=config)
        
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
            instruments = [{"instrument_id": "ETHUSDT-LINEAR.BYBIT", "bar_types": ["ETHUSDT-LINEAR.BYBIT-15-MINUTE-LAST-EXTERNAL"], "trade_size_usdt": "50"}]
        
        threading.Thread(target=self._monitor_loop, daemon=True).start()
        
        node = self._create_node(instruments)
        
        try:
            node.run()
        except KeyboardInterrupt:
            pass
        finally:
            node.dispose()

if __name__ == "__main__":
    trader = AutoDiscoveryLiveTrader(check_interval=300, max_coins=50, days_back=30)
    trader.run()
