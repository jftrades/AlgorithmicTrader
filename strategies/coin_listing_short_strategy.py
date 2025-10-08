# strat for coin_listing_short.yaml
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List, Union
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.common.enums import LogColor
from pydantic import Field
from decimal import Decimal

from nautilus_trader.indicators.aroon import AroonOscillator
from nautilus_trader.indicators.atr import AverageTrueRange
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from nautilus_trader.model.data import DataType
from data.download.crypto_downloads.custom_class.metrics_data import MetricsData


class CoinListingShortConfig(StrategyConfig):
    instruments: List[dict]  
    min_account_balance: float
    run_id: str
    sl_atr_multiple: float = 2.0
    atr_period: int = 14
    time_after_listing_close: Union[int, List[float]] = Field(default=14)

    # Risk Management Configuration
    exp_growth_atr_risk: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "atr_period": 14,
            "atr_multiple": 2.0,
            "risk_percent": 0.04
        }
    )
    log_growth_atr_risk: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "atr_period": 14,
            "atr_multiple": 2.0,
            "risk_percent": 0.04
        }
    )
    exp_fixed_trade_risk: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "invest_percent": 0.05
        }
    )

    log_fixed_trade_risk: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "investment_size": 50
        }
    )

    btc_performance_risk_scaling: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "risk_scaling_method": "exponential", 
            "rolling_zscore": 200,
            "stop_executing_above_zscore": 4.0,
            "max_zscore": 3.0,
            "min_zscore": -3.0,
            "risk_multiplier_max_z_threshold": 0.2,
            "risk_multiplier_min_z_threshold": 3
        }
    )

    sol_performance_risk_scaling: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "risk_scaling_method": "linear", 
            "rolling_zscore": 500,
            "stop_executing_above_zscore": 2.8,
            "max_zscore": 4.0,
            "min_zscore": -4.0,
            "risk_multiplier_max_z_threshold": 0.2,
            "risk_multiplier_min_z_threshold": 4.0
        }
    )

    # Entry Methods Configuration
    use_min_coin_filters: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "min_price": 0.25,
            "min_24h_volume": 50000,
            "min_sum_open_interest_value": 1000000
        }
    )

    use_aroon_simple_trend_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "aroon_period": 14,
            "aroon_osc_short_threshold": -50
        }
    )

    # metrics scaling
    exit_scale_binance_metrics: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "rolling_window_bars_binance": 100,
            "upper_percentile_threshold_binance": 95,
            "lower_percentile_threshold_binance": 5
        }
    )

    entry_scale_binance_metrics: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "rolling_window_bars_binance": 100,
            "upper_percentile_threshold_binance": 95,
            "lower_percentile_threshold_binance": 5
        }
    )

    five_day_scaling_filters: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "amount_change_scaled_values": 100,
            "toptrader_short_threshold": 0.8,
            "toptrader_allow_entry_difference": 0.4,
            "oi_trade_threshold": 0.8,
            "oi_allow_entry_difference": 0.4
        }
    )

    exit_l3_metrics_in_profit: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "exit_amount_change_scaled_values": 200,
            "exit_toptrader_short_threshold": -0.95,
            "exit_toptrader_allow_difference": [0.4, 0.8],
            "exit_oi_threshold": -0.95,
            "exit_oi_allow_difference": [0.4, 0.8]
        }
    )

    only_execute_short: bool = False
    hold_profit_for_remaining_days: bool = False
    close_positions_on_stop: bool = True
    max_leverage: Decimal = 10.0

