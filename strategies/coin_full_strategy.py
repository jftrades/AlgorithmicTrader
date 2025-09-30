# in here is the coin short strategy to short coins that have been listed for 14 days
from datetime import datetime, time, timezone, timedelta
from typing import Any, Dict, Optional, List
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.common.enums import LogColor
from pydantic import Field
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from nautilus_trader.indicators.macd import MovingAverageConvergenceDivergence
from nautilus_trader.indicators.donchian_channel import DonchianChannel
from nautilus_trader.indicators.aroon import AroonOscillator
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from nautilus_trader.indicators.atr import AverageTrueRange
from nautilus_trader.indicators.dm import DirectionalMovement
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from data.download.crypto_downloads.custom_class.metrics_data import MetricsData

class CoinFullConfig(StrategyConfig):
    instruments: List[dict]  
    max_leverage: float
    min_account_balance: float
    run_id: str
    sl_atr_multiple: float = 2.0
    atr_period: int = 14

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

    # Exit Methods Configuration
    use_close_ema: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "exit_trend_ema_period": 120,
            "min_bars_over_ema": 35,
            "min_bars_under_ema": 35
        }
    )

    use_fixed_rr: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "rr_tp_ratio": 1.5
        }
    )

    use_rsi_as_exit: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "rsi_period": 20,
            "rsi_long_exit_threshold": 0.7,
            "rsi_short_exit_threshold": 0.3
        }
    )

    use_topt_ratio_as_exit: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "short_min_extreme_reversal_topt_longshortratio": 0.3,
            "long_min_extreme_reversal_topt_longshortratio": 0.3
        }
    )

    use_macd_exit_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "macd_fast_exit_period": 10,
            "macd_slow_exit_period": 32,
            "macd_signal_exit_period": 10
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

    use_directional_movement_filter: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "period": 14,
            "min_di_diff": 0.02
        }
    )

    use_htf_ema_bias_filter: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "ema_period": 200
        }
    )

    use_trend_following_setup: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "entry_trend_ema_period": 40,
            "min_bars_under_ema": 20,
            "min_bars_over_ema": 20
        }
    )

    use_spike_reversion_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "reversion_ema_period": 25,
            "spike_atr_threshold": 0.4,
            "spike_atr_period": 10,
            "min_bars_spike_over_ema": 12,
            "min_bars_spike_under_ema": 12
        }
    )

    use_rsi_simple_reversion_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "usage_method": "execution",  # "execution" or "condition"
            "rsi_period": 20,
            "rsi_overbought": 0.7,
            "rsi_oversold": 0.3
        }
    )

    use_macd_simple_reversion_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9
        }
    )   

    use_aroon_simple_trend_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "aroon_period": 14,
            "aroon_osc_long_threshold": 50,
            "aroon_osc_short_threshold": -50
        }
    )

    use_donchian_breakout_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "donchian_period": 20,
            "min_breakout_strength": 0.5
        }
    )

    only_trade_rth: bool = False
    only_execute_short: bool = False
    hold_profit_for_remaining_days: bool = False
    close_positions_on_stop: bool = True


