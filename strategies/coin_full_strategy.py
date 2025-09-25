# in here is the coin short strategy to short coins that have been listed for 14 days
from datetime import datetime, time, timezone
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
            "rsi_exit_threshold": 0.5
        }
    )

    use_topt_ratio_as_exit: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "short_min_extreme_reversal_topt_longshortratio": 0.3,
            "long_min_extreme_reversal_topt_longshortratio": 0.3
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

    only_trade_rth: bool = False
    close_positions_on_stop: bool = True


class CoinFullStrategy(BaseStrategy,Strategy):
    def __init__(self, config: CoinFullConfig):
        super().__init__(config)
        self.risk_manager = RiskManager(config)
        self.order_types = OrderTypes(self) 
        self.add_instrument_context()
    
    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            # risk management
            current_instrument["atr"] = AverageTrueRange(self.config.atr_period)
            current_instrument["sl_atr_multiple"] = self.config.sl_atr_multiple
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
            # Create MACD line (fast MA - slow MA)
            current_instrument["macd"] = MovingAverageConvergenceDivergence(macd_fast_period, macd_slow_period)
            # Create signal line (EMA of MACD line)
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
            if self.config.use_macd_simple_reversion_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("macd", 1)
                current_instrument["collector"].initialise_logging_indicator("macd_signal", 1)
            if self.config.use_rsi_as_exit.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("rsi_exit", 1)

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

        if self.config.use_rsi_as_exit.get("enabled", False):
            rsi_exit = current_instrument.get("rsi_exit")
            if rsi_exit:
                rsi_exit.handle_bar(bar)

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

        self.macd_simple_reversion_setup(bar, current_instrument)
        self.spike_reversion_setup(bar, current_instrument)
        self.rsi_simple_reversion_setup(bar, current_instrument)
        self.trend_following_setup(bar, current_instrument)

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
                self.passes_htf_ema_bias_filter(bar, current_instrument, "short")):
                self.spike_short_entry_logic(bar, current_instrument)
            elif (bar_close < reversion_ema_value and 
                  current_instrument["bars_below_reversion_ema"] >= min_bars_spike_under_ema and
                  self.passes_htf_ema_bias_filter(bar, current_instrument, "long")):
                self.spike_long_entry_logic(bar, current_instrument)

    def spike_short_entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = float(bar.close)
        current_instrument["bars_since_entry"] = 0
        current_instrument["min_topt_difference_since_entry"] = None
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            current_instrument["sl_price"] = float(bar.close) + sl_atr_multiple * atr_value
        else:
            current_instrument["sl_price"] = None
        self.order_types.submit_short_market_order(instrument_id, int(qty))

    def spike_long_entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = float(bar.close)
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            current_instrument["sl_price"] = float(bar.close) - sl_atr_multiple * atr_value
        else:
            current_instrument["sl_price"] = None
        self.order_types.submit_long_market_order(instrument_id, int(qty))
                

    def rsi_simple_reversion_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_rsi_simple_reversion_system.get("enabled", False):
            return
            
        rsi = current_instrument["rsi"]
        if not rsi.initialized:
            return
            
        rsi_value = float(rsi.value)
        rsi_overbought = current_instrument["rsi_overbought"]
        rsi_oversold = current_instrument["rsi_oversold"]
        
        # Immediate execution on extreme RSI levels - no minimum bars required
        if rsi_value >= rsi_overbought and self.passes_htf_ema_bias_filter(bar, current_instrument, "short"):
            self.enter_short_rsi_reversion(bar, current_instrument)
        elif rsi_value <= rsi_oversold and self.passes_htf_ema_bias_filter(bar, current_instrument, "long"):
            self.enter_long_rsi_reversion(bar, current_instrument)

    def enter_short_rsi_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = float(bar.close)
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            current_instrument["sl_price"] = float(bar.close) + sl_atr_multiple * atr_value
        else:
            current_instrument["sl_price"] = None
        self.order_types.submit_short_market_order(instrument_id, int(qty))

    def enter_long_rsi_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = float(bar.close)
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            current_instrument["sl_price"] = float(bar.close) - sl_atr_multiple * atr_value
        else:
            current_instrument["sl_price"] = None
        self.order_types.submit_long_market_order(instrument_id, int(qty))

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
                self.passes_htf_ema_bias_filter(bar, current_instrument, "long")):
                self.enter_long_macd_reversion(bar, current_instrument)
            
            elif (prev_macd >= prev_signal and macd_line < signal_line and
                  macd_line > 0 and signal_line > 0 and
                  self.passes_htf_ema_bias_filter(bar, current_instrument, "short")):
                self.enter_short_macd_reversion(bar, current_instrument)
        
        current_instrument["prev_macd_line"] = macd_line
        current_instrument["prev_macd_signal"] = signal_line

    def enter_long_macd_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
        
        current_instrument["in_long_position"] = True
        current_instrument["long_entry_price"] = float(bar.close)
        current_instrument["bars_since_entry"] = 0
        current_instrument["max_topt_difference_since_entry"] = None
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            current_instrument["sl_price"] = float(bar.close) - sl_atr_multiple * atr_value
        else:
            current_instrument["sl_price"] = None
        self.order_types.submit_long_market_order(instrument_id, int(qty))

    def enter_short_macd_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
        
        current_instrument["in_short_position"] = True
        current_instrument["short_entry_price"] = float(bar.close)
        current_instrument["bars_since_entry"] = 0
        current_instrument["min_topt_difference_since_entry"] = None
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            current_instrument["sl_price"] = float(bar.close) + sl_atr_multiple * atr_value
        else:
            current_instrument["sl_price"] = None
        self.order_types.submit_short_market_order(instrument_id, int(qty))

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
            self.passes_htf_ema_bias_filter(bar, current_instrument, "long")):
            instrument_id = bar.bar_type.instrument_id
            trade_size_usdt = float(current_instrument["trade_size_usdt"])
            qty = max(1, trade_size_usdt / bar_close)
            
            current_instrument["in_long_position"] = True
            current_instrument["long_entry_price"] = bar_close
            current_instrument["bars_since_entry"] = 0
            atr_value = current_instrument["atr"].value
            sl_atr_multiple = current_instrument["sl_atr_multiple"]
            if atr_value is not None:
                current_instrument["sl_price"] = bar_close - sl_atr_multiple * atr_value
            else:
                current_instrument["sl_price"] = None
            self.order_types.submit_long_market_order(instrument_id, int(qty))

    def trend_short_entry_logic(self, bar: Bar, current_instrument: Dict[str, Any], prev_bar_close: float, bar_close: float, ema_value: float):
        min_bars_over_ema = self.config.use_trend_following_setup.get("min_bars_over_ema", 20)
        if (prev_bar_close >= ema_value and bar_close < ema_value and 
            current_instrument["bars_above_ema"] >= min_bars_over_ema and
            self.passes_htf_ema_bias_filter(bar, current_instrument, "short")):
            instrument_id = bar.bar_type.instrument_id
            trade_size_usdt = float(current_instrument["trade_size_usdt"])
            qty = max(1, trade_size_usdt / bar_close)
            
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = bar_close
            current_instrument["bars_since_entry"] = 0
            atr_value = current_instrument["atr"].value
            sl_atr_multiple = current_instrument["sl_atr_multiple"]
            if atr_value is not None:
                current_instrument["sl_price"] = bar_close + sl_atr_multiple * atr_value
            else:
                current_instrument["sl_price"] = None
            self.order_types.submit_short_market_order(instrument_id, int(qty))

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
        min_bars = self.config.use_close_ema.get("min_bars_over_ema", 35)
        
        if "ema_exit_qualified" not in current_instrument:
            current_instrument["ema_exit_qualified"] = False
        
        if current_price > ema_value:
            current_instrument["bars_over_ema_exit"] += 1
            current_instrument["bars_under_ema_exit"] = 0
            
            if current_instrument["bars_over_ema_exit"] >= min_bars:
                current_instrument["ema_exit_qualified"] = True
                
        else:
            current_instrument["bars_under_ema_exit"] += 1
            current_instrument["bars_over_ema_exit"] = 0
            
            if current_instrument["ema_exit_qualified"] and current_price <= ema_value:
                current_instrument["ema_exit_qualified"] = False  # Reset for next trade
                return True
                
        return False

    def check_ema_exit_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        exit_trend_ema = current_instrument["exit_trend_ema"]
        
        if not exit_trend_ema.initialized:
            return False
            
        current_price = float(bar.close)
        ema_value = float(exit_trend_ema.value)
        min_bars = self.config.use_close_ema.get("min_bars_under_ema", 35)
        
        if "ema_exit_qualified" not in current_instrument:
            current_instrument["ema_exit_qualified"] = False
        
        # EVERY bar: check if above or below EMA
        if current_price < ema_value:
            current_instrument["bars_under_ema_exit"] += 1
            current_instrument["bars_over_ema_exit"] = 0
            
            if current_instrument["bars_under_ema_exit"] >= min_bars:
                current_instrument["ema_exit_qualified"] = True
                
        else:
            current_instrument["bars_over_ema_exit"] += 1
            current_instrument["bars_under_ema_exit"] = 0
            
            if current_instrument["ema_exit_qualified"] and current_price >= ema_value:
                current_instrument["ema_exit_qualified"] = False  # Reset for next trade
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
        rsi_threshold = self.config.use_rsi_as_exit.get("rsi_exit_threshold", 0.5)
        
        # Exit long position when RSI crosses below threshold (momentum weakening)
        return rsi_value <= rsi_threshold

    def check_rsi_exit_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        rsi_exit = current_instrument.get("rsi_exit")
        if not rsi_exit or not rsi_exit.initialized:
            return False
        
        rsi_value = float(rsi_exit.value)
        rsi_threshold = self.config.use_rsi_as_exit.get("rsi_exit_threshold", 0.5)
        
        # Exit short position when RSI crosses above threshold (momentum weakening)
        return rsi_value >= rsi_threshold

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
        
        # MACD for reversion system (position 1)
        if self.config.use_macd_simple_reversion_system.get("enabled", False):
            macd = current_instrument["macd"]
            macd_signal_ema = current_instrument["macd_signal_ema"]
            if macd and macd.value is not None and macd_signal_ema and macd_signal_ema.value is not None:
                macd_value = float(macd.value)
                signal_value = float(macd_signal_ema.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd", value=macd_value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_signal", value=signal_value)
        
        # RSI for exit method (position 1)
        if self.config.use_rsi_as_exit.get("enabled", False):
            rsi_exit = current_instrument.get("rsi_exit")
            if rsi_exit and rsi_exit.value is not None:
                rsi_exit_value = float(rsi_exit.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="rsi_exit", value=rsi_exit_value)
        
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