class CoinListingShortStrategy(BaseStrategy, Strategy):

    def __init__(self, config: CoinListingShortConfig):
        super().__init__(config)
        self.risk_manager = RiskManager(config)
        self.risk_manager.set_strategy(self)
        self.risk_manager.set_max_leverage(Decimal(str(config.max_leverage)))
        self.order_types = OrderTypes(self) 
        self.onboard_dates = self.load_onboard_dates()
        self.add_instrument_context()
        self.setup_btc_tracking()
        self.setup_sol_tracking()
    
    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            # atr
            atr_period = self.config.atr_period
            if self.config.exp_growth_atr_risk["enabled"]:
                atr_period = self.config.exp_growth_atr_risk["atr_period"]
                current_instrument["sl_atr_multiple"] = self.config.exp_growth_atr_risk["atr_multiple"]
            elif self.config.log_growth_atr_risk["enabled"]:
                atr_period = self.config.log_growth_atr_risk["atr_period"]
                current_instrument["sl_atr_multiple"] = self.config.log_growth_atr_risk["atr_multiple"]
            else:
                current_instrument["sl_atr_multiple"] = self.config.sl_atr_multiple
            
            current_instrument["atr"] = AverageTrueRange(atr_period)
            current_instrument["sl_price"] = None

            # aroon oscillator
            aroon_config = self.config.use_aroon_simple_trend_system
            aroon_period = aroon_config.get("aroon_period", 14)
            aroon_osc_short_threshold = aroon_config.get("aroon_osc_short_threshold", -50)
            current_instrument["aroon"] = AroonOscillator(aroon_period)
            current_instrument["aroon_osc_short_threshold"] = aroon_osc_short_threshold

            # coin filters
            coin_filters = self.config.use_min_coin_filters
            current_instrument["use_min_coin_filters"] = coin_filters.get("enabled", True)
            current_instrument["min_price"] = coin_filters.get("min_price", 0.1)
            current_instrument["min_24h_volume"] = coin_filters.get("min_24h_volume", 5000000)
            current_instrument["min_sum_open_interest_value"] = coin_filters.get("min_sum_open_interest_value", 500000)
            current_instrument["volume_history"] = []
            current_instrument["price_history"] = []
            current_instrument["rolling_24h_volume"] = 0.0
            current_instrument["rolling_24h_dollar_volume"] = 0.0
            current_instrument["latest_open_interest_value"] = 0.0

            # Position tracking
            current_instrument["prev_bar_close"] = None
            current_instrument["short_entry_price"] = None
            current_instrument["bars_since_entry"] = 0
            current_instrument["in_short_position"] = False

            # Aroon crossover detection
            current_instrument["prev_aroon_osc_value"] = None

            # l3 metrics
            current_instrument["sum_toptrader_long_short_ratio"] = 0.0
            current_instrument["count_long_short_ratio"] = 0.0
            current_instrument["latest_open_interest_value"] = 0.0


            # Scaled values (separate from raw values) - ENTRY scaling
            current_instrument["sum_toptrader_long_short_ratio_scaled_entry"] = 0.0
            current_instrument["count_long_short_ratio_scaled_entry"] = 0.0
            current_instrument["latest_open_interest_value_scaled_entry"] = 0.0

            # Scaled values (separate from raw values) - EXIT scaling
            current_instrument["sum_toptrader_long_short_ratio_scaled_exit"] = 0.0
            current_instrument["count_long_short_ratio_scaled_exit"] = 0.0
            current_instrument["latest_open_interest_value_scaled_exit"] = 0.0

            # Historical storage for scaling - ENTRY Binance metrics
            current_instrument["sum_toptrader_long_short_ratio_history_entry"] = []
            current_instrument["count_long_short_ratio_history_entry"] = []
            current_instrument["latest_open_interest_value_history_entry"] = []

            # Historical storage for scaling - EXIT Binance metrics
            current_instrument["sum_toptrader_long_short_ratio_history_exit"] = []
            current_instrument["count_long_short_ratio_history_exit"] = []
            current_instrument["latest_open_interest_value_history_exit"] = []

            # ENTRY Scaling configs - use values from YAML configuration
            entry_binance_config = self.config.entry_scale_binance_metrics
            current_instrument["entry_scale_binance_enabled"] = entry_binance_config["enabled"]
            current_instrument["entry_rolling_window_bars_binance"] = entry_binance_config["rolling_window_bars_binance"]
            current_instrument["entry_upper_percentile_threshold_binance"] = entry_binance_config["upper_percentile_threshold_binance"]
            current_instrument["entry_lower_percentile_threshold_binance"] = entry_binance_config["lower_percentile_threshold_binance"]

            # EXIT Scaling configs - use values from YAML configuration
            exit_binance_config = self.config.exit_scale_binance_metrics
            current_instrument["exit_scale_binance_enabled"] = exit_binance_config["enabled"]
            current_instrument["exit_rolling_window_bars_binance"] = exit_binance_config["rolling_window_bars_binance"]
            current_instrument["exit_upper_percentile_threshold_binance"] = exit_binance_config["upper_percentile_threshold_binance"]
            current_instrument["exit_lower_percentile_threshold_binance"] = exit_binance_config["lower_percentile_threshold_binance"]

            # Five day scaling filters configuration
            filter_config = self.config.five_day_scaling_filters
            current_instrument["five_day_filters_enabled"] = filter_config["enabled"]
            current_instrument["amount_change_scaled_values"] = filter_config["amount_change_scaled_values"]
            current_instrument["toptrader_short_threshold"] = filter_config["toptrader_short_threshold"]
            current_instrument["toptrader_allow_entry_difference"] = filter_config["toptrader_allow_entry_difference"]
            current_instrument["oi_trade_threshold"] = filter_config["oi_trade_threshold"]
            current_instrument["oi_allow_entry_difference"] = filter_config["oi_allow_entry_difference"]
            
            # Historical tracking for five day scaling filters (uses ENTRY scaled values)
            current_instrument["toptrader_scaled_history"] = []
            current_instrument["oi_scaled_history"] = []

            # Exit L3 metrics configuration
            exit_config = self.config.exit_l3_metrics_in_profit
            current_instrument["exit_l3_enabled"] = exit_config["enabled"]
            current_instrument["exit_amount_change_scaled_values"] = exit_config["exit_amount_change_scaled_values"]
            current_instrument["exit_toptrader_short_threshold"] = exit_config["exit_toptrader_short_threshold"]
            current_instrument["exit_toptrader_allow_difference"] = exit_config["exit_toptrader_allow_difference"]
            current_instrument["exit_oi_threshold"] = exit_config["exit_oi_threshold"]
            current_instrument["exit_oi_allow_difference"] = exit_config["exit_oi_allow_difference"]
            
            # Track entry values for exit logic
            current_instrument["entry_toptrader_scaled"] = None
            current_instrument["entry_oi_scaled"] = None
            
            # Separate history arrays for exit logic (independent from five_day_scaling_filters)
            current_instrument["exit_toptrader_scaled_history"] = []
            current_instrument["exit_oi_scaled_history"] = []

            # visualizer
            if self.config.use_aroon_simple_trend_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("aroon_osc", 2)
            
            # Initialize scaled metrics visualization (both entry and exit)
            current_instrument["collector"].initialise_logging_indicator("scaled_toptrader_ratio_entry", 1)
            current_instrument["collector"].initialise_logging_indicator("scaled_open_interest_entry", 1)
            current_instrument["collector"].initialise_logging_indicator("scaled_toptrader_ratio_exit", 1)
            current_instrument["collector"].initialise_logging_indicator("scaled_open_interest_exit", 1)
            
            if self.config.btc_performance_risk_scaling.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("btc_zscore", 1)
                current_instrument["collector"].initialise_logging_indicator("btc_risk_multiplier", 1)
            
            if self.config.sol_performance_risk_scaling.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("sol_zscore", 1)
                current_instrument["collector"].initialise_logging_indicator("sol_risk_multiplier", 1)
    
    def setup_btc_tracking(self):
        if not self.config.btc_performance_risk_scaling.get("enabled", False):
            return
            
        btc_config = self.config.btc_performance_risk_scaling
        
        self.btc_context = {
        "rolling_zscore": btc_config.get("rolling_zscore", 200),
        "risk_scaling_method": btc_config.get("risk_scaling_method", "exponential"),
        "stop_executing_above_zscore": btc_config.get("stop_executing_above_zscore", 4.0),
        "max_zscore": btc_config.get("max_zscore", 3.0),
        "min_zscore": btc_config.get("min_zscore", -3.0),
        "risk_multiplier_max_z_threshold": btc_config.get("risk_multiplier_max_z_threshold", 0.2),
        "risk_multiplier_min_z_threshold": btc_config.get("risk_multiplier_min_z_threshold", 2.0),
        "btc_instrument_id": None,
        
        # Rolling z-score calculation components
        "price_history": [],
        "current_zscore": 0.0,
        "rolling_mean": 0.0,
        "rolling_std": 0.0,
        "current_risk_multiplier": 1.0
        }
    
    def setup_sol_tracking(self):
        if not self.config.sol_performance_risk_scaling.get("enabled", False):
            return
            
        sol_config = self.config.sol_performance_risk_scaling
        
        self.sol_context = {
        "rolling_zscore": sol_config.get("rolling_zscore", 500),
        "risk_scaling_method": sol_config.get("risk_scaling_method", "linear"),
        "stop_executing_above_zscore": sol_config.get("stop_executing_above_zscore", 2.8),
        "max_zscore": sol_config.get("max_zscore", 4.0),
        "min_zscore": sol_config.get("min_zscore", -4.0),
        "risk_multiplier_max_z_threshold": sol_config.get("risk_multiplier_max_z_threshold", 0.2),
        "risk_multiplier_min_z_threshold": sol_config.get("risk_multiplier_min_z_threshold", 4.0),
        "sol_instrument_id": None,
        
        # Rolling z-score calculation components
        "price_history": [],
        "current_zscore": 0.0,
        "rolling_mean": 0.0,
        "rolling_std": 0.0,
        "current_risk_multiplier": 1.0
        }            
    
    def on_start(self): 
        super().on_start()
        self._subscribe_to_metrics_data()

    def _subscribe_to_metrics_data(self):
        try:
            metrics_data_type = DataType(MetricsData)
            self.subscribe_data(data_type=metrics_data_type)
        except Exception as e:
            self.log.error(f"Failed to subscribe to MetricsData: {e}", LogColor.RED)
        
    def update_rolling_24h_volume(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        current_volume = float(bar.volume) if hasattr(bar, 'volume') else 0.0
        current_price = float(bar.close)
        
        if "volume_history" not in current_instrument:
            current_instrument["volume_history"] = []
        if "price_history" not in current_instrument:
            current_instrument["price_history"] = []
            
        volume_history = current_instrument["volume_history"]
        price_history = current_instrument["price_history"]
        
        volume_history.append(current_volume)
        price_history.append(current_price)
        
        max_bars = 96
        if len(volume_history) > max_bars:
            volume_history.pop(0)
            price_history.pop(0)
        
        current_instrument["rolling_24h_volume"] = sum(volume_history)
        dollar_volumes = [vol * price for vol, price in zip(volume_history, price_history)]
        current_instrument["rolling_24h_dollar_volume"] = sum(dollar_volumes)
    
    def on_data(self, data) -> None:
        if isinstance(data, MetricsData):
            self.on_metrics_data(data)

    def on_metrics_data(self, data: MetricsData) -> None:
        instrument_id = data.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is not None:
            # Store raw values first
            current_instrument["sum_toptrader_long_short_ratio"] = data.sum_toptrader_long_short_ratio
            current_instrument["count_long_short_ratio"] = data.count_long_short_ratio
            current_instrument["latest_open_interest_value"] = data.sum_open_interest_value
            
            # Apply BOTH entry and exit scaling
            self.entry_scale_binance_metrics(current_instrument)
            self.exit_scale_binance_metrics(current_instrument)

    def passes_coin_filters(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument.get("use_min_coin_filters", True):
            return True
        
        min_price = current_instrument["min_price"]
        if min_price > 0 and float(bar.close) < min_price:
            return False
        
        min_24h_volume = current_instrument["min_24h_volume"]
        if min_24h_volume > 0:
            rolling_24h_dollar_volume = current_instrument.get("rolling_24h_dollar_volume", 0.0)
            if rolling_24h_dollar_volume < min_24h_volume:
                return False
        
        min_open_interest_value = current_instrument["min_sum_open_interest_value"]
        if min_open_interest_value > 0:
            latest_open_interest_value = current_instrument.get("latest_open_interest_value", 0.0)
            if latest_open_interest_value < min_open_interest_value:
                return False
        
        return True
    
    def passes_five_day_scaling_filters(self, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument.get("five_day_filters_enabled", True):
            return True
        
        toptrader_threshold = current_instrument.get("toptrader_short_threshold", 0.0)
        oi_threshold = current_instrument.get("oi_trade_threshold", [0.8, 0.95])
        toptrader_difference = current_instrument.get("toptrader_allow_entry_difference", 0.0)
        oi_difference = current_instrument.get("oi_allow_entry_difference", [0.2, 0.5])
        
        toptrader_history = current_instrument.get("toptrader_scaled_history", [])
        oi_history = current_instrument.get("oi_scaled_history", [])
        
        if len(toptrader_history) == 0 or len(oi_history) == 0:
            return False
        
        # Use ENTRY scaled values for entry logic
        current_toptrader = current_instrument.get("sum_toptrader_long_short_ratio_scaled_entry", 0.0)
        current_oi = current_instrument.get("latest_open_interest_value_scaled_entry", 0.0)
        
        if toptrader_threshold >= 0:
            # Positive threshold: look for downward movement from peaks
            toptrader_past_condition = any(val >= toptrader_threshold for val in toptrader_history)
            if toptrader_past_condition:
                max_toptrader = max(toptrader_history)
                toptrader_condition = current_toptrader <= (max_toptrader - toptrader_difference)
            else:
                toptrader_condition = False
        else:
            # Negative threshold: look for upward movement from lows
            toptrader_past_condition = any(val <= toptrader_threshold for val in toptrader_history)
            if toptrader_past_condition:
                min_toptrader = min(toptrader_history)
                toptrader_condition = current_toptrader >= (min_toptrader + toptrader_difference)
            else:
                toptrader_condition = False
        
        oi_threshold_val = oi_threshold[0] if isinstance(oi_threshold, list) else oi_threshold
        oi_difference_val = oi_difference[0] if isinstance(oi_difference, list) else oi_difference
        
        if oi_threshold_val >= 0:
            # Positive threshold: look for downward movement from peaks
            oi_past_condition = any(val >= oi_threshold_val for val in oi_history)
            if oi_past_condition:
                max_oi = max(oi_history)
                oi_condition = current_oi <= (max_oi - oi_difference_val)
            else:
                oi_condition = False
        else:
            # Negative threshold: look for upward movement from lows
            oi_past_condition = any(val <= oi_threshold_val for val in oi_history)
            if oi_past_condition:
                min_oi = min(oi_history)
                oi_condition = current_oi >= (min_oi + oi_difference_val)
            else:
                oi_condition = False
        
        # At least ONE condition must be met (OR logic)
        return toptrader_condition or oi_condition
    
    def check_exit_l3_metrics_signal(self, current_instrument: Dict[str, Any], position) -> bool:
        if not current_instrument.get("exit_l3_enabled", False):
            return False
        
        if position is None:
            return False
        
        entry_price = position.avg_px_open
        current_price = current_instrument.get("prev_bar_close", entry_price)
        
        if position.side == PositionSide.SHORT:
            is_profitable = current_price < entry_price
        else:
            is_profitable = current_price > entry_price
        
        if not is_profitable:
            return False
        
        # Use EXIT scaled values for exit logic
        current_toptrader = current_instrument.get("sum_toptrader_long_short_ratio_scaled_exit", 0.0)
        current_oi = current_instrument.get("latest_open_interest_value_scaled_exit", 0.0)
        
        exit_toptrader_threshold = current_instrument.get("exit_toptrader_short_threshold", 0.0)
        exit_oi_threshold = current_instrument.get("exit_oi_threshold", -0.95)
        exit_toptrader_allow_diff = current_instrument.get("exit_toptrader_allow_difference", 0.0)
        exit_oi_allow_diff = current_instrument.get("exit_oi_allow_difference", [0.5, 1.0])
        
        if isinstance(exit_toptrader_allow_diff, list):
            exit_toptrader_allow_diff = exit_toptrader_allow_diff[0]
        if isinstance(exit_oi_allow_diff, list):
            exit_oi_allow_diff = exit_oi_allow_diff[0]
        
        # Get lookback window for exit tracking
        lookback_window = current_instrument.get("exit_amount_change_scaled_values", 200)
        
        # Use separate exit history arrays
        toptrader_history = current_instrument.get("exit_toptrader_scaled_history", [])
        oi_history = current_instrument.get("exit_oi_scaled_history", [])
        
        if len(toptrader_history) > lookback_window:
            toptrader_recent = toptrader_history[-lookback_window:]
        else:
            toptrader_recent = toptrader_history
            
        if len(oi_history) > lookback_window:
            oi_recent = oi_history[-lookback_window:]
        else:
            oi_recent = oi_history
        
        toptrader_exit_signal = False
        if exit_toptrader_threshold != 0.0 and exit_toptrader_allow_diff > 0.0:
            if exit_toptrader_threshold >= 0:
                # Positive threshold: check if we reached the extreme high, then snapped back down
                toptrader_reached_extreme = any(val >= exit_toptrader_threshold for val in toptrader_recent)
                if toptrader_reached_extreme:
                    max_toptrader = max(toptrader_recent)
                    toptrader_exit_signal = current_toptrader <= (max_toptrader - exit_toptrader_allow_diff)
            else:
                # Negative threshold: check if we reached the extreme low, then snapped back up
                toptrader_reached_extreme = any(val <= exit_toptrader_threshold for val in toptrader_recent)
                if toptrader_reached_extreme:
                    min_toptrader = min(toptrader_recent)
                    required_rebound = min_toptrader + exit_toptrader_allow_diff
                    toptrader_exit_signal = current_toptrader >= required_rebound
        
        oi_exit_signal = False
        if exit_oi_threshold != 0.0 and exit_oi_allow_diff > 0.0:
            if exit_oi_threshold >= 0:
                # Positive threshold: check if we reached the extreme high, then snapped back down
                oi_reached_extreme = any(val >= exit_oi_threshold for val in oi_recent)
                if oi_reached_extreme:
                    max_oi = max(oi_recent)
                    oi_exit_signal = current_oi <= (max_oi - exit_oi_allow_diff)
            else:
                # Negative threshold: check if we reached the extreme low, then snapped back up
                oi_reached_extreme = any(val <= exit_oi_threshold for val in oi_recent)
                if oi_reached_extreme:
                    min_oi = min(oi_recent)
                    required_oi_rebound = min_oi + exit_oi_allow_diff
                    oi_exit_signal = current_oi >= required_oi_rebound
                    
        final_exit_signal = toptrader_exit_signal or oi_exit_signal
        
        return final_exit_signal
    
    def detect_aroon_crossover_below(self, current_instrument: Dict[str, Any]) -> bool:
        aroon = current_instrument["aroon"]
        if not aroon.initialized:
            return False
            
        current_aroon = float(aroon.value)
        prev_aroon = current_instrument.get("prev_aroon_osc_value")
        threshold = current_instrument["aroon_osc_short_threshold"]
        
        if prev_aroon is None:
            return False
        
        crossover_detected = (prev_aroon > threshold) and (current_aroon <= threshold)
        
        return crossover_detected
    
    def load_onboard_dates(self):
        import csv
        from pathlib import Path
        
        onboard_dates = {}
        csv_path = Path(__file__).parent.parent / "data" / "DATA_STORAGE" / "project_future_scraper" / "new_binance_perpetual_futures.csv"
        
        try:
            with open(csv_path, 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    symbol = row['symbol']
                    onboard_date_str = row['onboardDate']
                    onboard_date = datetime.strptime(onboard_date_str, "%Y-%m-%d %H:%M:%S")
                    onboard_dates[symbol] = onboard_date
        except Exception as e:
            self.log.error(f"Failed to load onboard dates: {e}")
            
        return onboard_dates
    
    def check_time_based_exit(self, bar: Bar, current_instrument: Dict[str, Any], position, time_after_listing_close) -> bool:

        # Handle both single value and array for optimization
        if isinstance(time_after_listing_close, list):
            time_after_listing_close = time_after_listing_close[0]  # Use first value
            
        if time_after_listing_close is None or time_after_listing_close <= 0:
            return False
            
        instrument_id_str = str(bar.bar_type.instrument_id)
        base_symbol = instrument_id_str.split('-')[0]
        
        if base_symbol not in self.onboard_dates:
            return False
            
        onboard_date = self.onboard_dates[base_symbol]
        deadline = onboard_date + timedelta(days=time_after_listing_close)
        
        current_time = datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=timezone.utc).replace(tzinfo=None)
        
        if current_time >= deadline:
            return True
        #    entry_price = position.avg_px_open
        #    current_price = float(bar.close)
        #    
        #    if position.side == PositionSide.LONG:
        #        is_profitable = current_price > entry_price
        #    else:
        #        is_profitable = current_price < entry_price
                
        #    return is_profitable
            
        #return False    
    
    def is_trading_allowed_after_listing(self, bar: Bar) -> bool:
        if not self.config.hold_profit_for_remaining_days:
            return True
            
        instrument_id_str = str(bar.bar_type.instrument_id)
        base_symbol = instrument_id_str.split('-')[0]
        
        if base_symbol not in self.onboard_dates:
            return True
            
        onboard_date = self.onboard_dates[base_symbol]
        
        # Handle both single value and array for optimization
        time_after_listing = self.config.time_after_listing_close
        if isinstance(time_after_listing, list):
            time_after_listing = time_after_listing[0]  # Use first value for strategy logic
            
        deadline = onboard_date + timedelta(days=time_after_listing)
        
        current_time = datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=timezone.utc).replace(tzinfo=None)
        
        # Block all new trades after deadline
        if current_time < deadline:
            return True
        else:
            self.order_types.close_position_by_market_order(bar.bar_type.instrument_id)
            self.unsubscribe_bars(bar.bar_type)
            return False

    def entry_scale_binance_metrics(self, current_instrument: Dict[str, Any]) -> None:
        if not current_instrument.get("entry_scale_binance_enabled", True):
            return

        rolling_window = current_instrument.get("entry_rolling_window_bars_binance", 100)
        upper_threshold = current_instrument.get("entry_upper_percentile_threshold_binance", 95)
        lower_threshold = current_instrument.get("entry_lower_percentile_threshold_binance", 5)

        metrics = [
            ("sum_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio_history_entry", "sum_toptrader_long_short_ratio_scaled_entry"),
            ("count_long_short_ratio", "count_long_short_ratio_history_entry", "count_long_short_ratio_scaled_entry"),
            ("latest_open_interest_value", "latest_open_interest_value_history_entry", "latest_open_interest_value_scaled_entry")
        ]

        for metric_key, history_key, scaled_key in metrics:
            current_value = current_instrument[metric_key]
            history = current_instrument[history_key]
            
            history.append(current_value)
            
            if len(history) > rolling_window:
                history.pop(0)
            
            # Calculate percentile-based scaling
            if len(history) > 1:  # Need at least 2 values for percentiles
                sorted_values = sorted(history)
                n = len(sorted_values)
                
                lower_pos = (lower_threshold / 100.0) * (n - 1)
                upper_pos = (upper_threshold / 100.0) * (n - 1)
                
                lower_val = sorted_values[int(lower_pos)]
                upper_val = sorted_values[int(upper_pos)]
                
                if current_value <= lower_val:
                    scaled_value = -1.0
                elif current_value >= upper_val:
                    scaled_value = 1.0
                else:
                    if upper_val != lower_val:
                        scaled_value = -1.0 + 2.0 * (current_value - lower_val) / (upper_val - lower_val)
                    else:
                        scaled_value = 0.0
                
                # Store scaled value in separate field (keep raw value intact)
                current_instrument[scaled_key] = scaled_value
            else:
                current_instrument[scaled_key] = 0.0
        
        # Update historical tracking for five day filters (ENTRY uses entry scaled values)
        self.update_five_day_filter_history(current_instrument)

    def exit_scale_binance_metrics(self, current_instrument: Dict[str, Any]) -> None:
        if not current_instrument.get("exit_scale_binance_enabled", True):
            return

        rolling_window = current_instrument.get("exit_rolling_window_bars_binance", 100)
        upper_threshold = current_instrument.get("exit_upper_percentile_threshold_binance", 95)
        lower_threshold = current_instrument.get("exit_lower_percentile_threshold_binance", 5)

        metrics = [
            ("sum_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio_history_exit", "sum_toptrader_long_short_ratio_scaled_exit"),
            ("count_long_short_ratio", "count_long_short_ratio_history_exit", "count_long_short_ratio_scaled_exit"),
            ("latest_open_interest_value", "latest_open_interest_value_history_exit", "latest_open_interest_value_scaled_exit")
        ]

        for metric_key, history_key, scaled_key in metrics:
            current_value = current_instrument[metric_key]
            history = current_instrument[history_key]
            
            history.append(current_value)
            
            if len(history) > rolling_window:
                history.pop(0)
            
            # Calculate percentile-based scaling
            if len(history) > 1:  # Need at least 2 values for percentiles
                sorted_values = sorted(history)
                n = len(sorted_values)
                
                lower_pos = (lower_threshold / 100.0) * (n - 1)
                upper_pos = (upper_threshold / 100.0) * (n - 1)
                
                lower_val = sorted_values[int(lower_pos)]
                upper_val = sorted_values[int(upper_pos)]
                
                if current_value <= lower_val:
                    scaled_value = -1.0
                elif current_value >= upper_val:
                    scaled_value = 1.0
                else:
                    if upper_val != lower_val:
                        scaled_value = -1.0 + 2.0 * (current_value - lower_val) / (upper_val - lower_val)
                    else:
                        scaled_value = 0.0
                
                # Store scaled value in separate field (keep raw value intact)
                current_instrument[scaled_key] = scaled_value
            else:
                current_instrument[scaled_key] = 0.0
        
        # Update exit history (EXIT uses exit scaled values)
        self.update_exit_history(current_instrument)

    def update_five_day_filter_history(self, current_instrument: Dict[str, Any]) -> None:
        if not current_instrument.get("five_day_filters_enabled", True):
            return
        
        lookback_window = current_instrument.get("amount_change_scaled_values", 100)
        
        # Use ENTRY scaled values for five day filters (entry logic)
        toptrader_scaled = current_instrument.get("sum_toptrader_long_short_ratio_scaled_entry", 0.0)
        oi_scaled = current_instrument.get("latest_open_interest_value_scaled_entry", 0.0)
        
        current_instrument["toptrader_scaled_history"].append(toptrader_scaled)
        current_instrument["oi_scaled_history"].append(oi_scaled)
        
        if len(current_instrument["toptrader_scaled_history"]) > lookback_window:
            current_instrument["toptrader_scaled_history"].pop(0)
            
        if len(current_instrument["oi_scaled_history"]) > lookback_window:
            current_instrument["oi_scaled_history"].pop(0)

    def update_exit_history(self, current_instrument: Dict[str, Any]) -> None:
        if not current_instrument.get("exit_l3_enabled", False):
            return
        
        lookback_window = current_instrument.get("exit_amount_change_scaled_values", 200)
        
        # Use EXIT scaled values for exit logic
        toptrader_scaled = current_instrument.get("sum_toptrader_long_short_ratio_scaled_exit", 0.0)
        oi_scaled = current_instrument.get("latest_open_interest_value_scaled_exit", 0.0)
        
        # Initialize separate exit history arrays if needed
        if "exit_toptrader_scaled_history" not in current_instrument:
            current_instrument["exit_toptrader_scaled_history"] = []
        if "exit_oi_scaled_history" not in current_instrument:
            current_instrument["exit_oi_scaled_history"] = []
        
        current_instrument["exit_toptrader_scaled_history"].append(toptrader_scaled)
        current_instrument["exit_oi_scaled_history"].append(oi_scaled)
        
        if len(current_instrument["exit_toptrader_scaled_history"]) > lookback_window:
            current_instrument["exit_toptrader_scaled_history"].pop(0)
            
        if len(current_instrument["exit_oi_scaled_history"]) > lookback_window:
            current_instrument["exit_oi_scaled_history"].pop(0)

    def is_btc_instrument(self, instrument_id) -> bool:
        return "BTCUSDT" in str(instrument_id)
    
    def is_sol_instrument(self, instrument_id) -> bool:
        return "SOLUSDT" in str(instrument_id)
    
    def process_btc_bar(self, bar: Bar) -> None:
        if not self.config.btc_performance_risk_scaling.get("enabled", False):
            return
            
        if not hasattr(self, 'btc_context'):
            self.setup_btc_tracking()
            
        if self.btc_context["btc_instrument_id"] is None:
            self.btc_context["btc_instrument_id"] = bar.bar_type.instrument_id

        current_price = float(bar.close)
        self.btc_context["price_history"].append(current_price)
        
        window_size = self.btc_context["rolling_zscore"]
        if len(self.btc_context["price_history"]) > window_size:
            self.btc_context["price_history"].pop(0)
        
        self.update_btc_risk_metrics()
    
    def process_sol_bar(self, bar: Bar) -> None:
        if not self.config.sol_performance_risk_scaling.get("enabled", False):
            return
            
        if not hasattr(self, 'sol_context'):
            self.setup_sol_tracking()
            
        if self.sol_context["sol_instrument_id"] is None:
            self.sol_context["sol_instrument_id"] = bar.bar_type.instrument_id

        current_price = float(bar.close)
        self.sol_context["price_history"].append(current_price)
        
        window_size = self.sol_context["rolling_zscore"]
        if len(self.sol_context["price_history"]) > window_size:
            self.sol_context["price_history"].pop(0)
        
        self.update_sol_risk_metrics()
        

    def update_btc_risk_metrics(self) -> None:
        if not hasattr(self, 'btc_context') or len(self.btc_context["price_history"]) < 2:
            if hasattr(self, 'btc_context'):
                self.btc_context["current_risk_multiplier"] = 1.0
            return

        price_history = self.btc_context["price_history"]
        window_size = self.btc_context["rolling_zscore"]

        if len(price_history) >= 2:
            # Use leak-safe approach: exclude current price from statistics calculation
            stats_data = price_history[:-1]
            
            # Apply the window size properly
            if len(stats_data) > window_size:
                rolling_data = stats_data[-window_size:]  # Take last window_size points
            else:
                rolling_data = stats_data  # Use all available data if less than window
                
            self.btc_context["rolling_mean"] = sum(rolling_data) / len(rolling_data)

            if len(rolling_data) > 1:
                variance = sum((x - self.btc_context["rolling_mean"]) ** 2 for x in rolling_data) / (len(rolling_data) - 1)
                self.btc_context["rolling_std"] = variance ** 0.5
            else:
                self.btc_context["rolling_std"] = 0.0
            
            # Calculate z-score for current price
            current_price = price_history[-1]
            if self.btc_context["rolling_std"] > 0:
                self.btc_context["current_zscore"] = (current_price - self.btc_context["rolling_mean"]) / self.btc_context["rolling_std"]
            else:
                self.btc_context["current_zscore"] = 0.0
            
            # Clamp z-score to configured bounds
            zscore = max(self.btc_context["min_zscore"], 
                        min(self.btc_context["max_zscore"], self.btc_context["current_zscore"]))
            
            risk_multiplier = self._zscore_to_risk_multiplier_btc(zscore)
            self.btc_context["current_risk_multiplier"] = risk_multiplier
        else:
            self.btc_context["current_risk_multiplier"] = 1.0

    def update_sol_risk_metrics(self) -> None:
        if not hasattr(self, 'sol_context') or len(self.sol_context["price_history"]) < 2:
            if hasattr(self, 'sol_context'):
                self.sol_context["current_risk_multiplier"] = 1.0
            return

        price_history = self.sol_context["price_history"]
        window_size = self.sol_context["rolling_zscore"]

        if len(price_history) >= 2:
            # Use leak-safe approach: exclude current price from statistics calculation
            stats_data = price_history[:-1]
            
            # Apply the window size properly
            if len(stats_data) > window_size:
                rolling_data = stats_data[-window_size:]  # Take last window_size points
            else:
                rolling_data = stats_data  # Use all available data if less than window
                
            self.sol_context["rolling_mean"] = sum(rolling_data) / len(rolling_data)

            if len(rolling_data) > 1:
                variance = sum((x - self.sol_context["rolling_mean"]) ** 2 for x in rolling_data) / (len(rolling_data) - 1)
                self.sol_context["rolling_std"] = variance ** 0.5
            else:
                self.sol_context["rolling_std"] = 0.0
            
            # Calculate z-score for current price
            current_price = price_history[-1]
            if self.sol_context["rolling_std"] > 0:
                self.sol_context["current_zscore"] = (current_price - self.sol_context["rolling_mean"]) / self.sol_context["rolling_std"]
            else:
                self.sol_context["current_zscore"] = 0.0
            
            # Clamp z-score to configured bounds
            zscore = max(self.sol_context["min_zscore"], 
                        min(self.sol_context["max_zscore"], self.sol_context["current_zscore"]))
            
            risk_multiplier = self._zscore_to_risk_multiplier_sol(zscore)
            self.sol_context["current_risk_multiplier"] = risk_multiplier
        else:
            self.sol_context["current_risk_multiplier"] = 1.0

    def _zscore_to_risk_multiplier_btc(self, zscore: float) -> float:
        min_risk = self.btc_context["risk_multiplier_max_z_threshold"]  # 0.2 (low risk when BTC bullish)
        max_risk = self.btc_context["risk_multiplier_min_z_threshold"]  # 2.0 (high risk when BTC bearish)
        
        min_z = self.btc_context["min_zscore"]  # -3.0
        max_z = self.btc_context["max_zscore"]  # 3.0
        
        # Normalize z-score to 0-1 range
        normalized = (zscore - min_z) / (max_z - min_z)
        normalized = max(0.0, min(1.0, normalized))
        
        inverted_normalized = 1.0 - normalized
        
        if self.btc_context["risk_scaling_method"] == "exponential":
            risk_multiplier = min_risk + (max_risk - min_risk) * (inverted_normalized ** 2)
        else:
            risk_multiplier = min_risk + (max_risk - min_risk) * inverted_normalized
        
        return risk_multiplier

    def _zscore_to_risk_multiplier_sol(self, zscore: float) -> float:
        min_risk = self.sol_context["risk_multiplier_max_z_threshold"]  # 0.2 (low risk when SOL bullish)
        max_risk = self.sol_context["risk_multiplier_min_z_threshold"]  # 4.0 (high risk when SOL bearish)
        
        min_z = self.sol_context["min_zscore"]  # -4.0
        max_z = self.sol_context["max_zscore"]  # 4.0
        
        # Normalize z-score to 0-1 range
        normalized = (zscore - min_z) / (max_z - min_z)
        normalized = max(0.0, min(1.0, normalized))
        
        inverted_normalized = 1.0 - normalized
        
        if self.sol_context["risk_scaling_method"] == "exponential":
            risk_multiplier = min_risk + (max_risk - min_risk) * (inverted_normalized ** 2)
        else:
            risk_multiplier = min_risk + (max_risk - min_risk) * inverted_normalized
        
        return risk_multiplier






    
    def update_btc_visualizer_data(self, bar: Bar, btc_instrument: Dict[str, Any]) -> None:
        if not hasattr(self, 'btc_context'):
            return
            
        btc_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="btc_zscore", value=self.btc_context.get("current_zscore", 0.0))
        btc_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="btc_risk_multiplier", value=self.btc_context.get("current_risk_multiplier", 1.0))
    
    def update_sol_visualizer_data(self, bar: Bar, sol_instrument: Dict[str, Any]) -> None:
        if not hasattr(self, 'sol_context'):
            return
            
        sol_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="sol_zscore", value=self.sol_context.get("current_zscore", 0.0))
        sol_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="sol_risk_multiplier", value=self.sol_context.get("current_risk_multiplier", 1.0))
    
    def get_btc_risk_multiplier(self) -> float:
        if not self.config.btc_performance_risk_scaling.get("enabled", False):
            return 1.0
            
        if not hasattr(self, 'btc_context'):
            return 1.0
            
        return self.btc_context.get("current_risk_multiplier", 1.0)
    
    def get_sol_risk_multiplier(self) -> float:
        if not self.config.sol_performance_risk_scaling.get("enabled", False):
            return 1.0
            
        if not hasattr(self, 'sol_context'):
            return 1.0
            
        return self.sol_context.get("current_risk_multiplier", 1.0)
    
    def should_stop_executing_due_to_btc_zscore(self) -> bool:
        if not self.config.btc_performance_risk_scaling.get("enabled", False):
            return False
            
        if not hasattr(self, 'btc_context'):
            return False
            
        current_zscore = self.btc_context.get("current_zscore", 0.0)
        stop_threshold = self.btc_context.get("stop_executing_above_zscore", 4.0)
        
        should_stop = current_zscore > stop_threshold

        return should_stop
    
    def should_stop_executing_due_to_sol_zscore(self) -> bool:
        if not self.config.sol_performance_risk_scaling.get("enabled", False):
            return False
            
        if not hasattr(self, 'sol_context'):
            return False
            
        current_zscore = self.sol_context.get("current_zscore", 0.0)
        stop_threshold = self.sol_context.get("stop_executing_above_zscore", 2.8)
        
        should_stop = current_zscore > stop_threshold

        return should_stop
    
    def calculate_risk_based_position_size(self, instrument_id, entry_price: float, stop_loss_price: float) -> int:
        # SAFETY: Never calculate position size for BTC or SOL - return 0 to prevent trading
        if self.is_btc_instrument(instrument_id):
            self.log.warning(f"Position sizing blocked for BTC instrument: {instrument_id}")
            return 0
        
        if self.is_sol_instrument(instrument_id):
            self.log.warning(f"Position sizing blocked for SOL instrument: {instrument_id}")
            return 0
            
        from decimal import Decimal
        
        entry_price_decimal = Decimal(str(entry_price))
        stop_loss_price_decimal = Decimal(str(stop_loss_price))
        
        btc_risk_multiplier = self.get_btc_risk_multiplier()
        sol_risk_multiplier = self.get_sol_risk_multiplier()
        
        # Combine both risk multipliers (multiply them together)
        combined_risk_multiplier = btc_risk_multiplier * sol_risk_multiplier
        
        if self.config.exp_growth_atr_risk["enabled"]:
            base_risk_percent = Decimal(str(self.config.exp_growth_atr_risk["risk_percent"]))
            adjusted_risk_percent = base_risk_percent * Decimal(str(combined_risk_multiplier))
            exact_contracts = self.risk_manager.exp_growth_atr_risk(entry_price_decimal, stop_loss_price_decimal, adjusted_risk_percent)
            return round(float(exact_contracts))
        
        if self.config.log_growth_atr_risk["enabled"]:
            base_risk_percent = Decimal(str(self.config.log_growth_atr_risk["risk_percent"]))
            adjusted_risk_percent = base_risk_percent * Decimal(str(combined_risk_multiplier))
            exact_contracts = self.risk_manager.log_growth_atr_risk(entry_price_decimal, stop_loss_price_decimal, adjusted_risk_percent)
            return round(float(exact_contracts))
        
        return self.calculate_fixed_position_size(instrument_id, entry_price)

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        
        if self.is_btc_instrument(instrument_id):
            self.process_btc_bar(bar)
            
            btc_instrument = self.instrument_dict.get(instrument_id)
            if btc_instrument is not None:
                self.update_btc_visualizer_data(bar, btc_instrument)
            return
        
        if self.is_sol_instrument(instrument_id):
            self.process_sol_bar(bar)
            
            sol_instrument = self.instrument_dict.get(instrument_id)
            if sol_instrument is not None:
                self.update_sol_visualizer_data(bar, sol_instrument)
            return
            
        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is None:
            self.log.warning(f"No instrument found for {instrument_id}", LogColor.RED)
            return
        if "atr" not in current_instrument:
            self.add_instrument_context()
        
        self.update_rolling_24h_volume(bar, current_instrument)

        # Always handle ATR (needed for stop loss)
        current_instrument["atr"].handle_bar(bar)

        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            aroon.handle_bar(bar)
        
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            if not aroon.initialized:
                return        
        
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
                
        if not self.passes_coin_filters(bar, current_instrument):
            return
        
        position = self.base_get_position(instrument_id)

        if position is not None and position.side == PositionSide.SHORT:
            self.short_exit_logic(bar, current_instrument, position)
            return
        
        # Block new trades after listing deadline
        if not self.is_trading_allowed_after_listing(bar):
            return
            
        # Block new trades when BTC z-score is too high (extremely bullish)
        if self.should_stop_executing_due_to_btc_zscore():
            return
        
        # Block new trades when SOL z-score is too high (extremely bullish)
        if self.should_stop_executing_due_to_sol_zscore():
            return
            
        self.aroon_simple_trend_setup(bar, current_instrument)
        
        # Update previous Aroon value for next bar's crossover detection
        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            if aroon.initialized:
                current_instrument["prev_aroon_osc_value"] = float(aroon.value)



                

    
    def aroon_simple_trend_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if self.is_btc_instrument(bar.bar_type.instrument_id):
            return
            
        if not self.config.use_aroon_simple_trend_system.get("enabled", False):
            return
        
        aroon = current_instrument["aroon"]
        if not aroon.initialized:
            return
        
        if self.detect_aroon_crossover_below(current_instrument):
            # Then check both toptrader and OI filters before executing
            if self.passes_five_day_scaling_filters(current_instrument):
                self.enter_short_aroon_trend(bar, current_instrument)

    def enter_short_aroon_trend(self, bar: Bar, current_instrument: Dict[str, Any]):   
        instrument_id = bar.bar_type.instrument_id
        
        if self.is_btc_instrument(instrument_id):
            return
            
        entry_price = float(bar.close)
        
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 1.02
        
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["bars_since_entry"] = 0
            current_instrument["min_topt_difference_since_entry"] = None
            current_instrument["sl_price"] = stop_loss_price
            
            # Store entry metric values for exit logic (using ENTRY scaled values)
            current_instrument["entry_toptrader_scaled"] = current_instrument.get("sum_toptrader_long_short_ratio_scaled_entry", 0.0)
            current_instrument["entry_oi_scaled"] = current_instrument.get("latest_open_interest_value_scaled_entry", 0.0)
            
            self.log.info("Executing short trade - passed all filters (aroon crossover + toptrader + OI)")
            self.order_types.submit_short_market_order(instrument_id, qty)
            #self.order_types.submit_short_bracket_order(instrument_id, qty, entry_price, stop_loss_price, 0.000001)
    
    def short_exit_logic(self, bar: Bar, current_instrument: Dict[str, Any], position):
        current_instrument["bars_since_entry"] += 1
        sl_price = current_instrument.get("sl_price")
        instrument_id = bar.bar_type.instrument_id
        current_instrument["prev_bar_close"] = float(bar.close)
        
        if sl_price is not None and float(bar.close) >= sl_price:
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                #self.order_types.submit_long_market_order(instrument_id, int(close_qty))
                self.order_types.close_position_by_market_order(instrument_id)

            self.reset_position_tracking(current_instrument)
            return

        # Check for L3 metrics exit signal (counter-signals)
        if self.check_exit_l3_metrics_signal(current_instrument, position):
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                #self.order_types.submit_long_market_order(instrument_id, int(close_qty))
                self.order_types.close_position_by_market_order(instrument_id)
            self.reset_position_tracking(current_instrument)
            return

        if self.check_time_based_exit(bar, current_instrument, position, self.config.time_after_listing_close):
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                #self.order_types.submit_long_market_order(instrument_id, int(close_qty))
                self.order_types.close_position_by_market_order(instrument_id)
            self.reset_position_tracking(current_instrument)
            return
        
        if self.config.hold_profit_for_remaining_days:
            return

    def reset_position_tracking(self, current_instrument: Dict[str, Any]):
        current_instrument["short_entry_price"] = None
        current_instrument["bars_since_entry"] = 0
        current_instrument["sl_price"] = None
        current_instrument["in_short_position"] = False
        current_instrument["entry_toptrader_scaled"] = None
        current_instrument["entry_oi_scaled"] = None     



    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)

        # Scaled Binance metrics visualization (-1 to 1) - BOTH entry and exit
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="scaled_toptrader_ratio_entry", value=current_instrument.get("sum_toptrader_long_short_ratio_scaled_entry", 0.0))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="scaled_open_interest_entry", value=current_instrument.get("latest_open_interest_value_scaled_entry", 0.0))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="scaled_toptrader_ratio_exit", value=current_instrument.get("sum_toptrader_long_short_ratio_scaled_exit", 0.0))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="scaled_open_interest_exit", value=current_instrument.get("latest_open_interest_value_scaled_exit", 0.0))

        # Aroon Oscillator (position 2)
        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            aroon_osc_value = float(aroon.value) if aroon.value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="aroon_osc", value=aroon_osc_value)

        # BTC Risk Scaling metrics
        if self.config.btc_performance_risk_scaling.get("enabled", False) and hasattr(self, 'btc_context'):
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="btc_risk_multiplier", value=self.btc_context.get("current_risk_multiplier", 1.0))

        # SOL Risk Scaling metrics
        if self.config.sol_performance_risk_scaling.get("enabled", False) and hasattr(self, 'sol_context'):
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="sol_risk_multiplier", value=self.sol_context.get("current_risk_multiplier", 1.0))


    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)
    

    def on_position_closed(self, position_closed) -> None:
        instrument_id = position_closed.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is not None:
            self.reset_position_tracking(current_instrument)
        return self.base_on_position_closed(position_closed)
    
    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: Optional[InstrumentId] = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)