class CoinFullStrategy(BaseStrategy,Strategy):
    def __init__(self, config: CoinFullConfig):
        super().__init__(config)
        self.risk_manager = RiskManager(config)
        self.risk_manager.set_strategy(self)  # Set strategy reference for risk manager
        self.order_types = OrderTypes(self) 
        self.onboard_dates = self.load_onboard_dates()
        self.add_instrument_context()
    
    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            # risk management - get ATR period from enabled risk method
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

            # directional movement filter
            dm_config = self.config.use_directional_movement_filter
            dm_period = dm_config.get("period", 14)
            current_instrument["directional_movement"] = DirectionalMovement(dm_period)
            current_instrument["min_di_diff"] = dm_config.get("min_di_diff", 0.02)

            # htf ema bias filter
            htf_ema_config = self.config.use_htf_ema_bias_filter
            htf_ema_period = htf_ema_config.get("ema_period", 200)
            current_instrument["htf_ema"] = ExponentialMovingAverage(htf_ema_period)

            # aroon filter
            aroon_config = self.config.use_aroon_simple_trend_system
            aroon_period = aroon_config.get("aroon_period", 14)
            aroon_osc_long_threshold = aroon_config.get("aroon_osc_long_threshold", 50)
            aroon_osc_short_threshold = aroon_config.get("aroon_osc_short_threshold", -50)
            current_instrument["aroon"] = AroonOscillator(aroon_period)
            current_instrument["aroon_osc_long_threshold"] = aroon_osc_long_threshold   
            current_instrument["aroon_osc_short_threshold"] = aroon_osc_short_threshold

            # donchian channel
            donchian_config = self.config.use_donchian_breakout_system
            donchian_period = donchian_config.get("donchian_period", 20)
            min_breakout_strength = donchian_config.get("min_breakout_strength", 0.5)
            current_instrument["donchian"] = DonchianChannel(donchian_period)
            current_instrument["min_breakout_strength"] = min_breakout_strength

            # spike basic
            spike_config = self.config.use_spike_reversion_system
            spike_atr_period = spike_config.get("spike_atr_period", 20)
            reversion_ema_period = spike_config.get("reversion_ema_period", 25)
            current_instrument["spike_atr"] = AverageTrueRange(spike_atr_period)
            current_instrument["reversion_ema"] = ExponentialMovingAverage(reversion_ema_period)
            current_instrument["spike_atr_threshold"] = spike_config.get("spike_atr_threshold", 2.5)

            # macd simple reversion
            macd_config = self.config.use_macd_simple_reversion_system
            macd_fast_period = macd_config.get("macd_fast_period", 12)
            macd_slow_period = macd_config.get("macd_slow_period", 26)
            macd_signal_period = macd_config.get("macd_signal_period", 9)
            current_instrument["macd"] = MovingAverageConvergenceDivergence(macd_fast_period, macd_slow_period)
            current_instrument["macd_signal_ema"] = ExponentialMovingAverage(macd_signal_period)
            current_instrument["prev_macd_line"] = None
            current_instrument["prev_macd_signal"] = None

            # rsi simple reversion
            rsi_config = self.config.use_rsi_simple_reversion_system
            rsi_period = rsi_config.get("rsi_period", 14)
            current_instrument["rsi"] = RelativeStrengthIndex(rsi_period)
            current_instrument["rsi_overbought"] = rsi_config.get("rsi_overbought", 70)
            current_instrument["rsi_oversold"] = rsi_config.get("rsi_oversold", 30)

            # trend basic
            trend_config = self.config.use_trend_following_setup
            entry_trend_ema_period = trend_config.get("entry_trend_ema_period", 40)
            current_instrument["entry_trend_ema"] = ExponentialMovingAverage(entry_trend_ema_period)
            
            # exit methods
            exit_config = self.config.use_close_ema
            exit_trend_ema_period = exit_config.get("exit_trend_ema_period", 120)
            current_instrument["exit_trend_ema"] = ExponentialMovingAverage(exit_trend_ema_period)
            if self.config.use_rsi_as_exit.get("enabled", False):
                rsi_exit_config = self.config.use_rsi_as_exit
                rsi_exit_period = rsi_exit_config.get("rsi_period", 20)
                current_instrument["rsi_exit"] = RelativeStrengthIndex(rsi_exit_period)
                
            # macd exit system
            if self.config.use_macd_exit_system.get("enabled", False):
                macd_exit_config = self.config.use_macd_exit_system
                macd_exit_fast = macd_exit_config.get("macd_fast_exit_period", 10)
                macd_exit_slow = macd_exit_config.get("macd_slow_exit_period", 32)
                macd_exit_signal = macd_exit_config.get("macd_signal_exit_period", 10)
                current_instrument["macd_exit"] = MovingAverageConvergenceDivergence(macd_exit_fast, macd_exit_slow)
                current_instrument["macd_exit_signal"] = ExponentialMovingAverage(macd_exit_signal)
                current_instrument["prev_macd_exit_line"] = None
                current_instrument["prev_macd_exit_signal"] = None
            current_instrument["prev_bar_close"] = None
            current_instrument["short_entry_price"] = None
            current_instrument["long_entry_price"] = None
            current_instrument["bars_since_entry"] = 0
            current_instrument["bars_above_ema"] = 0  # For trend following entry logic
            current_instrument["bars_below_ema"] = 0  # For trend following entry logic
            current_instrument["bars_above_reversion_ema"] = 0
            current_instrument["bars_below_reversion_ema"] = 0
            current_instrument["bars_over_ema_exit"] = 0
            current_instrument["bars_under_ema_exit"] = 0
            current_instrument["max_extreme_topt_long"] = None
            current_instrument["min_extreme_topt_short"] = None
            current_instrument["in_short_position"] = False
            current_instrument["in_long_position"] = False
            
            # rth
            current_instrument["only_trade_rth"] = self.config.only_trade_rth
            current_instrument["rth_start_hour"] = 14
            current_instrument["rth_start_minute"] = 30
            current_instrument["rth_end_hour"] = 21
            current_instrument["rth_end_minute"] = 0
            
            # toptrader metrics (for exit method only)
            current_instrument["sum_toptrader_long_short_ratio"] = 0.0
            current_instrument["count_long_short_ratio"] = 0.0

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

            # visualize - only show indicators for enabled systems
            if self.config.use_trend_following_setup.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("entry_trend_ema", 0)
            if self.config.use_close_ema.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("exit_trend_ema", 0)
            if self.config.use_spike_reversion_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("reversion_ema", 0)
            if self.config.use_htf_ema_bias_filter.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("htf_ema", 0)
            if self.config.use_directional_movement_filter.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("di_diff", 2)
            if self.config.use_rsi_simple_reversion_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("rsi", 1)
                usage_method = self.config.use_rsi_simple_reversion_system.get("usage_method", "execution")
                if usage_method == "condition":
                    current_instrument["collector"].initialise_logging_indicator("rsi_overbought_level", 1)
                    current_instrument["collector"].initialise_logging_indicator("rsi_oversold_level", 1)
            if self.config.use_macd_simple_reversion_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("macd", 1)
                current_instrument["collector"].initialise_logging_indicator("macd_signal", 1)
            if self.config.use_aroon_simple_trend_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("aroon_osc", 1)
            if self.config.use_donchian_breakout_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("donchian_upper", 0)
                current_instrument["collector"].initialise_logging_indicator("donchian_lower", 0)
                current_instrument["collector"].initialise_logging_indicator("donchian_middle", 0)
            if self.config.use_rsi_as_exit.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("rsi_exit", 1)
            if self.config.use_macd_exit_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("macd_exit", 1)
                current_instrument["collector"].initialise_logging_indicator("macd_exit_signal", 1)


    def on_start(self): 
        super().on_start()
        self._subscribe_to_metrics_data()
        
    def _subscribe_to_metrics_data(self):
        try:
            from nautilus_trader.model.data import DataType
            metrics_data_type = DataType(MetricsData)
            self.subscribe_data(data_type=metrics_data_type)
        except Exception as e:
            self.log.error(f"Failed to subscribe to MetricsData: {e}", LogColor.RED)

    def is_rth_time(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument["only_trade_rth"]:
            return True
            
        bar_time = datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=timezone.utc).time()
        rth_start = time(current_instrument["rth_start_hour"], current_instrument["rth_start_minute"])
        rth_end = time(current_instrument["rth_end_hour"], current_instrument["rth_end_minute"])
        
        return rth_start <= bar_time <= rth_end

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
        
        # Keep only 24 hours worth of 15-minute bars (24h * 4 bars/hour = 96 bars)
        max_bars = 96
        if len(volume_history) > max_bars:
            volume_history.pop(0)
            price_history.pop(0)
        
        # Calculate rolling 24h volume and dollar volume
        current_instrument["rolling_24h_volume"] = sum(volume_history)
        dollar_volumes = [vol * price for vol, price in zip(volume_history, price_history)]
        current_instrument["rolling_24h_dollar_volume"] = sum(dollar_volumes)

    def difference_topt_longshortratio(self, current_instrument: Dict[str, Any]) -> Optional[float]:
        if not self.config.use_topt_ratio_as_exit.get("enabled", False):
            return None

        toptrader_ratio = current_instrument.get("sum_toptrader_long_short_ratio", 0.0)
        retail_ratio = current_instrument.get("count_long_short_ratio", 0.0)
            
        if retail_ratio == 0 or toptrader_ratio == 0:
            return None

        difference = (toptrader_ratio - retail_ratio) / retail_ratio
        return difference

    def on_data(self, data) -> None:
        if isinstance(data, MetricsData):
            self.on_metrics_data(data)

    def on_metrics_data(self, metrics_data: MetricsData) -> None:
        instrument_id = metrics_data.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        
        if current_instrument is not None:
            current_instrument["latest_open_interest_value"] = metrics_data.sum_open_interest_value
            current_instrument["sum_toptrader_long_short_ratio"] = metrics_data.sum_toptrader_long_short_ratio
            current_instrument["count_long_short_ratio"] = metrics_data.count_long_short_ratio
            current_instrument["sum_taker_long_short_vol_ratio"] = getattr(metrics_data, 'sum_taker_long_short_vol_ratio', 0.0)

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

    def passes_directional_movement_filter(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not self.config.use_directional_movement_filter.get("enabled", False):
            return True
        
        dm = current_instrument["directional_movement"]
        if not dm.initialized:
            return False
        
        min_di_diff = current_instrument["min_di_diff"]
        di_diff = abs(dm.pos - dm.neg)
        return di_diff >= min_di_diff

    def passes_htf_ema_bias_filter(self, bar: Bar, current_instrument: Dict[str, Any], trade_direction: str) -> bool:
        if not self.config.use_htf_ema_bias_filter.get("enabled", False):
            return True
        
        htf_ema = current_instrument["htf_ema"]
        if not htf_ema.initialized:
            return True
        
        current_price = float(bar.close)
        ema_value = float(htf_ema.value)
        
        if trade_direction == "long":
            return current_price > ema_value
        elif trade_direction == "short":
            return current_price < ema_value
        
        return False

    def passes_rsi_condition_filter(self, bar: Bar, current_instrument: Dict[str, Any], trade_direction: str) -> bool:
        """
        RSI condition filter - only active when RSI usage_method is set to "condition"
        """
        if not self.config.use_rsi_simple_reversion_system.get("enabled", False):
            return True
            
        usage_method = self.config.use_rsi_simple_reversion_system.get("usage_method", "execution")
        if usage_method != "condition":
            return True
            
        rsi = current_instrument["rsi"]
        if not rsi.initialized:
            return True
            
        rsi_value = float(rsi.value)
        rsi_overbought = current_instrument["rsi_overbought"]
        rsi_oversold = current_instrument["rsi_oversold"]
        
        if trade_direction == "long":
            # For long trades, RSI should be oversold (good entry condition)
            return rsi_value <= rsi_oversold
        elif trade_direction == "short":
            # For short trades, RSI should be overbought (good entry condition)
            return rsi_value >= rsi_overbought
            
        return False

    def is_long_entry_allowed(self) -> bool:
        """
        Check if long entries are allowed based on configuration.
        When only_execute_short is True, all long entries will be blocked.
        """
        return not self.config.only_execute_short

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

    def check_time_based_exit(self, bar: Bar, current_instrument: Dict[str, Any], position) -> bool:
        if not self.config.hold_profit_for_remaining_days:
            return False
            
        instrument_id_str = str(bar.bar_type.instrument_id)
        base_symbol = instrument_id_str.split('-')[0]
        
        if base_symbol not in self.onboard_dates:
            return False
            
        onboard_date = self.onboard_dates[base_symbol]
        deadline = onboard_date + timedelta(days=13.5)
        
        current_time = datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=timezone.utc).replace(tzinfo=None)
        
        if current_time >= deadline:
            entry_price = position.avg_px_open
            current_price = float(bar.close)
            
            if position.side == PositionSide.LONG:
                is_profitable = current_price > entry_price
            else:
                is_profitable = current_price < entry_price
                
            return is_profitable
            
        return False

    def is_trading_allowed_after_listing(self, bar: Bar) -> bool:
        if not self.config.hold_profit_for_remaining_days:
            return True
            
        instrument_id_str = str(bar.bar_type.instrument_id)
        base_symbol = instrument_id_str.split('-')[0]
        
        if base_symbol not in self.onboard_dates:
            return True
            
        onboard_date = self.onboard_dates[base_symbol]
        deadline = onboard_date + timedelta(days=13.5)
        
        current_time = datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=timezone.utc).replace(tzinfo=None)
        
        # Block all new trades after deadline
        return current_time < deadline

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is None:
            self.log.warning(f"No instrument found for {instrument_id}", LogColor.RED)
            return

        if "atr" not in current_instrument:
            self.add_instrument_context()
    
        self.update_rolling_24h_volume(bar, current_instrument)
        
        # Always handle ATR (needed for stop loss)
        current_instrument["atr"].handle_bar(bar)
        
        if self.config.use_directional_movement_filter.get("enabled", False):
            current_instrument["directional_movement"].handle_bar(bar)
        
        if self.config.use_htf_ema_bias_filter.get("enabled", False):
            current_instrument["htf_ema"].handle_bar(bar)
        
        # Only handle indicators for enabled systems
        if self.config.use_trend_following_setup.get("enabled", False):
            entry_trend_ema = current_instrument["entry_trend_ema"]
            entry_trend_ema.handle_bar(bar)
        
        if self.config.use_close_ema.get("enabled", False):
            exit_trend_ema = current_instrument["exit_trend_ema"]
            exit_trend_ema.handle_bar(bar)
        
        if self.config.use_spike_reversion_system.get("enabled", False):
            current_instrument["spike_atr"].handle_bar(bar)
            reversion_ema = current_instrument["reversion_ema"]
            reversion_ema.handle_bar(bar)
        
        if self.config.use_rsi_simple_reversion_system.get("enabled", False):
            rsi = current_instrument["rsi"]
            rsi.handle_bar(bar)

        if self.config.use_macd_simple_reversion_system.get("enabled", False):
            macd = current_instrument["macd"]
            macd.handle_bar(bar)
            # Update signal line EMA with MACD value
            if macd.initialized:
                macd_signal_ema = current_instrument["macd_signal_ema"]
                macd_signal_ema.update_raw(macd.value)

        if self.config.use_donchian_breakout_system.get("enabled", False):
            donchian = current_instrument["donchian"]
            # Store previous values before updating for breakout detection
            if donchian.initialized:
                current_instrument["prev_donchian_upper"] = float(donchian.upper)
                current_instrument["prev_donchian_lower"] = float(donchian.lower)
            donchian.handle_bar(bar)

        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            aroon.handle_bar(bar)

        if self.config.use_rsi_as_exit.get("enabled", False):
            rsi_exit = current_instrument.get("rsi_exit")
            if rsi_exit:
                rsi_exit.handle_bar(bar)

        if self.config.use_macd_exit_system.get("enabled", False):
            macd_exit = current_instrument.get("macd_exit")
            macd_exit_signal = current_instrument.get("macd_exit_signal")
            if macd_exit and macd_exit_signal:
                macd_exit.handle_bar(bar)
                if macd_exit.initialized:
                    macd_exit_signal.update_raw(macd_exit.value)

        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

        if self.config.use_trend_following_setup.get("enabled", False):
            entry_trend_ema = current_instrument["entry_trend_ema"]
            if not entry_trend_ema.initialized:
                return
        
        if self.config.use_spike_reversion_system.get("enabled", False):
            reversion_ema = current_instrument["reversion_ema"]
            if not reversion_ema.initialized:
                return
            
        if self.config.use_rsi_simple_reversion_system.get("enabled", False):
            rsi = current_instrument["rsi"]
            if not rsi.initialized:
                return

        if self.config.use_macd_simple_reversion_system.get("enabled", False):
            macd = current_instrument["macd"]
            macd_signal_ema = current_instrument["macd_signal_ema"]
            if not macd.initialized or not macd_signal_ema.initialized:
                return

        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            if not aroon.initialized:
                return
        if self.config.use_donchian_breakout_system.get("enabled", False):
            donchian = current_instrument["donchian"]
            if not donchian.initialized:
                return

        if self.config.use_macd_exit_system.get("enabled", False):
            macd_exit = current_instrument.get("macd_exit")
            macd_exit_signal = current_instrument.get("macd_exit_signal")
            if not macd_exit or not macd_exit_signal or not macd_exit.initialized or not macd_exit_signal.initialized:
                return

        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        
        if not self.is_rth_time(bar, current_instrument):
            return

        if not self.passes_coin_filters(bar, current_instrument):
            return
        
        if not self.passes_directional_movement_filter(bar, current_instrument):
            return
        
        position = self.base_get_position(instrument_id)
        
        if position is not None and position.side == PositionSide.SHORT:
            self.short_exit_logic(bar, current_instrument, position)
            return
            
        if position is not None and position.side == PositionSide.LONG:
            self.long_exit_logic(bar, current_instrument, position)
            return
        
        # Block new trades after listing deadline
        if not self.is_trading_allowed_after_listing(bar):
            return
        
        self.donchian_breakout_setup(bar, current_instrument)
        self.aroon_simple_trend_setup(bar, current_instrument)
        self.macd_simple_reversion_setup(bar, current_instrument)
        self.spike_reversion_setup(bar, current_instrument)
        self.rsi_simple_reversion_setup(bar, current_instrument)
        self.trend_following_setup(bar, current_instrument)

    def donchian_breakout_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_donchian_breakout_system.get("enabled", False):
            return
        
        donchian = current_instrument["donchian"]
        if not donchian.initialized:
            return
            
        # Use previous Donchian values for breakout detection to avoid look-ahead bias
        if "prev_donchian_upper" not in current_instrument or "prev_donchian_lower" not in current_instrument:
            return  # Wait for at least one previous value
            
        donchian_upper = current_instrument["prev_donchian_upper"]
        donchian_lower = current_instrument["prev_donchian_lower"]
        bar_close = float(bar.close)
        min_breakout_strength = current_instrument["min_breakout_strength"]
        
        # Standard Donchian breakout with percentage strength filter
        if bar_close > donchian_upper:
            upper_breakout_strength = (bar_close - donchian_upper) / donchian_upper
            if (upper_breakout_strength >= min_breakout_strength and
                self.is_long_entry_allowed() and
                self.passes_htf_ema_bias_filter(bar, current_instrument, "long") and
                self.passes_rsi_condition_filter(bar, current_instrument, "long")):
                self.enter_long_donchian_breakout(bar, current_instrument)

        elif bar_close < donchian_lower:
            lower_breakout_strength = (donchian_lower - bar_close) / donchian_lower
            if (lower_breakout_strength >= min_breakout_strength and
                self.passes_htf_ema_bias_filter(bar, current_instrument, "short") and
                self.passes_rsi_condition_filter(bar, current_instrument, "short")):
                self.enter_short_donchian_breakout(bar, current_instrument)

    def enter_long_donchian_breakout(self, bar: Bar, current_instrument: Dict[str, Any]):  
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price - sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 0.98
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_long_market_order(instrument_id, qty)

    def enter_short_donchian_breakout(self, bar: Bar, current_instrument: Dict[str, Any]):   
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 1.02
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["min_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_short_market_order(instrument_id, qty)

    def aroon_simple_trend_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_aroon_simple_trend_system.get("enabled", False):
            return
        
        aroon = current_instrument["aroon"]
        if not aroon.initialized:
            return
            
        aroon_osc_value = float(aroon.value)
        long_threshold = current_instrument["aroon_osc_long_threshold"]
        short_threshold = current_instrument["aroon_osc_short_threshold"]
        
        if (aroon_osc_value >= long_threshold and 
            self.is_long_entry_allowed() and
            self.passes_htf_ema_bias_filter(bar, current_instrument, "long") and
            self.passes_rsi_condition_filter(bar, current_instrument, "long")):
            self.enter_long_aroon_trend(bar, current_instrument)
        elif (aroon_osc_value <= short_threshold and 
              self.passes_htf_ema_bias_filter(bar, current_instrument, "short") and
              self.passes_rsi_condition_filter(bar, current_instrument, "short")):
            self.enter_short_aroon_trend(bar, current_instrument)

    def enter_long_aroon_trend(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price - sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 0.98
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_long_market_order(instrument_id, qty)

    def enter_short_aroon_trend(self, bar: Bar, current_instrument: Dict[str, Any]):   
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 1.02
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["min_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_short_market_order(instrument_id, qty)

    def spike_reversion_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_spike_reversion_system.get("enabled", False):
            return
        
        spike_atr = current_instrument["spike_atr"]
        reversion_ema = current_instrument["reversion_ema"]
        
        if not spike_atr.initialized or not reversion_ema.initialized:
            return
            
        reversion_ema_value = float(reversion_ema.value)
        bar_close = float(bar.close)
        
        if bar_close >= reversion_ema_value:
            current_instrument["bars_above_reversion_ema"] += 1
            current_instrument["bars_below_reversion_ema"] = 0
        else:
            current_instrument["bars_below_reversion_ema"] += 1
            current_instrument["bars_above_reversion_ema"] = 0
            
        spike_atr_threshold = current_instrument["spike_atr_threshold"]
        prev_close = current_instrument.get("prev_bar_close")
        if prev_close is None:
            prev_close = float(bar.open) if bar.open is not None else float(bar.close)
        
        bar_tr = max(
            float(bar.high) - float(bar.low),
            abs(float(bar.high) - prev_close),
            abs(float(bar.low) - prev_close)
        )
        
        spike_atr_value = current_instrument["spike_atr"].value
        if spike_atr_value is None or spike_atr_value <= 0:
            return
            
        if bar_tr < (spike_atr_threshold * spike_atr_value):
            min_bars_spike_over_ema = self.config.use_spike_reversion_system.get("min_bars_spike_over_ema", 12)
            min_bars_spike_under_ema = self.config.use_spike_reversion_system.get("min_bars_spike_under_ema", 12)
            
            if (bar_close > reversion_ema_value and 
                current_instrument["bars_above_reversion_ema"] >= min_bars_spike_over_ema and
                self.passes_htf_ema_bias_filter(bar, current_instrument, "short") and
                self.passes_rsi_condition_filter(bar, current_instrument, "short")):
                self.spike_short_entry_logic(bar, current_instrument)
            elif (bar_close < reversion_ema_value and 
                  current_instrument["bars_below_reversion_ema"] >= min_bars_spike_under_ema and
                  self.is_long_entry_allowed() and
                  self.passes_htf_ema_bias_filter(bar, current_instrument, "long") and
                  self.passes_rsi_condition_filter(bar, current_instrument, "long")):
                self.spike_long_entry_logic(bar, current_instrument)

    def spike_short_entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 1.02
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["min_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_short_market_order(instrument_id, qty)

    def spike_long_entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price - sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 0.98
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_long_market_order(instrument_id, qty)
                

    def rsi_simple_reversion_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_rsi_simple_reversion_system.get("enabled", False):
            return
            
        rsi = current_instrument["rsi"]
        if not rsi.initialized:
            return
            
        usage_method = self.config.use_rsi_simple_reversion_system.get("usage_method", "execution")
        
        if usage_method == "execution":
            # Original behavior - RSI directly triggers trades
            rsi_value = float(rsi.value)
            rsi_overbought = current_instrument["rsi_overbought"]
            rsi_oversold = current_instrument["rsi_oversold"]
            
            # Immediate execution on extreme RSI levels - no minimum bars required
            if rsi_value >= rsi_overbought and self.passes_htf_ema_bias_filter(bar, current_instrument, "short"):
                self.enter_short_rsi_reversion(bar, current_instrument)
            elif rsi_value <= rsi_oversold and self.is_long_entry_allowed() and self.passes_htf_ema_bias_filter(bar, current_instrument, "long"):
                self.enter_long_rsi_reversion(bar, current_instrument)
        elif usage_method == "condition":
            # New behavior - RSI acts as a condition for other entry methods
            # The actual condition checking is done in passes_rsi_condition_filter method
            pass

    def enter_short_rsi_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 1.02
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_short_market_order(instrument_id, qty)

    def enter_long_rsi_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price - sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 0.98
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_long_market_order(instrument_id, qty)

    def macd_simple_reversion_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_macd_simple_reversion_system.get("enabled", False):
            return
            
        macd = current_instrument["macd"]
        macd_signal_ema = current_instrument["macd_signal_ema"]
        
        if not macd.initialized or not macd_signal_ema.initialized:
            return
        
        macd_line = float(macd.value)              # MACD line (fast line)
        signal_line = float(macd_signal_ema.value) # Signal line (slow line)
        
        prev_macd = current_instrument.get("prev_macd_line")
        prev_signal = current_instrument.get("prev_macd_signal")
        
        if prev_macd is not None and prev_signal is not None:            
            if (prev_macd <= prev_signal and macd_line > signal_line and 
                macd_line < 0 and signal_line < 0 and
                self.is_long_entry_allowed() and
                self.passes_htf_ema_bias_filter(bar, current_instrument, "long") and
                self.passes_rsi_condition_filter(bar, current_instrument, "long")):
                self.enter_long_macd_reversion(bar, current_instrument)
            
            elif (prev_macd >= prev_signal and macd_line < signal_line and
                  macd_line > 0 and signal_line > 0 and
                  self.passes_htf_ema_bias_filter(bar, current_instrument, "short") and
                  self.passes_rsi_condition_filter(bar, current_instrument, "short")):
                self.enter_short_macd_reversion(bar, current_instrument)
        
        current_instrument["prev_macd_line"] = macd_line
        current_instrument["prev_macd_signal"] = signal_line

    def enter_long_macd_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price - sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 0.98
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_long_market_order(instrument_id, qty)

    def enter_short_macd_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        # Calculate ATR-based stop loss
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            # Fallback to 2% stop loss if ATR not available
            stop_loss_price = entry_price * 1.02
        
        # Calculate risk-based position size
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = entry_price
        current_instrument["bars_since_entry"] = 0
        current_instrument["min_topt_difference_since_entry"] = None
        current_instrument["sl_price"] = stop_loss_price
        self.order_types.submit_short_market_order(instrument_id, qty)

    def trend_following_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_trend_following_setup.get("enabled", False):
            return
        entry_trend_ema_value = current_instrument["entry_trend_ema"].value
        if entry_trend_ema_value is None:
            return
        
        prev_bar_close = current_instrument.get("prev_bar_close")
        if prev_bar_close is None:
            current_instrument["prev_bar_close"] = float(bar.close)
            return

        prev_bar_close_f = float(prev_bar_close)
        bar_close_f = float(bar.close)
        ema_f = float(entry_trend_ema_value)
        
        if bar_close_f >= ema_f:
            current_instrument["bars_above_ema"] += 1
            self.trend_long_entry_logic(bar, current_instrument, prev_bar_close_f, bar_close_f, ema_f)
            current_instrument["bars_below_ema"] = 0
        else:
            current_instrument["bars_below_ema"] += 1
            self.trend_short_entry_logic(bar, current_instrument, prev_bar_close_f, bar_close_f, ema_f)
            current_instrument["bars_above_ema"] = 0
        
        current_instrument["prev_bar_close"] = bar_close_f

    def trend_long_entry_logic(self, bar: Bar, current_instrument: Dict[str, Any], prev_bar_close: float, bar_close: float, ema_value: float):
        min_bars_under_ema = self.config.use_trend_following_setup.get("min_bars_under_ema", 20)
        if (prev_bar_close < ema_value and bar_close >= ema_value and 
            current_instrument["bars_below_ema"] >= min_bars_under_ema and
            self.is_long_entry_allowed() and
            self.passes_htf_ema_bias_filter(bar, current_instrument, "long") and
            self.passes_rsi_condition_filter(bar, current_instrument, "long")):
            
            instrument_id = bar.bar_type.instrument_id
            entry_price = bar_close
            
            # Calculate ATR-based stop loss
            atr_value = current_instrument["atr"].value
            sl_atr_multiple = current_instrument["sl_atr_multiple"]
            if atr_value is not None:
                stop_loss_price = entry_price - sl_atr_multiple * atr_value
            else:
                # Fallback to 2% stop loss if ATR not available
                stop_loss_price = entry_price * 0.98
            
            # Calculate risk-based position size
            qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
            
            current_instrument["in_long_position"] = True
            current_instrument["long_entry_price"] = entry_price
            current_instrument["bars_since_entry"] = 0
            current_instrument["sl_price"] = stop_loss_price
            self.order_types.submit_long_market_order(instrument_id, qty)

    def trend_short_entry_logic(self, bar: Bar, current_instrument: Dict[str, Any], prev_bar_close: float, bar_close: float, ema_value: float):
        min_bars_over_ema = self.config.use_trend_following_setup.get("min_bars_over_ema", 20)
        if (prev_bar_close >= ema_value and bar_close < ema_value and 
            current_instrument["bars_above_ema"] >= min_bars_over_ema and
            self.passes_htf_ema_bias_filter(bar, current_instrument, "short") and
            self.passes_rsi_condition_filter(bar, current_instrument, "short")):
            
            instrument_id = bar.bar_type.instrument_id
            entry_price = bar_close
            
            # Calculate ATR-based stop loss
            atr_value = current_instrument["atr"].value
            sl_atr_multiple = current_instrument["sl_atr_multiple"]
            if atr_value is not None:
                stop_loss_price = entry_price + sl_atr_multiple * atr_value
            else:
                # Fallback to 2% stop loss if ATR not available
                stop_loss_price = entry_price * 1.02
            
            # Calculate risk-based position size
            qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
            
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["bars_since_entry"] = 0
            current_instrument["sl_price"] = stop_loss_price
            self.order_types.submit_short_market_order(instrument_id, qty)

    def long_exit_logic(self, bar: Bar, current_instrument: Dict[str, Any], position):
        current_instrument["bars_since_entry"] += 1
        sl_price = current_instrument.get("sl_price")
        instrument_id = bar.bar_type.instrument_id
        
        # Always check stop loss first (highest priority)
        if sl_price is not None and float(bar.close) <= sl_price:
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_short_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        # Check time-based exit (overrides all other exits if enabled)
        if self.check_time_based_exit(bar, current_instrument, position):
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_short_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        # Skip all other exits if time-based exit is enabled but deadline not reached
        if self.config.hold_profit_for_remaining_days:
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        should_exit = False
        
        if self.config.use_close_ema.get("enabled", False):
            if self.check_ema_exit_long(bar, current_instrument):
                should_exit = True
        
        if not should_exit and self.config.use_topt_ratio_as_exit.get("enabled", False):
            if self.check_topt_ratio_exit_long(bar, current_instrument):
                should_exit = True
        
        if not should_exit and self.config.use_fixed_rr.get("enabled", False):
            if self.check_fixed_rr_exit_long(bar, current_instrument, position):
                should_exit = True
        
        if not should_exit and self.config.use_macd_exit_system.get("enabled", False):
            if self.check_macd_exit_long(bar, current_instrument):
                should_exit = True
        
        # Execute exit if any method triggered
        if should_exit:
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_short_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
        
        current_instrument["prev_bar_close"] = float(bar.close)

    def short_exit_logic(self, bar: Bar, current_instrument: Dict[str, Any], position):
        current_instrument["bars_since_entry"] += 1
        sl_price = current_instrument.get("sl_price")
        instrument_id = bar.bar_type.instrument_id
        
        # Always check stop loss first (highest priority)
        if sl_price is not None and float(bar.close) >= sl_price:
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_long_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        # Check time-based exit (overrides all other exits if enabled)
        if self.check_time_based_exit(bar, current_instrument, position):
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_long_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        # Skip all other exits if time-based exit is enabled but deadline not reached
        if self.config.hold_profit_for_remaining_days:
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        should_exit = False
        
        if self.config.use_close_ema.get("enabled", False):
            if self.check_ema_exit_short(bar, current_instrument):
                should_exit = True
        
        if not should_exit and self.config.use_rsi_as_exit.get("enabled", False):
            if self.check_rsi_exit_short(bar, current_instrument):
                should_exit = True
        
        if not should_exit and self.config.use_topt_ratio_as_exit.get("enabled", False):
            if self.check_topt_ratio_exit_short(bar, current_instrument):
                should_exit = True
        
        if not should_exit and self.config.use_fixed_rr.get("enabled", False):
            if self.check_fixed_rr_exit_short(bar, current_instrument, position):
                should_exit = True
        
        if not should_exit and self.config.use_macd_exit_system.get("enabled", False):
            if self.check_macd_exit_short(bar, current_instrument):
                should_exit = True
        
        # Execute exit if any method triggered
        if should_exit:
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_long_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
        
        current_instrument["prev_bar_close"] = float(bar.close)

    def reset_position_tracking(self, current_instrument: Dict[str, Any]):
        current_instrument["short_entry_price"] = None
        current_instrument["long_entry_price"] = None
        current_instrument["bars_since_entry"] = 0
        current_instrument["sl_price"] = None
        current_instrument["in_short_position"] = False
        current_instrument["in_long_position"] = False
        current_instrument["max_extreme_topt_long"] = None
        current_instrument["min_extreme_topt_short"] = None
        current_instrument["bars_over_ema_exit"] = 0
        current_instrument["bars_under_ema_exit"] = 0
        current_instrument["ema_exit_qualified"] = False

    def check_ema_exit_long(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        exit_trend_ema = current_instrument["exit_trend_ema"]
        
        if not exit_trend_ema.initialized:
            return False
            
        current_price = float(bar.close)
        ema_value = float(exit_trend_ema.value)
        min_bars = self.config.use_close_ema.get("min_bars_under_ema", 40)

        if "ema_exit_qualified" not in current_instrument:
            current_instrument["ema_exit_qualified"] = False
        if "bars_under_ema_exit" not in current_instrument:
            current_instrument["bars_under_ema_exit"] = 0
        if "bars_over_ema_exit" not in current_instrument:
            current_instrument["bars_over_ema_exit"] = 0
        
        if current_price > ema_value:
            current_instrument["bars_over_ema_exit"] += 1
            current_instrument["bars_under_ema_exit"] = 0
            
            if current_instrument["bars_over_ema_exit"] >= min_bars:
                current_instrument["ema_exit_qualified"] = True
        else:
            current_instrument["bars_under_ema_exit"] += 1
            current_instrument["bars_over_ema_exit"] = 0
            
            if current_instrument["ema_exit_qualified"] and current_price <= ema_value:
                current_instrument["ema_exit_qualified"] = False
                return True

        return False

    def check_ema_exit_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        exit_trend_ema = current_instrument["exit_trend_ema"]
        
        if not exit_trend_ema.initialized:
            return False
            
        current_price = float(bar.close)
        ema_value = float(exit_trend_ema.value)
        min_bars = self.config.use_close_ema.get("min_bars_over_ema", 40)

        if "ema_exit_qualified" not in current_instrument:
            current_instrument["ema_exit_qualified"] = False
        if "bars_under_ema_exit" not in current_instrument:
            current_instrument["bars_under_ema_exit"] = 0
        if "bars_over_ema_exit" not in current_instrument:
            current_instrument["bars_over_ema_exit"] = 0
        
        if current_price < ema_value:
            current_instrument["bars_under_ema_exit"] += 1
            current_instrument["bars_over_ema_exit"] = 0
            
            if current_instrument["bars_under_ema_exit"] >= min_bars:
                current_instrument["ema_exit_qualified"] = True
        else:
            current_instrument["bars_over_ema_exit"] += 1
            current_instrument["bars_under_ema_exit"] = 0
            
            if current_instrument["ema_exit_qualified"] and current_price >= ema_value:
                current_instrument["ema_exit_qualified"] = False
                return True

        return False

    def check_topt_ratio_exit_long(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        min_reversal = self.config.use_topt_ratio_as_exit.get("long_min_extreme_reversal_topt_longshortratio", 0.3)
        
        divergence = self.difference_topt_longshortratio(current_instrument)
        if divergence is None:
            return False
        
        # Track maximum extreme divergence reached
        max_extreme = current_instrument.get("max_extreme_topt_long")
        if max_extreme is None or divergence > max_extreme:
            current_instrument["max_extreme_topt_long"] = divergence
            max_extreme = divergence
        
        # Exit if divergence has decreased by minimum reversal amount
        return max_extreme is not None and (max_extreme - divergence) >= min_reversal

    def check_topt_ratio_exit_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        min_reversal = self.config.use_topt_ratio_as_exit.get("short_min_extreme_reversal_topt_longshortratio", 0.3)
        
        divergence = self.difference_topt_longshortratio(current_instrument)
        if divergence is None:
            return False
        
        # Track minimum extreme divergence reached (most negative)
        min_extreme = current_instrument.get("min_extreme_topt_short")
        if min_extreme is None or divergence < min_extreme:
            current_instrument["min_extreme_topt_short"] = divergence
            min_extreme = divergence
        
        # Exit if divergence has increased by minimum reversal amount (become less negative)
        return min_extreme is not None and (divergence - min_extreme) >= min_reversal

    def check_fixed_rr_exit_long(self, bar: Bar, current_instrument: Dict[str, Any], position) -> bool:
        entry_price = current_instrument.get("long_entry_price")
        if entry_price is None:
            entry_price = float(position.avg_px_open) if hasattr(position, 'avg_px_open') else None
        
        sl_price = current_instrument.get("sl_price")
        if entry_price is None or sl_price is None:
            return False
            
        current_price = float(bar.close)
        rr_ratio = self.config.use_fixed_rr.get("rr_tp_ratio", 1.5)
        
        risk = entry_price - sl_price
        
        target_price = entry_price + (risk * rr_ratio)
        
        return current_price >= target_price

    def check_fixed_rr_exit_short(self, bar: Bar, current_instrument: Dict[str, Any], position) -> bool:
        entry_price = current_instrument.get("short_entry_price")
        if entry_price is None:
            entry_price = float(position.avg_px_open) if hasattr(position, 'avg_px_open') else None
        
        sl_price = current_instrument.get("sl_price")
        if entry_price is None or sl_price is None:
            return False
            
        current_price = float(bar.close)
        rr_ratio = self.config.use_fixed_rr.get("rr_tp_ratio", 1.5)
        
        # Calculate risk amount
        risk = sl_price - entry_price
        
        # Calculate target price
        target_price = entry_price - (risk * rr_ratio)
        
        # Exit if target is reached
        return current_price <= target_price

    def check_rsi_exit_long(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        rsi_exit = current_instrument.get("rsi_exit")
        if not rsi_exit or not rsi_exit.initialized:
            return False
        
        rsi_value = float(rsi_exit.value)
        rsi_long_exit_threshold = self.config.use_rsi_as_exit.get("rsi_long_exit_threshold", 0.7)
        
        # Exit long position when RSI is overbought (momentum exhaustion)
        return rsi_value >= rsi_long_exit_threshold

    def check_rsi_exit_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        rsi_exit = current_instrument.get("rsi_exit")
        if not rsi_exit or not rsi_exit.initialized:
            return False
        
        rsi_value = float(rsi_exit.value)
        rsi_short_exit_threshold = self.config.use_rsi_as_exit.get("rsi_short_exit_threshold", 0.3)
        
        # Exit short position when RSI is oversold (downside momentum exhaustion)
        return rsi_value <= rsi_short_exit_threshold

    def check_macd_exit_long(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        """
        Long exit: When fast MACD line crosses slow MACD line above 0 line (from above to below)
        """
        macd_exit = current_instrument.get("macd_exit")
        macd_exit_signal = current_instrument.get("macd_exit_signal")
        
        if not macd_exit or not macd_exit_signal or not macd_exit.initialized or not macd_exit_signal.initialized:
            return False
        
        macd_line = float(macd_exit.value)  # Fast line
        signal_line = float(macd_exit_signal.value)  # Slow line
        
        prev_macd = current_instrument.get("prev_macd_exit_line")
        prev_signal = current_instrument.get("prev_macd_exit_signal")
        
        # Store current values for next bar
        current_instrument["prev_macd_exit_line"] = macd_line
        current_instrument["prev_macd_exit_signal"] = signal_line
        
        if prev_macd is None or prev_signal is None:
            return False
        
        above_zero = macd_line > 0 and signal_line > 0
        bearish_crossover = prev_macd > prev_signal and macd_line <= signal_line
        
        return above_zero and bearish_crossover

    def check_macd_exit_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        macd_exit = current_instrument.get("macd_exit")
        macd_exit_signal = current_instrument.get("macd_exit_signal")
        
        if not macd_exit or not macd_exit_signal or not macd_exit.initialized or not macd_exit_signal.initialized:
            return False
        
        macd_line = float(macd_exit.value)  # Fast line
        signal_line = float(macd_exit_signal.value)  # Slow line
        
        prev_macd = current_instrument.get("prev_macd_exit_line")
        prev_signal = current_instrument.get("prev_macd_exit_signal")
        
        # Store current values for next bar
        current_instrument["prev_macd_exit_line"] = macd_line
        current_instrument["prev_macd_exit_signal"] = signal_line
        
        if prev_macd is None or prev_signal is None:
            return False
        
        below_zero = macd_line < 0 and signal_line < 0
        bullish_crossover = prev_macd < prev_signal and macd_line >= signal_line
        
        return below_zero and bullish_crossover

    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)

        # Only visualize indicators for enabled systems
        if self.config.use_trend_following_setup.get("enabled", False):
            entry_trend_ema_value = float(current_instrument["entry_trend_ema"].value) if current_instrument["entry_trend_ema"].value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="entry_trend_ema", value=entry_trend_ema_value)
        
        if self.config.use_close_ema.get("enabled", False):
            exit_trend_ema_value = float(current_instrument["exit_trend_ema"].value) if current_instrument["exit_trend_ema"].value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="exit_trend_ema", value=exit_trend_ema_value)
        
        # Spike reversion EMA (position 0)
        if self.config.use_spike_reversion_system.get("enabled", False):
            reversion_ema_value = float(current_instrument["reversion_ema"].value) if current_instrument["reversion_ema"].value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="reversion_ema", value=reversion_ema_value)

        # HTF EMA bias filter (position 0)
        if self.config.use_htf_ema_bias_filter.get("enabled", False):
            htf_ema_value = float(current_instrument["htf_ema"].value) if current_instrument["htf_ema"].value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="htf_ema", value=htf_ema_value)

        # Directional Movement difference (position 1)
        if self.config.use_directional_movement_filter.get("enabled", False):
            dm = current_instrument["directional_movement"]
            if dm and dm.initialized:
                di_diff_value = abs(dm.pos - dm.neg)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="di_diff", value=di_diff_value)
            else:
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="di_diff", value=None)

        # RSI for reversion system (position 1)
        if self.config.use_rsi_simple_reversion_system.get("enabled", False):
            rsi_value = float(current_instrument["rsi"].value) if current_instrument["rsi"].value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="rsi", value=rsi_value)
            
            # Add condition mode visualization
            usage_method = self.config.use_rsi_simple_reversion_system.get("usage_method", "execution")
            if usage_method == "condition":
                rsi_overbought = current_instrument["rsi_overbought"]
                rsi_oversold = current_instrument["rsi_oversold"]
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="rsi_overbought_level", value=rsi_overbought)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="rsi_oversold_level", value=rsi_oversold)
        
        # MACD for reversion system (position 1)
        if self.config.use_macd_simple_reversion_system.get("enabled", False):
            macd = current_instrument["macd"]
            macd_signal_ema = current_instrument["macd_signal_ema"]
            if macd and macd.value is not None and macd_signal_ema and macd_signal_ema.value is not None:
                macd_value = float(macd.value)
                signal_value = float(macd_signal_ema.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd", value=macd_value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_signal", value=signal_value)

        # Aroon Oscillator (position 1)
        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            aroon_osc_value = float(aroon.value) if aroon.value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="aroon_osc", value=aroon_osc_value)

        # Donchian Channel (position 0)
        if self.config.use_donchian_breakout_system.get("enabled", False):
            donchian = current_instrument["donchian"]
            donchian_upper_value = float(donchian.upper) if donchian.upper is not None else None
            donchian_lower_value = float(donchian.lower) if donchian.lower is not None else None
            donchian_middle_value = float(donchian.middle) if donchian.middle is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="donchian_upper", value=donchian_upper_value)
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="donchian_lower", value=donchian_lower_value)
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="donchian_middle", value=donchian_middle_value)

        # RSI for exit method (position 1)
        if self.config.use_rsi_as_exit.get("enabled", False):       
            rsi_exit = current_instrument.get("rsi_exit")
            if rsi_exit and rsi_exit.value is not None:
                rsi_exit_value = float(rsi_exit.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="rsi_exit", value=rsi_exit_value)
        
        # MACD for exit method (position 1)
        if self.config.use_macd_exit_system.get("enabled", False):
            macd_exit = current_instrument.get("macd_exit")
            macd_exit_signal = current_instrument.get("macd_exit_signal")
            if macd_exit and macd_exit.value is not None and macd_exit_signal and macd_exit_signal.value is not None:
                macd_exit_value = float(macd_exit.value)
                macd_exit_signal_value = float(macd_exit_signal.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_exit", value=macd_exit_value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_exit_signal", value=macd_exit_signal_value)
        
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        instrument_id = position_closed.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is not None:
            self.reset_position_tracking(current_instrument)
            current_instrument["bars_above_ema"] = 0
            current_instrument["bars_below_ema"] = 0
            current_instrument["bars_above_reversion_ema"] = 0
            current_instrument["bars_below_reversion_ema"] = 0
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: Optional[InstrumentId] = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)
