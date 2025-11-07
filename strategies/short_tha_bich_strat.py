## code für die dann aber wirklich nutzbar coin short strat
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
from nautilus_trader.indicators.macd import MovingAverageConvergenceDivergence
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
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

    only_execute_short: bool = False
    hold_profit_for_remaining_days: bool = False
    close_positions_on_stop: bool = True
    max_leverage: Decimal = 10.0

class ShortThaBitchStrat(BaseStrategy, Strategy):
    def __init__(self, config: ShortThaBitchStratConfig):
        super().__init__(config)
        self.risk_manager = RiskManager(config)
        self.risk_manager.set_strategy(self)    
        self.risk_manager.set_max_leverage(Decimal(str(config.max_leverage)))
        self.order_types = OrderTypes(self) 
        self.onboard_dates = self.load_onboard_dates()
        self.add_instrument_context()

    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            # das hier drunter nur ATR
            atr_period = self.config.atr_period
            exp_growth_config = self.config.exp_growth_atr_risk
            log_growth_config = self.config.log_growth_atr_risk
            
            if exp_growth_config["enabled"]:
                atr_period = exp_growth_config["atr_period"]
                current_instrument["sl_atr_multiple"] = exp_growth_config["atr_multiple"]
            elif log_growth_config["enabled"]:
                atr_period = log_growth_config["atr_period"]
                current_instrument["sl_atr_multiple"] = log_growth_config["atr_multiple"]
            else:
                current_instrument["sl_atr_multiple"] = self.config.sl_atr_multiple
            
            current_instrument["atr"] = AverageTrueRange(atr_period)
            current_instrument["sl_price"] = None

            # htf ema bias filter
            htf_ema_config = self.config.use_htf_ema_bias_filter
            htf_ema_period = htf_ema_config.get("ema_period", 200)
            current_instrument["htf_ema"] = ExponentialMovingAverage(htf_ema_period)

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
            current_instrument["rsi_overbought"] = rsi_config.get("rsi_overbought", 0.7)
            current_instrument["rsi_oversold"] = rsi_config.get("rsi_oversold", 0.3)

            # Position tracking initialization
            current_instrument["in_short_position"] = False
            current_instrument["in_long_position"] = False
            current_instrument["short_entry_price"] = None
            current_instrument["long_entry_price"] = None
            current_instrument["prev_bar_close"] = None

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

            if self.config.use_htf_ema_bias_filter.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("htf_ema", 0)
            if self.config.use_macd_simple_reversion_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("macd", 1)
                current_instrument["collector"].initialise_logging_indicator("macd_signal", 1)
            if self.config.use_rsi_simple_reversion_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("rsi", 1)
            if self.config.use_macd_exit_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("macd_exit", 1)
                current_instrument["collector"].initialise_logging_indicator("macd_exit_signal", 1)


    def on_start(self):
        super().on_start()
        # self._subscribe_to_metrics_data()  # Disabled - not configured in YAML
        self._request_historical_bars()

    def _request_historical_bars(self):
        # Calculate how many bars we need based on indicator periods
        max_lookback = max(
            self.config.atr_period if self.config.log_growth_atr_risk.get("enabled", False) else self.config.atr_period,
            self.config.log_growth_atr_risk.get("atr_period", 14),
            self.config.use_htf_ema_bias_filter.get("ema_period", 200),
            self.config.use_macd_simple_reversion_system.get("macd_slow_period", 26),
            self.config.use_macd_exit_system.get("macd_slow_exit_period", 32),
            self.config.use_rsi_simple_reversion_system.get("rsi_period", 20)
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
        return not self.config.only_execute_short
    
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
            
            # # Process BTC/SOL bars
            # if self.is_btc_instrument(instrument_id):
            #     self.process_btc_bar(bar)
            #     continue
                
            # Process trading instrument bars
            current_instrument = self.instrument_dict.get(instrument_id)
            if current_instrument is None:
                continue
                
            # Update indicators with historical bars
            if "atr" in current_instrument:
                current_instrument["atr"].handle_bar(bar)
            
            if self.config.use_htf_ema_bias_filter.get("enabled", False):
                if "htf_ema" in current_instrument:
                    current_instrument["htf_ema"].handle_bar(bar)
            
            if self.config.use_macd_simple_reversion_system.get("enabled", False):
                if "macd" in current_instrument:
                    current_instrument["macd"].handle_bar(bar)
                if "macd_signal_ema" in current_instrument and current_instrument["macd"].initialized:
                    current_instrument["macd_signal_ema"].update_raw(current_instrument["macd"].value)
            
            if self.config.use_rsi_simple_reversion_system.get("enabled", False):
                if "rsi" in current_instrument:
                    current_instrument["rsi"].handle_bar(bar)
            
            if self.config.use_macd_exit_system.get("enabled", False):
                if "macd_exit" in current_instrument:
                    current_instrument["macd_exit"].handle_bar(bar)
                if "macd_exit_signal" in current_instrument and current_instrument["macd_exit"].initialized:
                    current_instrument["macd_exit_signal"].update_raw(current_instrument["macd_exit"].value)

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id

        # if self.is_btc_instrument(instrument_id):
        #     self.process_btc_bar(bar)
            
        #     btc_instrument = self.instrument_dict.get(instrument_id)
        #     if btc_instrument is not None:
        #         self.update_btc_visualizer_data(bar, btc_instrument)
        #     return

        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is None:
            self.log.warning(f"No instrument found for {instrument_id}", LogColor.RED)
            return
        if "atr" not in current_instrument:
            self.add_instrument_context()

        current_instrument["atr"].handle_bar(bar)
        if self.config.use_htf_ema_bias_filter.get("enabled", False):
            htf_ema = current_instrument["htf_ema"]
            htf_ema.handle_bar(bar)
        
        if self.config.use_macd_simple_reversion_system.get("enabled", False):
            macd = current_instrument["macd"]
            macd.handle_bar(bar)
            if macd.initialized:
                macd_signal_ema = current_instrument["macd_signal_ema"]
                macd_signal_ema.update_raw(macd.value)
        
        if self.config.use_rsi_simple_reversion_system.get("enabled", False):
            rsi = current_instrument["rsi"]
            rsi.handle_bar(bar)
        
        if self.config.use_macd_exit_system.get("enabled", False):
            macd_exit = current_instrument["macd_exit"]
            macd_exit.handle_bar(bar)
            if macd_exit.initialized:
                macd_exit_signal = current_instrument["macd_exit_signal"]
                macd_exit_signal.update_raw(macd_exit.value)
        
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)
        
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return  
        
        position = self.base_get_position(instrument_id)

        
        if position is not None and position.side == PositionSide.SHORT:
            self.short_exit_logic(bar, current_instrument, position)
            return
        
        # Block new trades after listing deadline
        if not self.is_trading_allowed_after_listing(bar):
            return
        
        self.macd_simple_reversion_setup(bar, current_instrument)
        
        # Only call RSI setup if usage_method is "execution" (direct RSI entry signals)
        # When usage_method="condition", RSI only acts as filter in macd_simple_reversion_setup
        if self.config.use_rsi_simple_reversion_system.get("usage_method") == "execution":
            self.rsi_simple_reversion_setup(bar, current_instrument)

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
            # rsi_oversold = current_instrument["rsi_oversold"]  # Unused with only_execute_short=true
            
            # Immediate execution on extreme RSI levels - no minimum bars required
            if rsi_value >= rsi_overbought and self.passes_htf_ema_bias_filter(bar, current_instrument, "short"):
                self.enter_short_rsi_reversion(bar, current_instrument)
            # Long entries disabled via only_execute_short=true
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
        
        # Only submit order if quantity > 0
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["sl_price"] = stop_loss_price
            self.order_types.submit_short_market_order(instrument_id, qty)

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
                pass  # Long entries disabled via only_execute_short=true
            
            elif (prev_macd >= prev_signal and macd_line < signal_line and
                  macd_line > 0 and signal_line > 0 and
                  self.passes_htf_ema_bias_filter(bar, current_instrument, "short") and
                  self.passes_rsi_condition_filter(bar, current_instrument, "short")):
                self.enter_short_macd_reversion(bar, current_instrument)
        
        current_instrument["prev_macd_line"] = macd_line
        current_instrument["prev_macd_signal"] = signal_line

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
        
        # Only submit order if quantity > 0
        if qty > 0:
            current_instrument["in_short_position"] = True
            current_instrument["short_entry_price"] = entry_price
            current_instrument["sl_price"] = stop_loss_price
            self.order_types.submit_short_market_order(instrument_id, qty)

    def short_exit_logic(self, bar: Bar, current_instrument: Dict[str, Any], position):
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
        if self.check_time_based_exit(bar, current_instrument, position, self.config.time_after_listing_close):
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

        if not should_exit and self.config.use_macd_exit_system.get("enabled", False):
            if self.check_macd_exit_short(bar, current_instrument):
                should_exit = True
        
        if should_exit:
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_long_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
        
        current_instrument["prev_bar_close"] = float(bar.close)

    def reset_position_tracking(self, current_instrument: Dict[str, Any]):
        current_instrument["short_entry_price"] = None
        current_instrument["sl_price"] = None
        current_instrument["in_short_position"] = False

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
        if self.config.use_htf_ema_bias_filter.get("enabled", False):
            htf_ema_value = float(current_instrument["htf_ema"].value) if current_instrument["htf_ema"].value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="htf_ema", value=htf_ema_value)

        # MACD for reversion system (position 1)
        if self.config.use_macd_simple_reversion_system.get("enabled", False):
            macd = current_instrument["macd"]
            macd_signal_ema = current_instrument["macd_signal_ema"]
            if macd and macd.value is not None and macd_signal_ema and macd_signal_ema.value is not None:
                macd_value = float(macd.value)
                signal_value = float(macd_signal_ema.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd", value=macd_value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="macd_signal", value=signal_value)

        # RSI for reversion system (position 1)
        if self.config.use_rsi_simple_reversion_system.get("enabled", False):
            rsi = current_instrument.get("rsi")
            if rsi and rsi.value is not None:
                rsi_value = float(rsi.value)
                current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="rsi", value=rsi_value)

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



    
    


    

