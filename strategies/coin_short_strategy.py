# in here is the coin short strategy to short coins that have been listed for 14 days
from decimal import Decimal
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional, List
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.enums import OrderSide, TimeInForce, PositionSide
from nautilus_trader.common.enums import LogColor
from pydantic import Field

from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from nautilus_trader.indicators.atr import AverageTrueRange
from tools.help_funcs.base_strategy import BaseStrategy
from tools.structure.TTTbreakout import TTTBreakout_Analyser
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags   
from nautilus_trader.common.enums import LogColor
from data.download.crypto_downloads.custom_class.metrics_data import MetricsData

class CoinShortConfig(StrategyConfig):
    instruments: List[dict]  
    max_leverage: float
    min_account_balance: float
    run_id: str

    use_trend_following_setup: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "entry_trend_ema_period": 20,
            "min_bars_over_ema": 5,
            "sl_atr_multiple": 2,
            "atr_period"    : 14
        }
    )
    use_min_coin_filters: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "min_price": 0.1,
            "min_24h_volume": 5000000,
            "min_sum_open_interest_value": 500000,
        }
    )

    use_metrics_trend_following: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "min_difference_topt_longshortratio": 0.2
        }
    )

    only_trade_rth: bool = False
    close_positions_on_stop: bool = True


