# strat for coin_listing_short.yaml
from datetime import datetime, time, timezone, timedelta
from typing import Any, Dict, Optional, List, Union
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.common.enums import LogColor
from pydantic import Field

from nautilus_trader.indicators.aroon import AroonOscillator
from nautilus_trader.indicators.atr import AverageTrueRange
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from nautilus_trader.model.data import DataType
from data.download.crypto_downloads.custom_class.metrics_data import MetricsData
from data.download.crypto_downloads.custom_class.lunar_data import LunarData

class CoinListingShortConfig(StrategyConfig):
    instruments: List[dict]  
    max_leverage: float
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

    only_execute_short: bool = False
    hold_profit_for_remaining_days: bool = False
    close_positions_on_stop: bool = True

class CoinListingShortStrategy(BaseStrategy, Strategy):

    def __init__(self, config: CoinListingShortConfig):
        super().__init__(config)
        self.risk_manager = RiskManager(config)
        self.risk_manager.set_strategy(self)
        self.order_types = OrderTypes(self) 
        self.onboard_dates = self.load_onboard_dates()
        self.add_instrument_context()
    
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

            # l3 metrics
            current_instrument["sum_toptrader_long_short_ratio"] = 0.0
            current_instrument["count_long_short_ratio"] = 0.0
            current_instrument["latest_open_interest_value"] = 0.0

            # lunar data
            current_instrument["posts_created"] = 0.0
            current_instrument["sentiment"] = 0.0
            current_instrument["interactions"] = 0.0

            # visualizer
            if self.config.use_aroon_simple_trend_system.get("enabled", False):
                current_instrument["collector"].initialise_logging_indicator("aroon_osc", 1)
            
            # Initialize lunar data visualization
            current_instrument["collector"].initialise_logging_indicator("interactions", 2)
            current_instrument["collector"].initialise_logging_indicator("posts_created", 3)
            current_instrument["collector"].initialise_logging_indicator("sentiment", 4)
            
            # Initialize metrics data visualization
            current_instrument["collector"].initialise_logging_indicator("toptr_long_short_ratio", 5)
            current_instrument["collector"].initialise_logging_indicator("count_long_short_ratio", 6)
            current_instrument["collector"].initialise_logging_indicator("open_interest_value", 7)
    
    def on_start(self): 
        super().on_start()
        self._subscribe_to_metrics_data()
        self._subscribe_to_lunar_data()

    def _subscribe_to_lunar_data(self):
        try:
            lunar_data_type = DataType(LunarData)
            self.subscribe_data(data_type=lunar_data_type)
        except Exception as e:
            self.log.error(f"Failed to subscribe to LunarData: {e}", LogColor.RED)

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
        elif isinstance(data, LunarData):
            self.on_lunar_data(data)
    def on_lunar_data(self, data: LunarData) -> None:
        instrument_id = data.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is not None:
            current_instrument["posts_created"] = data.posts_created
            current_instrument["sentiment"] = data.sentiment
            current_instrument["interactions"] = data.interactions

    def on_metrics_data(self, data: MetricsData) -> None:
        instrument_id = data.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is not None:
            current_instrument["sum_toptrader_long_short_ratio"] = data.sum_toptrader_long_short_ratio
            current_instrument["count_long_short_ratio"] = data.count_long_short_ratio
            current_instrument["latest_open_interest_value"] = data.sum_open_interest_value

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
        time_after_listing_close = self.config.time_after_listing_close
        if not self.config.hold_profit_for_remaining_days:
            return False
            
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
        
        # Handle both single value and array for optimization
        time_after_listing = self.config.time_after_listing_close
        if isinstance(time_after_listing, list):
            time_after_listing = time_after_listing[0]  # Use first value for strategy logic
            
        deadline = onboard_date + timedelta(days=time_after_listing)
        
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
        self.aroon_simple_trend_setup(bar, current_instrument)
    
    def aroon_simple_trend_setup(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_aroon_simple_trend_system.get("enabled", False):
            return
        
        aroon = current_instrument["aroon"]
        if not aroon.initialized:
            return
            
        aroon_osc_value = float(aroon.value)
        short_threshold = current_instrument["aroon_osc_short_threshold"]
        
        if (aroon_osc_value <= short_threshold):
            self.enter_short_aroon_trend(bar, current_instrument)

    def enter_short_aroon_trend(self, bar: Bar, current_instrument: Dict[str, Any]):   
        instrument_id = bar.bar_type.instrument_id
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
            self.order_types.submit_short_market_order(instrument_id, qty)
    
    def short_exit_logic(self, bar: Bar, current_instrument: Dict[str, Any], position):
        current_instrument["bars_since_entry"] += 1      # ✅ HAS THIS
        sl_price = current_instrument.get("sl_price")
        instrument_id = bar.bar_type.instrument_id
        
        if sl_price is not None and float(bar.close) >= sl_price:
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_long_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
            current_instrument["prev_bar_close"] = float(bar.close)
            return

        if self.check_time_based_exit(bar, current_instrument, position):
            close_qty = min(int(abs(position.quantity)), abs(position.quantity))
            if close_qty > 0:
                self.order_types.submit_long_market_order(instrument_id, int(close_qty))
            self.reset_position_tracking(current_instrument)
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        if self.config.hold_profit_for_remaining_days:
            current_instrument["prev_bar_close"] = float(bar.close)
            return

    def reset_position_tracking(self, current_instrument: Dict[str, Any]):
        current_instrument["short_entry_price"] = None
        current_instrument["bars_since_entry"] = 0
        current_instrument["sl_price"] = None
        current_instrument["in_short_position"] = False     



    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)

        # Lunar data indicators
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="interactions", value=current_instrument.get("interactions", 0.0))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="posts_created", value=current_instrument.get("posts_created", 0.0))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="sentiment", value=current_instrument.get("sentiment", 0.0))

        # Metrics data indicators
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="toptr_long_short_ratio", value=current_instrument.get("sum_toptrader_long_short_ratio", 0.0))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="count_long_short_ratio", value=current_instrument.get("count_long_short_ratio", 0.0))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="open_interest_value", value=current_instrument.get("latest_open_interest_value", 0.0))

        # Aroon Oscillator (position 1)
        if self.config.use_aroon_simple_trend_system.get("enabled", False):
            aroon = current_instrument["aroon"]
            aroon_osc_value = float(aroon.value) if aroon.value is not None else None
            current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="aroon_osc", value=aroon_osc_value)


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