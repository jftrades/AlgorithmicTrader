import os
import yaml
import asyncio
from pathlib import Path
from nautilus_trader.live.node import TradingNode
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.config import LoggingConfig, CacheConfig, MessageBusConfig
from nautilus_trader.config import DataEngineConfig, RiskEngineConfig, ExecEngineConfig
from nautilus_trader.config import LiveDataClientConfig, LiveExecClientConfig
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.model.enums import LogLevel, OmsType, AccountType


class LiveTrader:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.node = None

    def _load_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _setup_environment_variables(self):
        required_vars = ['BINANCE_TESTNET_API_KEY', 'BINANCE_TESTNET_API_SECRET']
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            raise EnvironmentError(f"Missing required environment variables: {missing_vars}")

    def _create_trading_node_config(self) -> TradingNodeConfig:
        config = self.config
        
        trader_id = TraderId(config["trader_id"])
        instance_id = config["instance_id"]
        
        log_level = getattr(LogLevel, config.get("log_level", "INFO"))
        
        logging_config = LoggingConfig(
            log_level=log_level,
            log_level_file=log_level,
            log_file_format="json"
        )
        
        cache_config = CacheConfig(
            database=config.get("cache", {}).get("type", "memory")
        )
        
        message_bus_config = MessageBusConfig(
            database=config.get("message_bus", {}).get("database", "memory"),
            encoding=config.get("message_bus", {}).get("encoding", "msgpack"),
            timestamps_as_iso8601=config.get("message_bus", {}).get("timestamps_as_iso8601", True)
        )
        
        data_engine_config = DataEngineConfig(
            validate_data_sequence=config.get("data_engine", {}).get("validate_data_sequence", True),
            debug=config.get("data_engine", {}).get("debug", False)
        )
        
        risk_engine_config = RiskEngineConfig(
            bypass=config.get("risk_engine", {}).get("bypass", False),
            max_order_rate=config.get("risk_engine", {}).get("max_order_rate", "100/00:00:01"),
            max_notional_per_order=config.get("risk_engine", {}).get("max_notional_per_order", {})
        )
        
        exec_engine_config = ExecEngineConfig(
            load_cache=config.get("exec_engine", {}).get("load_cache", True),
            save_cache=config.get("exec_engine", {}).get("save_cache", True)
        )
        
        data_clients = []
        for client_config in config.get("data_clients", []):
            if client_config["client_id"] == "BINANCE":
                data_client_config = LiveDataClientConfig(
                    client_id=client_config["client_id"],
                    factory=client_config["factory"],
                    config={
                        "api_key": os.getenv("BINANCE_TESTNET_API_KEY"),
                        "api_secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
                        "testnet": client_config["config"]["testnet"],
                        "us": client_config["config"]["us"],
                        "base_url_ws": client_config["config"]["base_url_ws"]
                    }
                )
                data_clients.append(data_client_config)
        
        exec_clients = []
        for client_config in config.get("exec_clients", []):
            if client_config["client_id"] == "BINANCE":
                exec_client_config = LiveExecClientConfig(
                    client_id=client_config["client_id"],
                    factory=client_config["factory"],
                    config={
                        "api_key": os.getenv("BINANCE_TESTNET_API_KEY"),
                        "api_secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
                        "testnet": client_config["config"]["testnet"],
                        "us": client_config["config"]["us"],
                        "base_url": client_config["config"]["base_url"]
                    }
                )
                exec_clients.append(exec_client_config)
        
        venues = []
        for venue_config in config.get("venues", []):
            venue = {
                "name": venue_config["name"],
                "oms_type": getattr(OmsType, venue_config["oms_type"]),
                "account_type": getattr(AccountType, venue_config["account_type"]),
                "base_currency": venue_config["base_currency"],
                "starting_balances": venue_config["starting_balances"]
            }
            venues.append(venue)
        
        strategies = []
        for instrument in config.get("instruments", []):
            strategy_config = ImportableStrategyConfig(
                strategy_path=config["strategy_path"],
                config_path=config["config_path"],
                config=self._build_strategy_config(config, instrument)
            )
            strategies.append(strategy_config)
        
        return TradingNodeConfig(
            trader_id=trader_id,
            instance_id=instance_id,
            logging=logging_config,
            cache=cache_config,
            message_bus=message_bus_config,
            data_engine=data_engine_config,
            risk_engine=risk_engine_config,
            exec_engine=exec_engine_config,
            data_clients=data_clients,
            exec_clients=exec_clients,
            strategies=strategies
        )

    def _build_strategy_config(self, config: dict, instrument: dict) -> dict:
        strategy_config = {
            "instruments": [instrument],
            "max_leverage": 10.0,
            "min_account_balance": 1000.0,
            "run_id": f"live_{config['instance_id']}",
            "time_after_listing_close": config.get("time_after_listing_close", 19),
            "only_execute_short": config.get("only_execute_short", True),
            "hold_profit_for_remaining_days": config.get("hold_profit_for_remaining_days", True),
            "close_positions_on_stop": True,
            "atr_period": 20,
            "sl_atr_multiple": 2.0
        }
        
        if "use_min_coin_filters" in config:
            strategy_config["use_min_coin_filters"] = config["use_min_coin_filters"]
        
        if "use_aroon_simple_trend_system" in config:
            strategy_config["use_aroon_simple_trend_system"] = config["use_aroon_simple_trend_system"]
        
        if "entry_scale_binance_metrics" in config:
            entry_config = config["entry_scale_binance_metrics"].copy()
            if isinstance(entry_config.get("rolling_window_bars_binance"), list):
                entry_config["rolling_window_bars_binance"] = entry_config["rolling_window_bars_binance"][0]
            strategy_config["entry_scale_binance_metrics"] = entry_config
        
        if "exit_scale_binance_metrics" in config:
            strategy_config["exit_scale_binance_metrics"] = config["exit_scale_binance_metrics"]
        
        if "five_day_scaling_filters" in config:
            filters_config = config["five_day_scaling_filters"].copy()
            if isinstance(filters_config.get("amount_change_scaled_values"), list):
                filters_config["amount_change_scaled_values"] = filters_config["amount_change_scaled_values"][0]
            strategy_config["five_day_scaling_filters"] = filters_config
        
        if "exit_l3_metrics_in_profit" in config:
            strategy_config["exit_l3_metrics_in_profit"] = config["exit_l3_metrics_in_profit"]
        
        if "log_growth_atr_risk" in config:
            strategy_config["log_growth_atr_risk"] = config["log_growth_atr_risk"]
        
        if "exp_growth_atr_risk" in config:
            strategy_config["exp_growth_atr_risk"] = config["exp_growth_atr_risk"]
        
        if "btc_performance_risk_scaling" in config:
            strategy_config["btc_performance_risk_scaling"] = config["btc_performance_risk_scaling"]
        
        return strategy_config

    async def run(self):
        self._setup_environment_variables()
        
        config = self._create_trading_node_config()
        
        self.node = TradingNode(config=config)
        
        try:
            await self.node.start()
            await self.node.run_async()
        except KeyboardInterrupt:
            print("Shutting down gracefully...")
        finally:
            if self.node:
                await self.node.stop()

    def stop(self):
        if self.node:
            asyncio.create_task(self.node.stop())


async def main():
    config_path = Path(__file__).parent.parent / "config" / "live_coin_listing_short.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    trader = LiveTrader(str(config_path))
    await trader.run()


if __name__ == "__main__":
    asyncio.run(main())