class CoinShortStrategy(BaseStrategy,Strategy):
    def __init__(self, config: CoinShortConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config)
        self.risk_manager = RiskManager(config)
        self.order_types = OrderTypes(self) 
        self.add_instrument_context()
    
    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            
            # Trend following general setup
            trend_config = self.config.use_trend_following_setup
            entry_trend_ema_period = trend_config.get("entry_trend_ema_period", 20)
            current_instrument["entry_trend_ema"] = ExponentialMovingAverage(entry_trend_ema_period)
            atr_period = trend_config.get("atr_period", 14)
            current_instrument["atr"] = AverageTrueRange(atr_period)
            current_instrument["sl_atr_multiple"] = trend_config.get("sl_atr_multiple", 2)
            current_instrument["sl_price"] = None
            current_instrument["prev_bar_close"] = None
            current_instrument["short_entry_price"] = None
            current_instrument["bars_since_entry"] = 0
            current_instrument["min_bars_before_exit"] = 10
            current_instrument["only_trade_rth"] = self.config.only_trade_rth
            current_instrument["rth_start_hour"] = 14
            current_instrument["rth_start_minute"] = 30
            current_instrument["rth_end_hour"] = 21
            current_instrument["rth_end_minute"] = 0
            current_instrument["bars_above_ema"] = 0
            
            # Trend following L3 metrics
            l3_trend_metrics = self.config.use_metrics_trend_following
            current_instrument["use_metrics_trend_following"] = l3_trend_metrics.get("enabled", True)
            current_instrument["min_difference_topt_longshortratio"] = l3_trend_metrics.get("min_difference_topt_longshortratio", 0.2)
            current_instrument["count_toptrader_long_short_ratio"] = 0.0
            current_instrument["count_long_short_ratio"] = 0.0


            # Min coin filters
            coin_filters = self.config.use_min_coin_filters
            current_instrument["use_min_coin_filters"] = coin_filters.get("enabled", True)
            current_instrument["min_price"] = coin_filters.get("min_price", 0.1)
            current_instrument["min_24h_volume"] = coin_filters.get("min_24h_volume", 5000000)
            current_instrument["min_sum_open_interest_value"] = coin_filters.get("min_sum_open_interest_value", 500000)
            current_instrument["volume_history"] = []  # Store token volumes
            current_instrument["price_history"] = []   # Store prices for dollar volume calculation
            current_instrument["rolling_24h_volume"] = 0.0      # Token volume
            current_instrument["rolling_24h_dollar_volume"] = 0.0  # Dollar volume
            current_instrument["latest_open_interest_value"] = 0.0


    def on_start(self):
        super().on_start() if hasattr(super(), 'on_start') else None
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

    def difference_topt_longshortratio(self, current_instrument: Dict[str, Any]) -> Optional[float]:
        if not current_instrument.get("use_metrics_trend_following", False):
            return None
            
        count_topt = current_instrument.get("count_toptrader_long_short_ratio", 0.0)
        count_total = current_instrument.get("count_long_short_ratio", 0.0)
            
        if count_total == 0:
            return None
            
        difference = (count_topt - (count_total - count_topt)) / count_total
        return difference

    def on_data(self, data) -> None:
        if isinstance(data, MetricsData):
            self.on_metrics_data(data)

    def on_metrics_data(self, metrics_data: MetricsData) -> None:
        instrument_id = metrics_data.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        
        if current_instrument is not None:
            current_instrument["latest_open_interest_value"] = metrics_data.sum_open_interest_value
            current_instrument["count_toptrader_long_short_ratio"] = metrics_data.count_toptrader_long_short_ratio
            current_instrument["count_long_short_ratio"] = metrics_data.count_long_short_ratio

    def passes_coin_filters(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument.get("use_min_coin_filters", True):
            return True
        
        # Price filter
        min_price = current_instrument["min_price"]
        if min_price > 0 and float(bar.close) < min_price:
            return False
        
        # 24h volume filter  
        min_24h_volume = current_instrument["min_24h_volume"]
        if min_24h_volume > 0:
            rolling_24h_dollar_volume = current_instrument.get("rolling_24h_dollar_volume", 0.0)
            if rolling_24h_dollar_volume < min_24h_volume:
                return False
        
        # Open interest value filter
        min_open_interest_value = current_instrument["min_sum_open_interest_value"]
        if min_open_interest_value > 0:
            latest_open_interest_value = current_instrument.get("latest_open_interest_value", 0.0)
            if latest_open_interest_value < min_open_interest_value:
                return False
        
        return True

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)

        if current_instrument is None:
            self.log.warning(f"No instrument found for {instrument_id}", LogColor.RED)
            return

        self.update_rolling_24h_volume(bar, current_instrument)
        
        current_instrument["atr"].handle_bar(bar)
        entry_trend_ema = current_instrument["entry_trend_ema"]
        entry_trend_ema.handle_bar(bar)

        if not entry_trend_ema.initialized:
            return

        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        
        if not self.is_rth_time(bar, current_instrument):
            return

        if not self.passes_coin_filters(bar, current_instrument):
            return

        self.trend_following_setup_logic(bar, current_instrument)
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

    def trend_following_setup_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        if not self.config.use_trend_following_setup.get("enabled", True):
            return
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
        entry_trend_ema_value = current_instrument["entry_trend_ema"].value
        prev_bar_close = current_instrument.get("prev_bar_close")
        if entry_trend_ema_value is None:
            return
        position = self.base_get_position(instrument_id)
        if position is not None and position.side == PositionSide.SHORT:
            current_instrument["bars_since_entry"] += 1
            entry_price = current_instrument.get("short_entry_price")
            if entry_price is None:
                entry_price = float(position.avg_px_open) if hasattr(position, 'avg_px_open') else None
            bars_since_entry = current_instrument["bars_since_entry"]
            min_bars_required = current_instrument["min_bars_before_exit"]
            sl_price = current_instrument.get("sl_price")
            
            if sl_price is not None and float(bar.close) >= sl_price:
                self.sl_trend_following_setup(instrument_id, int(position.quantity))
                current_instrument["short_entry_price"] = None
                current_instrument["bars_since_entry"] = 0
                current_instrument["sl_price"] = None
                current_instrument["prev_bar_close"] = float(bar.close)
                return
            
            if (float(bar.close) < entry_price
                and entry_price is not None and
                bars_since_entry >= min_bars_required):
                self.tp_trend_following_setup(instrument_id, int(abs(position.quantity)))
            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        if prev_bar_close is None:
            current_instrument["prev_bar_close"] = float(bar.close)
            return

        prev_bar_close_f = float(prev_bar_close)
        bar_close_f = float(bar.close)
        ema_f = float(entry_trend_ema_value)
        min_bars_over_ema = self.config.use_trend_following_setup.get("min_bars_over_ema", 30)

        # Simple counter logic: if above EMA add +1, if below reset to 0
        if bar_close_f >= ema_f:
            current_instrument["bars_above_ema"] += 1
        else:
            # Check for short entry BEFORE resetting counter: cross below EMA AND had enough bars above EMA
            if (prev_bar_close_f >= ema_f and bar_close_f < ema_f and 
                current_instrument["bars_above_ema"] >= min_bars_over_ema):
                self.short_trend_following_setup_market_order(instrument_id, int(qty))
                current_instrument["short_entry_price"] = bar_close_f
                current_instrument["bars_since_entry"] = 0
                atr_value = current_instrument["atr"].value
                sl_atr_multiple = current_instrument["sl_atr_multiple"]
                if atr_value is not None:
                    current_instrument["sl_price"] = bar_close_f + sl_atr_multiple * atr_value
                else:
                    current_instrument["sl_price"] = None
            
            # Reset counter when below EMA
            current_instrument["bars_above_ema"] = 0
        
        current_instrument["prev_bar_close"] = bar_close_f

    # def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
     #   self.order_types.submit_long_market_order(instrument_id, qty)

    def short_trend_following_setup_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    def tp_trend_following_setup(self, instrument_id: InstrumentId, qty: int):
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return
            
        difference = self.difference_topt_longshortratio(current_instrument)
        if difference is not None:
            self.log.info(f"{instrument_id}: TopTrader diff = {difference:.3f}", LogColor.CYAN)
            
            # Check if we should close position based on difference
            min_diff = current_instrument["min_difference_topt_longshortratio"]
            if difference > min_diff:
                position = self.base_get_position(instrument_id)
                if position is not None and position.side == PositionSide.SHORT:
                    close_qty = min(qty, abs(position.quantity))
                    if close_qty <= 0:
                        return
                    self.order_types.submit_long_market_order(instrument_id, int(close_qty))
                    self.log.info(f"{instrument_id}: Closed short position - diff {difference:.3f} > {min_diff:.3f}", LogColor.GREEN)
    
    def sl_trend_following_setup(self, instrument_id: InstrumentId, qty: int):
        position = self.base_get_position(instrument_id)
        if position is None or position.quantity < 0:
            return
        close_qty = min(qty, abs(position.quantity))
        if close_qty <= 0:
            return
        self.order_types.submit_long_market_order(instrument_id, int(close_qty))

    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)

        entry_trend_ema_value = float(current_instrument["entry_trend_ema"].value) if current_instrument["entry_trend_ema"].value is not None else None

        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="entry_trend_ema", value=entry_trend_ema_value)

    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        instrument_id = position_closed.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is not None:
            current_instrument["short_entry_price"] = None
            current_instrument["bars_since_entry"] = 0
            current_instrument["bars_above_ema"] = 0
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: Optional[InstrumentId] = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)
