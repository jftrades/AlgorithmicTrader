from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List, Union
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.common.enums import LogColor
from pydantic import Field
from decimal import Decimal
from nautilus_trader.indicators.volatility import AverageTrueRange
from nautilus_trader.indicators.averages import ExponentialMovingAverage
from nautilus_trader.indicators.trend import MovingAverageConvergenceDivergence
from nautilus_trader.indicators.momentum import RelativeStrengthIndex
from nautilus_trader.indicators.trend import DirectionalMovement
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
# from nautilus_trader.model.data import DataType
# from data.download.crypto_downloads.custom_class.bybit_metrics_data import BybitMetricsData


class ShortThaBitchStratConfig(StrategyConfig):
    instruments:List[dict]
    min_account_balance: float
    run_id: str
    sl_atr_multiple: float = 2.0
    atr_period: int = 14
    time_after_listing_close: Union[int, List[float]] = Field(default=14)

    exp_growth_atr_risk: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
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

    use_macd_exit_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "macd_fast_exit_period": 10,
            "macd_slow_exit_period": 32,
            "macd_signal_exit_period": 10
        }
    )

    use_trailing_stop_exit: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "atr_multiple": 2.0,
            "activation_profit_atr": 1.0  # activate trailing after X ATR profit
        }
    )

    use_htf_ema_bias_filter: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "ema_period": 200
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

    use_rsi_simple_reversion_system: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "usage_method": "condition",  # "execution" or "condition"
            "rsi_period": 20,
            "rsi_overbought": 0.7,
            "rsi_oversold": 0.3
        }
    )

    atr_burst_entry: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "atr_period_calc": 40,
            "tr_lb": 3,
            "atr_burst_threshold": 10,
            "waiting_bars_after_burst": 5
        }
    )

    btc_regime_filter: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "ema_period": 200,
            "only_short_below_ema": True
        }
    )

    relative_strength_entry: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "lookback_bars": 10,
            "weakness_threshold": -0.02
        }
    )

    directional_movement_filter: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "period": 14,
            "min_di_diff": 0.02,
            "require_minus_di_above": True
        }
    )

    retest_entry: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "breakdown_ema_period": 50,
            "max_retest_bars": 10,
            "retest_tolerance_atr": 0.3
        }
    )

    only_execute_short: bool = False
    hold_profit_for_remaining_days: bool = False
    close_positions_on_stop: bool = True
    max_concurrent_positions: int = 50
    max_leverage: Decimal = 10.0

class ShortThaBitchStrat(BaseStrategy, Strategy):
    def __init__(self, config: ShortThaBitchStratConfig):
        super().__init__(config)
        self.risk_manager = RiskManager(config)
        self.risk_manager.set_strategy(self)    
        self.risk_manager.set_max_leverage(Decimal(str(config.max_leverage)))
        self.order_types = OrderTypes(self) 
        self.onboard_dates = self.load_onboard_dates()
        self._init_relative_strength()
        self.add_instrument_context()

    def _init_relative_strength(self):
        rs_config = self.config.relative_strength_entry if isinstance(self.config.relative_strength_entry, dict) else {}
        if rs_config.get("enabled", False):
            lookback = rs_config.get("lookback_bars", 10)
            self.btc_price_history = []
            self.btc_lookback = lookback
            self.btc_current_price = None
        else:
            self.btc_price_history = []
            self.btc_lookback = 10
            self.btc_current_price = None

    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            # das hier drunter nur ATR
            atr_period = self.config.atr_period
            
            # Handle exp_growth_atr_risk - check if it's a dict (might be FieldInfo if not in YAML)
            exp_growth_config = self.config.exp_growth_atr_risk if isinstance(self.config.exp_growth_atr_risk, dict) else {}
            log_growth_config = self.config.log_growth_atr_risk if isinstance(self.config.log_growth_atr_risk, dict) else {}
            
            if exp_growth_config.get("enabled", False):
                atr_period = exp_growth_config.get("atr_period", 14)
                current_instrument["sl_atr_multiple"] = exp_growth_config.get("atr_multiple", 2.0)
            elif log_growth_config.get("enabled", False):
                atr_period = log_growth_config.get("atr_period", 14)
                current_instrument["sl_atr_multiple"] = log_growth_config.get("atr_multiple", 2.0)
            else:
                current_instrument["sl_atr_multiple"] = self.config.sl_atr_multiple 
            
            current_instrument["atr"] = AverageTrueRange(atr_period)
            current_instrument["sl_price"] = None

            # htf ema bias filter
            htf_ema_config = self.config.use_htf_ema_bias_filter if isinstance(self.config.use_htf_ema_bias_filter, dict) else {}
            htf_ema_period = htf_ema_config.get("ema_period", 200)
            current_instrument["htf_ema"] = ExponentialMovingAverage(htf_ema_period)

            # macd simple reversion
            macd_config = self.config.use_macd_simple_reversion_system if isinstance(self.config.use_macd_simple_reversion_system, dict) else {}
            macd_fast_period = macd_config.get("macd_fast_period", 12)
            macd_slow_period = macd_config.get("macd_slow_period", 26)
            macd_signal_period = macd_config.get("macd_signal_period", 9)
            current_instrument["macd"] = MovingAverageConvergenceDivergence(macd_fast_period, macd_slow_period)
            current_instrument["macd_signal_ema"] = ExponentialMovingAverage(macd_signal_period)
            current_instrument["prev_macd_line"] = None
            current_instrument["prev_macd_signal"] = None

            # rsi simple reversion
            rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
            rsi_period = rsi_config.get("rsi_period", 14)
            current_instrument["rsi"] = RelativeStrengthIndex(rsi_period)
            current_instrument["rsi_overbought"] = rsi_config.get("rsi_overbought", 0.7)
            current_instrument["rsi_oversold"] = rsi_config.get("rsi_oversold", 0.3)

            dm_config = self.config.directional_movement_filter if isinstance(self.config.directional_movement_filter, dict) else {}
            dm_period = dm_config.get("period", 14)
            current_instrument["directional_movement"] = DirectionalMovement(dm_period)
            current_instrument["min_di_diff"] = dm_config.get("min_di_diff", 0.02)

            retest_config = self.config.retest_entry if isinstance(self.config.retest_entry, dict) else {}
            retest_ema_period = retest_config.get("breakdown_ema_period", 50)
            current_instrument["retest_ema"] = ExponentialMovingAverage(retest_ema_period)
            current_instrument["breakdown_detected"] = False
            current_instrument["bars_since_breakdown"] = 0
            current_instrument["breakdown_price"] = None

            atr_burst_config = self.config.atr_burst_entry if isinstance(self.config.atr_burst_entry, dict) else {}
            if atr_burst_config.get("enabled", False):
                atr_burst_period = atr_burst_config.get("atr_period_calc", 40)
                current_instrument["atr_burst"] = AverageTrueRange(atr_burst_period)
                current_instrument["atr_history"] = []
                current_instrument["tr_history"] = []
                current_instrument["tr_lb"] = atr_burst_config.get("tr_lb", 3)
                current_instrument["burst_detected"] = False
                current_instrument["bars_since_burst"] = 0
                current_instrument["burst_threshold"] = atr_burst_config.get("atr_burst_threshold", 10)
                current_instrument["waiting_bars"] = atr_burst_config.get("waiting_bars_after_burst", 5)

            current_instrument["in_short_position"] = False
            current_instrument["in_long_position"] = False
            current_instrument["short_entry_price"] = None
            current_instrument["long_entry_price"] = None
            current_instrument["prev_bar_close"] = None
            
            # trailing stop tracking
            current_instrument["trailing_stop_price"] = None
            current_instrument["trailing_stop_activated"] = False
            current_instrument["best_price_since_entry"] = None

           # macd exit system
            macd_exit_config = self.config.use_macd_exit_system if isinstance(self.config.use_macd_exit_system, dict) else {}
            if macd_exit_config.get("enabled", False):
                macd_exit_fast = macd_exit_config.get("macd_fast_exit_period", 10)
                macd_exit_slow = macd_exit_config.get("macd_slow_exit_period", 32)
                macd_exit_signal = macd_exit_config.get("macd_signal_exit_period", 10)
                current_instrument["macd_exit"] = MovingAverageConvergenceDivergence(macd_exit_fast, macd_exit_slow)
                current_instrument["macd_exit_signal"] = ExponentialMovingAverage(macd_exit_signal)
                current_instrument["prev_macd_exit_line"] = None
                current_instrument["prev_macd_exit_signal"] = None

            htf_ema_config = self.config.use_htf_ema_bias_filter if isinstance(self.config.use_htf_ema_bias_filter, dict) else {}
            if htf_ema_config.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("htf_ema", 0)
            
            macd_config = self.config.use_macd_simple_reversion_system if isinstance(self.config.use_macd_simple_reversion_system, dict) else {}
            if macd_config.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("macd", 1)
                current_instrument["collector"].initialise_logging_indicator("macd_signal", 1)
            
            rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
            if rsi_config.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("rsi", 1)
            
            macd_exit_config = self.config.use_macd_exit_system if isinstance(self.config.use_macd_exit_system, dict) else {}
            if macd_exit_config.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("macd_exit", 1)
                current_instrument["collector"].initialise_logging_indicator("macd_exit_signal", 1)

            atr_burst_config = self.config.atr_burst_entry if isinstance(self.config.atr_burst_entry, dict) else {}
            if atr_burst_config.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("tr_atr_ratio", 1)


    def on_start(self):
        super().on_start()
        # self._subscribe_to_metrics_data()  # Disabled - not configured in YAML
        self._request_historical_bars()

    def _request_historical_bars(self):
        # Calculate how many bars we need based on indicator periods
        log_growth_config = self.config.log_growth_atr_risk if isinstance(self.config.log_growth_atr_risk, dict) else {}
        htf_ema_config = self.config.use_htf_ema_bias_filter if isinstance(self.config.use_htf_ema_bias_filter, dict) else {}
        macd_config = self.config.use_macd_simple_reversion_system if isinstance(self.config.use_macd_simple_reversion_system, dict) else {}
        macd_exit_config = self.config.use_macd_exit_system if isinstance(self.config.use_macd_exit_system, dict) else {}
        rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
        atr_burst_config = self.config.atr_burst_entry if isinstance(self.config.atr_burst_entry, dict) else {}
        
        max_lookback = max(
            self.config.atr_period if log_growth_config.get("enabled", False) else self.config.atr_period,
            log_growth_config.get("atr_period", 14),
            htf_ema_config.get("ema_period", 200),
            macd_config.get("macd_slow_period", 26),
            macd_exit_config.get("macd_slow_exit_period", 32),
            rsi_config.get("rsi_period", 20),
            atr_burst_config.get("atr_period_calc", 40) + 100
        )
        
        # Add 10% buffer to ensure we have enough data
        bars_needed = int(max_lookback * 1.1)
        
        self.log.info(f"Requesting {bars_needed} historical bars for {len(self.config.instruments)} instruments",LogColor.BLUE)

        for instrument_data in self.config.instruments:
            try:
                instrument_id_str = instrument_data.get("instrument_id")
                if not instrument_id_str:
                    self.log.warning("Instrument missing instrument_id, skipping", LogColor.YELLOW)
                    continue
                    
                instrument_id = InstrumentId.from_str(instrument_id_str)
                
                # Get the first bar_type from the list (typically only one per instrument)
                bar_types = instrument_data.get("bar_types", [])
                if not bar_types:
                    self.log.warning(
                        f"No bar_types defined for {instrument_id}, skipping historical bar request",
                        LogColor.YELLOW
                    )
                    continue
                
                bar_type = BarType.from_str(bar_types[0])
                
                # Calculate how far back we need to go (bars_needed * 15 minutes for 15-min bars)
                lookback_minutes = bars_needed * 15
                start_time = self._clock.utc_now() - timedelta(minutes=lookback_minutes)
                
                # Request historical bars using start time
                self.request_bars(bar_type, start=start_time)
                
            except Exception as e:
                self.log.error(
                    f"Failed to request historical bars for {instrument_data.get('instrument_id')}: {e}",
                    LogColor.RED
                )

    # def _subscribe_to_metrics_data(self):
    #     try:
    #         metrics_data_type = DataType(BybitMetricsData)
    #         self.subscribe_data(data_type=metrics_data_type)
    #     except Exception as e:
    #         self.log.error(f"Failed to subscribe to BybitMetricsData: {e}", LogColor.RED)

    # def on_data(self, data) -> None:
    #     if isinstance(data, BybitMetricsData):
    #         self.on_metrics_data(data)

    # def on_metrics_data(self, data: BybitMetricsData) -> None:
    #     instrument_id = data.instrument_id
    #     
    #     # Skip metrics for BTC and SOL - they're only used for price-based risk scaling
    #     if self.is_btc_instrument(instrument_id) or self.is_sol_instrument(instrument_id):
    #         return
    #     
    #     current_instrument = self.instrument_dict.get(instrument_id)
    #
    #     if current_instrument is not None:
    #         # Map Bybit fields to strategy fields - OI only
    #         current_instrument["latest_open_interest_value"] = data.open_interest
    #         
    #         # Apply BOTH entry and exit scaling
    #         self.entry_scale_binance_metrics(current_instrument)
    #         self.exit_scale_binance_metrics(current_instrument)
    #         
    #         # Update L3 window if trade is active
    #         self.update_l3_window(current_instrument)


    def passes_htf_ema_bias_filter(self, bar: Bar, current_instrument: Dict[str, Any], trade_direction: str) -> bool:
        htf_ema_config = self.config.use_htf_ema_bias_filter if isinstance(self.config.use_htf_ema_bias_filter, dict) else {}
        if not htf_ema_config.get("enabled", False):
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
        rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
        if not rsi_config.get("enabled", False):
            return True
            
        usage_method = rsi_config.get("usage_method", "execution")
        if usage_method != "condition":
            return True
            
        rsi = current_instrument["rsi"]
        if not rsi.initialized:
            return True
            
        rsi_value = float(rsi.value)
        rsi_overbought = current_instrument["rsi_overbought"]
        rsi_oversold = current_instrument["rsi_oversold"]
        
        if trade_direction == "long":
            return rsi_value <= rsi_oversold
        elif trade_direction == "short":
            return rsi_value >= rsi_overbought
            
        return False

    def passes_directional_movement_filter(self, bar: Bar, current_instrument: Dict[str, Any], trade_direction: str) -> bool:
        dm_config = self.config.directional_movement_filter if isinstance(self.config.directional_movement_filter, dict) else {}
        if not dm_config.get("enabled", False):
            return True
        
        dm = current_instrument["directional_movement"]
        if not dm.initialized:
            return True
        
        min_di_diff = current_instrument["min_di_diff"]
        di_plus = float(dm.pos)
        di_minus = float(dm.neg)
        di_diff = abs(di_plus - di_minus)
        
        if di_diff < min_di_diff:
            return False
        
        require_minus_above = dm_config.get("require_minus_di_above", True)
        if require_minus_above and trade_direction == "short":
            return di_minus > di_plus
        elif require_minus_above and trade_direction == "long":
            return di_plus > di_minus
        
        return True

    def update_retest_state(self, bar: Bar, current_instrument: Dict[str, Any]):
        retest_config = self.config.retest_entry if isinstance(self.config.retest_entry, dict) else {}
        if not retest_config.get("enabled", False):
            return
        
        retest_ema = current_instrument["retest_ema"]
        if not retest_ema.initialized:
            return
        
        current_price = float(bar.close)
        ema_value = float(retest_ema.value)
        
        if not current_instrument.get("breakdown_detected", False):
            if current_price < ema_value:
                current_instrument["breakdown_detected"] = True
                current_instrument["bars_since_breakdown"] = 0
                current_instrument["lowest_since_breakdown"] = current_price
        else:
            current_instrument["bars_since_breakdown"] += 1
            lowest = current_instrument.get("lowest_since_breakdown", current_price)
            if current_price < lowest:
                current_instrument["lowest_since_breakdown"] = current_price
            
            max_bars = retest_config.get("max_retest_bars", 10)
            if current_instrument["bars_since_breakdown"] > max_bars:
                current_instrument["breakdown_detected"] = False
                current_instrument["bars_since_breakdown"] = 0
                current_instrument["lowest_since_breakdown"] = None

    def check_retest_entry_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        retest_config = self.config.retest_entry if isinstance(self.config.retest_entry, dict) else {}
        if not retest_config.get("enabled", False):
            return False
        
        if not current_instrument.get("breakdown_detected", False):
            return False
        
        retest_ema = current_instrument["retest_ema"]
        if not retest_ema.initialized:
            return False
        
        atr = current_instrument.get("atr")
        if atr is None or not atr.initialized:
            return False
        
        current_price = float(bar.close)
        ema_value = float(retest_ema.value)
        atr_value = float(atr.value)
        tolerance = retest_config.get("retest_tolerance_atr", 0.3) * atr_value
        
        lowest = current_instrument.get("lowest_since_breakdown", current_price)
        bounced_up = current_price > lowest
        near_ema = current_price >= ema_value - tolerance
        
        if bounced_up and near_ema and current_price < ema_value + tolerance:
            return True
        
        return False
    

    def is_long_entry_allowed(self) -> bool:
        return not self.config.only_execute_short
    
    def is_btc_instrument(self, instrument_id) -> bool:
        return "BTCUSDT" in str(instrument_id)
    
    def update_btc_price(self, bar: Bar):
        price = float(bar.close)
        self.btc_current_price = price
        self.btc_price_history.append(price)
        if len(self.btc_price_history) > self.btc_lookback + 1:
            self.btc_price_history.pop(0)
    
    def get_btc_return(self) -> Optional[float]:
        if len(self.btc_price_history) < 2:
            return None
        return (self.btc_price_history[-1] - self.btc_price_history[0]) / self.btc_price_history[0]
    
    def get_coin_return(self, current_instrument: Dict[str, Any]) -> Optional[float]:
        price_history = current_instrument.get("price_history", [])
        if len(price_history) < 2:
            return None
        return (price_history[-1] - price_history[0]) / price_history[0]
    
    def update_coin_price_history(self, bar: Bar, current_instrument: Dict[str, Any]):
        price = float(bar.close)
        if "price_history" not in current_instrument:
            current_instrument["price_history"] = []
        current_instrument["price_history"].append(price)
        if len(current_instrument["price_history"]) > self.btc_lookback + 1:
            current_instrument["price_history"].pop(0)
    
    def passes_relative_strength_entry(self, current_instrument: Dict[str, Any]) -> bool:
        rs_config = self.config.relative_strength_entry if isinstance(self.config.relative_strength_entry, dict) else {}
        if not rs_config.get("enabled", False):
            return True
        
        btc_return = self.get_btc_return()
        coin_return = self.get_coin_return(current_instrument)
        
        if btc_return is None or coin_return is None:
            return False
        
        relative_strength = coin_return - btc_return
        weakness_threshold = rs_config.get("weakness_threshold", -0.02)
        
        if relative_strength <= weakness_threshold:
            return True
        
        return False
    
    def can_open_new_position(self) -> bool:
        open_positions = [p for p in self.cache.positions() if p.is_open]
        if len(open_positions) >= self.config.max_concurrent_positions:
            self.log.warning(f"Max concurrent positions ({self.config.max_concurrent_positions}) reached, blocking new entry", LogColor.YELLOW)
            return False
        return True
    
    def load_onboard_dates(self):
        import csv
        from pathlib import Path
        
        onboard_dates = {}
        
        live_csv = Path(__file__).parent.parent / "data" / "DATA_STORAGE" / "project_future_scraper" / "bybit_live_linear_perpetual_futures.csv"
        backtest_csv = Path(__file__).parent.parent / "data" / "DATA_STORAGE" / "project_future_scraper" / "new_bybit_linear_perpetual_futures.csv"
        
        csv_path = live_csv if live_csv.exists() else backtest_csv
        
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
        
        # Log current time and deadline in a readable format
        #self.log.info(f"Current time: {current_time}, Deadline: {deadline}", LogColor.CYAN)
        
        # Block all new trades after deadline
        if current_time < deadline:
            return True
        else:
            self.log.info("TIME CLOSURE", LogColor.CYAN)
            self.log.info("TIME CLOSURE", LogColor.CYAN)
            self.log.info("TIME CLOSURE", LogColor.CYAN)
            self.log.info("TIME CLOSURE", LogColor.CYAN)
            self.log.info("TIME CLOSURE", LogColor.CYAN)
            self.log.info("TIME CLOSURE", LogColor.CYAN)
            self.log.info("TIME CLOSURE", LogColor.CYAN)
            self.order_types.close_position_by_market_order(bar.bar_type.instrument_id)
            self.unsubscribe_bars(bar.bar_type)
            
            return False

    # def is_btc_instrument(self, instrument_id) -> bool:
    #     return "BTCUSDT" in str(instrument_id)
    # 
    # def is_btc_instrument(self, instrument_id) -> bool:
    #     return "BTCUSDT" in str(instrument_id)
    
    # def process_btc_bar(self, bar: Bar) -> None:
    #     if not self.config.btc_performance_risk_scaling.get("enabled", False):
    #         return
            
    #     if not hasattr(self, 'btc_context'):
    #         self.setup_btc_tracking()
            
    #     if self.btc_context["btc_instrument_id"] is None:
    #         self.btc_context["btc_instrument_id"] = bar.bar_type.instrument_id

    #     current_price = float(bar.close)
    #     self.btc_context["price_history"].append(current_price)
        
    #     window_size = self.btc_context["rolling_zscore"]
    #     if len(self.btc_context["price_history"]) > window_size:
    #         self.btc_context["price_history"].pop(0)
        
    #     self.update_btc_risk_metrics()

    def on_historical_data(self, data):
        if data is None:
            return
        
        # Handle both single Bar and list of Bars
        bars = [data] if isinstance(data, Bar) else data
        
        if not bars:
            return
        
        # Feed all bars to indicators (silently - no logging spam)
        for bar in bars:
            instrument_id = bar.bar_type.instrument_id
            
            if self.is_btc_instrument(instrument_id):
                self.update_btc_price(bar)
                continue
                
            current_instrument = self.instrument_dict.get(instrument_id)
            if current_instrument is None:
                continue
                
            # Update indicators with historical bars
            if "atr" in current_instrument:
                current_instrument["atr"].handle_bar(bar)
            
            htf_ema_config = self.config.use_htf_ema_bias_filter if isinstance(self.config.use_htf_ema_bias_filter, dict) else {}
            if htf_ema_config.get("enabled", False):
                if "htf_ema" in current_instrument:
                    current_instrument["htf_ema"].handle_bar(bar)
            
            macd_config = self.config.use_macd_simple_reversion_system if isinstance(self.config.use_macd_simple_reversion_system, dict) else {}
            if macd_config.get("enabled", False):
                if "macd" in current_instrument:
                    current_instrument["macd"].handle_bar(bar)
                if "macd_signal_ema" in current_instrument and current_instrument["macd"].initialized:
                    current_instrument["macd_signal_ema"].update_raw(current_instrument["macd"].value)
            
            rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
            if rsi_config.get("enabled", False):
                if "rsi" in current_instrument:
                    current_instrument["rsi"].handle_bar(bar)
            
            macd_exit_config = self.config.use_macd_exit_system if isinstance(self.config.use_macd_exit_system, dict) else {}
            if macd_exit_config.get("enabled", False):
                if "macd_exit" in current_instrument:
                    current_instrument["macd_exit"].handle_bar(bar)
                if "macd_exit_signal" in current_instrument and current_instrument["macd_exit"].initialized:
                    current_instrument["macd_exit_signal"].update_raw(current_instrument["macd_exit"].value)

            dm_config = self.config.directional_movement_filter if isinstance(self.config.directional_movement_filter, dict) else {}
            if dm_config.get("enabled", False):
                if "directional_movement" in current_instrument:
                    current_instrument["directional_movement"].handle_bar(bar)

            retest_config = self.config.retest_entry if isinstance(self.config.retest_entry, dict) else {}
            if retest_config.get("enabled", False):
                if "retest_ema" in current_instrument:
                    current_instrument["retest_ema"].handle_bar(bar)

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id

        if self.is_btc_instrument(instrument_id):
            self.update_btc_price(bar)
            return

        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is None:
            self.log.warning(f"No instrument found for {instrument_id}", LogColor.RED)
            return
        if "atr" not in current_instrument:
            self.add_instrument_context()

        current_instrument["atr"].handle_bar(bar)
        
        htf_ema_config = self.config.use_htf_ema_bias_filter if isinstance(self.config.use_htf_ema_bias_filter, dict) else {}
        if htf_ema_config.get("enabled", False):
            htf_ema = current_instrument["htf_ema"]
            htf_ema.handle_bar(bar)
        
        macd_config = self.config.use_macd_simple_reversion_system if isinstance(self.config.use_macd_simple_reversion_system, dict) else {}
        if macd_config.get("enabled", False):
            macd = current_instrument["macd"]
            macd.handle_bar(bar)
            if macd.initialized:
                macd_signal_ema = current_instrument["macd_signal_ema"]
                macd_signal_ema.update_raw(macd.value)
        
        rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
        if rsi_config.get("enabled", False):
            rsi = current_instrument["rsi"]
            rsi.handle_bar(bar)
        
        macd_exit_config = self.config.use_macd_exit_system if isinstance(self.config.use_macd_exit_system, dict) else {}
        if macd_exit_config.get("enabled", False):
            macd_exit = current_instrument["macd_exit"]
            macd_exit.handle_bar(bar)
            if macd_exit.initialized:
                macd_exit_signal = current_instrument["macd_exit_signal"]
                macd_exit_signal.update_raw(macd_exit.value)
        
        dm_config = self.config.directional_movement_filter if isinstance(self.config.directional_movement_filter, dict) else {}
        if dm_config.get("enabled", False):
            current_instrument["directional_movement"].handle_bar(bar)

        retest_config = self.config.retest_entry if isinstance(self.config.retest_entry, dict) else {}
        if retest_config.get("enabled", False):
            current_instrument["retest_ema"].handle_bar(bar)
            self.update_retest_state(bar, current_instrument)

        atr_burst_config = self.config.atr_burst_entry if isinstance(self.config.atr_burst_entry, dict) else {}
        if atr_burst_config.get("enabled", False):
            atr_burst = current_instrument["atr_burst"]
            atr_burst.handle_bar(bar)
            if atr_burst.initialized:
                atr_history = current_instrument["atr_history"]
                atr_history.append(float(atr_burst.value))
                if len(atr_history) > 100:
                    atr_history.pop(0)
                
                tr_lb = current_instrument["tr_lb"]
                if len(atr_history) >= tr_lb:
                    cumulative_atr = sum(atr_history[-tr_lb:])
                    true_range = float(bar.high.as_double() - bar.low.as_double())
                    is_upside = float(bar.close.as_double() - bar.open.as_double()) > 0
                    
                    tr_history = current_instrument["tr_history"]
                    tr_history.append(true_range if is_upside else 0)
                    if len(tr_history) > tr_lb:
                        tr_history.pop(0)
                    
                    cumulative_tr = sum(tr_history)
                    tr_atr_ratio = cumulative_tr / cumulative_atr if cumulative_atr > 0 else 0
                    current_instrument["tr_atr_ratio"] = tr_atr_ratio
                    
                    if not current_instrument.get("burst_detected", False):
                        if tr_atr_ratio > current_instrument["burst_threshold"] and is_upside:
                            current_instrument["burst_detected"] = True
                            current_instrument["bars_since_burst"] = 0
                    else:
                        current_instrument["bars_since_burst"] += 1
        
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)
        
        self.update_coin_price_history(bar, current_instrument)
        
        position = self.base_get_position(instrument_id)
        
        # if we have a position, check exit logic (even if SL order is open)
        if position is not None and position.side == PositionSide.SHORT:
            self.short_exit_logic(bar, current_instrument, position)
            return
        
        # only block new entries if we have pending orders and no position
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        
        if not self.is_trading_allowed_after_listing(bar):
            return
        
        self.relative_strength_entry_setup(bar, current_instrument)
        
        self.atr_burst_setup(bar, current_instrument)
        self.macd_simple_reversion_setup(bar, current_instrument)
        self.retest_entry_setup(bar, current_instrument)
        
        rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
        if rsi_config.get("usage_method") == "execution":
            self.rsi_simple_reversion_setup(bar, current_instrument)

    def atr_burst_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        atr_burst_config = self.config.atr_burst_entry if isinstance(self.config.atr_burst_entry, dict) else {}
        if not atr_burst_config.get("enabled", False):
            return
        
        if not current_instrument.get("burst_detected", False):
            return
        
        waiting_bars = current_instrument["waiting_bars"]
        bars_since_burst = current_instrument["bars_since_burst"]
        
        if bars_since_burst == waiting_bars:
            self.log.info(f"ATTEMPTING SHORT ENTRY after {waiting_bars} bars!", LogColor.GREEN)
            self.enter_short_atr_burst(bar, current_instrument)
            current_instrument["burst_detected"] = False
            current_instrument["bars_since_burst"] = 0

    def relative_strength_entry_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        rs_config = self.config.relative_strength_entry if isinstance(self.config.relative_strength_entry, dict) else {}
        if not rs_config.get("enabled", False):
            return
        
        if not self.passes_relative_strength_entry(current_instrument):
            return
        
        if not self.can_open_new_position():
            return
        
        self.enter_short_relative_strength(bar, current_instrument)

    def enter_short_relative_strength(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        atr = current_instrument["atr"]
        if not atr.initialized:
            return
        
        atr_value = float(atr.value)
        sl_atr_multiple = current_instrument.get("sl_atr_multiple", self.config.sl_atr_multiple)
        stop_loss_price = entry_price + (atr_value * sl_atr_multiple)
        
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["sl_price"] = stop_loss_price
            current_instrument["best_price_since_entry"] = entry_price
            current_instrument["trailing_stop_activated"] = False
            current_instrument["trailing_stop_price"] = None
            self.order_types.submit_short_market_order_with_sl(instrument_id, qty, stop_loss_price)

    def enter_short_atr_burst(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        if not self.passes_htf_ema_bias_filter(bar, current_instrument, "short"):
            return
        
        atr = current_instrument["atr"]
        if not atr.initialized:
            return
        
        atr_value = float(atr.value)
        sl_atr_multiple = current_instrument.get("sl_atr_multiple", self.config.sl_atr_multiple)
        stop_loss_price = entry_price + (atr_value * sl_atr_multiple)
        
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["sl_price"] = stop_loss_price
            current_instrument["best_price_since_entry"] = entry_price
            current_instrument["trailing_stop_activated"] = False
            current_instrument["trailing_stop_price"] = None
            self.order_types.submit_short_market_order_with_sl(instrument_id, qty, stop_loss_price)

    def rsi_simple_reversion_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
        if not rsi_config.get("enabled", False):
            return
            
        rsi = current_instrument["rsi"]
        if not rsi.initialized:
            return
            
        usage_method = rsi_config.get("usage_method", "execution")
        
        if usage_method == "execution":
            rsi_value = float(rsi.value)
            rsi_overbought = current_instrument["rsi_overbought"]
            
            if rsi_value >= rsi_overbought and self.passes_htf_ema_bias_filter(bar, current_instrument, "short"):
                self.enter_short_rsi_reversion(bar, current_instrument)
        elif usage_method == "condition":
            pass

    def enter_short_rsi_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            stop_loss_price = entry_price * 1.02
        
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["sl_price"] = stop_loss_price
            current_instrument["best_price_since_entry"] = entry_price
            current_instrument["trailing_stop_activated"] = False
            current_instrument["trailing_stop_price"] = None
            self.order_types.submit_short_market_order_with_sl(instrument_id, qty, stop_loss_price)

    def macd_simple_reversion_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        macd_config = self.config.use_macd_simple_reversion_system if isinstance(self.config.use_macd_simple_reversion_system, dict) else {}
        if not macd_config.get("enabled", False):
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
                self.passes_rsi_condition_filter(bar, current_instrument, "long") and
                self.passes_directional_movement_filter(bar, current_instrument, "long")):
                pass
            
            elif (prev_macd >= prev_signal and macd_line < signal_line and
                  macd_line > 0 and signal_line > 0 and
                  self.passes_htf_ema_bias_filter(bar, current_instrument, "short") and
                  self.passes_rsi_condition_filter(bar, current_instrument, "short") and
                  self.passes_directional_movement_filter(bar, current_instrument, "short")):
                self.enter_short_macd_reversion(bar, current_instrument)
        
        current_instrument["prev_macd_line"] = macd_line
        current_instrument["prev_macd_signal"] = signal_line

    def retest_entry_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        retest_config = self.config.retest_entry if isinstance(self.config.retest_entry, dict) else {}
        if not retest_config.get("enabled", False):
            return
        
        if not self.check_retest_entry_short(bar, current_instrument):
            return
        
        if not self.passes_htf_ema_bias_filter(bar, current_instrument, "short"):
            return
        
        if not self.passes_directional_movement_filter(bar, current_instrument, "short"):
            return
        
        self.enter_short_retest(bar, current_instrument)
        current_instrument["breakdown_detected"] = False
        current_instrument["bars_since_breakdown"] = 0
        current_instrument["breakdown_price"] = None

    def enter_short_retest(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        if not self.can_open_new_position():
            return
        
        atr = current_instrument["atr"]
        if not atr.initialized:
            return
        
        atr_value = float(atr.value)
        sl_atr_multiple = current_instrument.get("sl_atr_multiple", self.config.sl_atr_multiple)
        stop_loss_price = entry_price + (atr_value * sl_atr_multiple)
        
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["sl_price"] = stop_loss_price
            current_instrument["best_price_since_entry"] = entry_price
            current_instrument["trailing_stop_activated"] = False
            current_instrument["trailing_stop_price"] = None
            self.order_types.submit_short_market_order_with_sl(instrument_id, qty, stop_loss_price)

    def enter_short_macd_reversion(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        entry_price = float(bar.close)
        
        if not self.can_open_new_position():
            return
        
        atr_value = current_instrument["atr"].value
        sl_atr_multiple = current_instrument["sl_atr_multiple"]
        if atr_value is not None:
            stop_loss_price = entry_price + sl_atr_multiple * atr_value
        else:
            stop_loss_price = entry_price * 1.02
        
        qty = self.calculate_risk_based_position_size(instrument_id, entry_price, stop_loss_price)
        
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["sl_price"] = stop_loss_price
            current_instrument["best_price_since_entry"] = entry_price  # init for trailing stop
            current_instrument["trailing_stop_activated"] = False
            current_instrument["trailing_stop_price"] = None
            self.order_types.submit_short_market_order_with_sl(instrument_id, qty, stop_loss_price)

    def short_exit_logic(self, bar: Bar, current_instrument: Dict[str, Any], position):
        sl_price = current_instrument.get("sl_price")
        instrument_id = bar.bar_type.instrument_id
        current_price = float(bar.close)
        
        # SL hit check - just reset tracking, exchange handles the actual close
        if sl_price is not None and float(bar.high) >= sl_price:
            self.log.info(f"SL HIT at {current_price:.4f} (SL was {sl_price:.4f})", LogColor.RED)
            self.reset_position_tracking(current_instrument)
            current_instrument["prev_bar_close"] = current_price
            return
        
        # time-based exit
        if self.check_time_based_exit(bar, current_instrument, position, self.config.time_after_listing_close):
            self._execute_exit(instrument_id, position, current_instrument, "TIME EXIT")
            current_instrument["prev_bar_close"] = current_price
            return
        
        # skip other exits if holding for remaining days
        if self.config.hold_profit_for_remaining_days:
            current_instrument["prev_bar_close"] = current_price
            return
        
        # trailing stop exit
        trailing_config = self.config.use_trailing_stop_exit if isinstance(self.config.use_trailing_stop_exit, dict) else {}
        if trailing_config.get("enabled", False):
            if self.check_trailing_stop_exit_short(bar, current_instrument):
                self._execute_exit(instrument_id, position, current_instrument, "TRAILING STOP")
                current_instrument["prev_bar_close"] = current_price
                return

        # macd exit
        macd_exit_config = self.config.use_macd_exit_system if isinstance(self.config.use_macd_exit_system, dict) else {}
        if macd_exit_config.get("enabled", False):
            if self.check_macd_exit_short(bar, current_instrument):
                self._execute_exit(instrument_id, position, current_instrument, "MACD EXIT")
                current_instrument["prev_bar_close"] = current_price
                return
        
        current_instrument["prev_bar_close"] = current_price
    
    def _execute_exit(self, instrument_id, position, current_instrument, reason: str):
        """Execute exit - cancel SL order and close position."""
        close_qty = abs(float(position.quantity))
        if close_qty > 0:
            self.log.info(f"{reason}: Closing {close_qty} @ market", LogColor.GREEN)
            self._cancel_open_orders(instrument_id)
            self.order_types.submit_long_market_order(instrument_id, int(close_qty))
        self.reset_position_tracking(current_instrument)
    
    def _cancel_open_orders(self, instrument_id):
        """Cancel all open orders for the given instrument (used to cancel SL orders before manual exit)."""
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        for order in open_orders:
            self.cancel_order(order)

    def reset_position_tracking(self, current_instrument: Dict[str, Any]):
        current_instrument["short_entry_price"] = None
        current_instrument["sl_price"] = None
        current_instrument["in_short_position"] = False
        current_instrument["trailing_stop_price"] = None
        current_instrument["trailing_stop_activated"] = False
        current_instrument["best_price_since_entry"] = None

    def check_trailing_stop_exit_short(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        """Trailing stop for short positions - trails down as price drops."""
        trailing_config = self.config.use_trailing_stop_exit if isinstance(self.config.use_trailing_stop_exit, dict) else {}
        
        entry_price = current_instrument.get("short_entry_price")
        if entry_price is None:
            return False
        
        atr = current_instrument.get("atr")
        if atr is None or not atr.initialized:
            return False
        
        atr_value = float(atr.value)
        current_price = float(bar.close)
        atr_multiple = trailing_config.get("atr_multiple", 2.0)
        activation_atr = trailing_config.get("activation_profit_atr", 1.0)
        
        # track best price (lowest for short)
        best_price = current_instrument.get("best_price_since_entry")
        if best_price is None or current_price < best_price:
            current_instrument["best_price_since_entry"] = current_price
            best_price = current_price
        
        # check if trailing stop should activate (price dropped enough)
        profit_distance = entry_price - best_price
        activation_distance = atr_value * activation_atr
        
        if not current_instrument.get("trailing_stop_activated", False):
            if profit_distance >= activation_distance:
                current_instrument["trailing_stop_activated"] = True
                # set initial trailing stop
                current_instrument["trailing_stop_price"] = best_price + (atr_value * atr_multiple)
                self.log.info(f"Trailing stop ACTIVATED at {current_instrument['trailing_stop_price']:.4f}", LogColor.CYAN)
        
        # update trailing stop if activated (only moves down for shorts)
        if current_instrument.get("trailing_stop_activated", False):
            new_trail = best_price + (atr_value * atr_multiple)
            current_trail = current_instrument.get("trailing_stop_price")
            
            if current_trail is None or new_trail < current_trail:
                current_instrument["trailing_stop_price"] = new_trail
            
            # check if trailing stop hit
            if current_price >= current_instrument["trailing_stop_price"]:
                self.log.info(f"Trailing stop HIT at {current_price:.4f}", LogColor.GREEN)
                return True
        
        return False

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

        # HTF EMA bias filter (position 0)
        htf_ema_config = self.config.use_htf_ema_bias_filter if isinstance(self.config.use_htf_ema_bias_filter, dict) else {}
        if htf_ema_config.get("enabled", False):
            htf_ema_value = float(current_instrument["htf_ema"].value) if current_instrument["htf_ema"].value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="htf_ema", value=htf_ema_value)

        # MACD for reversion system (position 1)
        macd_config = self.config.use_macd_simple_reversion_system if isinstance(self.config.use_macd_simple_reversion_system, dict) else {}
        if macd_config.get("enabled", False):
            macd = current_instrument["macd"]
            macd_signal_ema = current_instrument["macd_signal_ema"]
            if macd and macd.value is not None and macd_signal_ema and macd_signal_ema.value is not None:
                macd_value = float(macd.value)
                signal_value = float(macd_signal_ema.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd", value=macd_value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_signal", value=signal_value)

        # RSI for reversion system (position 1)
        rsi_config = self.config.use_rsi_simple_reversion_system if isinstance(self.config.use_rsi_simple_reversion_system, dict) else {}
        if rsi_config.get("enabled", False):
            rsi = current_instrument.get("rsi")
            if rsi and rsi.value is not None:
                rsi_value = float(rsi.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="rsi", value=rsi_value)

        # MACD for exit method (position 1)
        macd_exit_config = self.config.use_macd_exit_system if isinstance(self.config.use_macd_exit_system, dict) else {}
        if macd_exit_config.get("enabled", False):
            macd_exit = current_instrument.get("macd_exit")
            macd_exit_signal = current_instrument.get("macd_exit_signal")
            if macd_exit and macd_exit.value is not None and macd_exit_signal and macd_exit_signal.value is not None:
                macd_exit_value = float(macd_exit.value)
                macd_exit_signal_value = float(macd_exit_signal.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_exit", value=macd_exit_value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_exit_signal", value=macd_exit_signal_value)

        atr_burst_config = self.config.atr_burst_entry if isinstance(self.config.atr_burst_entry, dict) else {}
        if atr_burst_config.get("enabled", False):
            tr_atr_ratio = current_instrument.get("tr_atr_ratio", 0)
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="tr_atr_ratio", value=tr_atr_ratio)
        
    def on_order_filled(self, order_filled) -> None:
        self.log.info(f"ORDER FILLED: {order_filled.ts_event})", LogColor.CYAN)
        self.log.info(f"ORDER px: {order_filled.last_px})", LogColor.CYAN)
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
    
    def on_position_opened(self, position_opened) -> None:
        self.log.info(f"POS OPENED: {position_opened.ts_init})", LogColor.CYAN)
        self.log.info(f"POS OPENED: {position_opened.ts_opened})", LogColor.CYAN)



    
    


    

