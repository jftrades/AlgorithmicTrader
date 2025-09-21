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

class CoinShortConfig(StrategyConfig):
    instruments: List[dict]  
    max_leverage: float
    min_account_balance: float
    run_id: str

    use_trend_following_setup: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "entry_trend_ema_period": 20,
            "min_bars_over_ema": 5
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
            current_instrument["collector"].initialise_logging_indicator("entry_trend_ema", 0)
            trend_config = self.config.use_trend_following_setup
            entry_trend_ema_period = trend_config.get("entry_trend_ema_period", 20)
            min_bars_over_ema = trend_config.get("min_bars_over_ema", 5)
            current_instrument["entry_trend_ema"] = ExponentialMovingAverage(entry_trend_ema_period)
            current_instrument["entry_trend_ema_period"] = entry_trend_ema_period
            current_instrument["prev_entry_trend_ema"] = None

            trend_config = self.config.use_trend_following_setup
            atr_period = trend_config.get("atr_period", 14)
            current_instrument["atr"] = AverageTrueRange(atr_period)
            current_instrument["sl_atr_multiple"] = trend_config.get("sl_atr_multiple", 2)
            current_instrument["sl_price"] = None

            current_instrument["bars_over_ema_count"] = 0
            current_instrument["prev_bar_close"] = None
            current_instrument["min_bars_over_ema"] = min_bars_over_ema
            current_instrument["short_entry_price"] = None  # Add this to track entry price
            current_instrument["bars_since_entry"] = 0  # Add this to track bars since entry
            current_instrument["min_bars_before_exit"] = 10
            
            current_instrument["only_trade_rth"] = self.config.only_trade_rth
            current_instrument["rth_start_hour"] = 14
            current_instrument["rth_start_minute"] = 30
            current_instrument["rth_end_hour"] = 21
            current_instrument["rth_end_minute"] = 0        

    def is_rth_time(self, bar: Bar, current_instrument: Dict[str, Any]) -> bool:
        if not current_instrument["only_trade_rth"]:
            return True
            
        bar_time = datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=timezone.utc).time()
        rth_start = time(current_instrument["rth_start_hour"], current_instrument["rth_start_minute"])
        rth_end = time(current_instrument["rth_end_hour"], current_instrument["rth_end_minute"])
        
        return rth_start <= bar_time <= rth_end
    
    def on_bar (self, bar:Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        current_instrument["atr"].handle_bar(bar)

        if current_instrument is None:
            self.log.warning(f"No instrument found for {instrument_id}", LogColor.RED)
            return
        entry_trend_ema = current_instrument["entry_trend_ema"]
        entry_trend_ema.handle_bar(bar)

        if not entry_trend_ema.initialized:
            return

        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        
        if not self.is_rth_time(bar, current_instrument):
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

            # --- SL logic: price >= SL price (for shorts) ---
            sl_price = current_instrument.get("sl_price")
            if sl_price is not None and float(bar.close) >= sl_price:
                self.log.info(f"SL hit for {instrument_id}: close={bar.close} >= SL={sl_price:.4f}", LogColor.RED)
                self.sl_trend_following_setup(instrument_id, int(position.quantity))
                current_instrument["short_entry_price"] = None
                current_instrument["bars_since_entry"] = 0
                current_instrument["sl_price"] = None
                current_instrument["prev_bar_close"] = float(bar.close)
                return

            # --- TP logic ---
            if (float(bar.close) > entry_trend_ema_value and
                entry_price is not None and 
                float(bar.close) < entry_price and  # In profit
                bars_since_entry >= min_bars_required):  # Minimum bars passed

                self.tp_trend_following_setup(instrument_id, int(position.quantity))
                current_instrument["short_entry_price"] = None
                current_instrument["bars_since_entry"] = 0
                current_instrument["sl_price"] = None

            current_instrument["prev_bar_close"] = float(bar.close)
            return
        
        if float(bar.close) > entry_trend_ema_value:
            current_instrument["bars_over_ema_count"] += 1

        if prev_bar_close is None:
            current_instrument["prev_bar_close"] = float(bar.close)
            return

        min_bars_required = current_instrument["min_bars_over_ema"]
        if (prev_bar_close > entry_trend_ema_value and 
            float(bar.close) < entry_trend_ema_value and
            current_instrument["bars_over_ema_count"] >= min_bars_required):
            
            self.log.info(
                f"Short signal for {instrument_id}: prev_close={prev_bar_close:.4f} > EMA={entry_trend_ema_value:.4f}, current_close={bar.close} < EMA. Bars over EMA: {current_instrument['bars_over_ema_count']}",
                LogColor.MAGENTA
            )
            self.short_trend_following_setup_market_order(instrument_id, int(qty))
            current_instrument["short_entry_price"] = float(bar.close)
            current_instrument["bars_since_entry"] = 0  # Reset counter on new entry

            # Set SL price for short: entry + N*ATR
            atr_value = current_instrument["atr"].value
            sl_atr_multiple = current_instrument["sl_atr_multiple"]
            if atr_value is not None:
                current_instrument["sl_price"] = float(bar.close) + sl_atr_multiple * atr_value
            else:
                current_instrument["sl_price"] = None

        if float(bar.close) <= entry_trend_ema_value:
            current_instrument["bars_over_ema_count"] = 0

    # def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
     #   self.order_types.submit_long_market_order(instrument_id, qty)

    def short_trend_following_setup_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    def tp_trend_following_setup(self, instrument_id: InstrumentId, qty: int):
        position = self.base_get_position(instrument_id)
        if position is None or position.quantity < 0:
            return
        close_qty = min(qty, abs(position.quantity))
        if close_qty <= 0:
            return
        self.order_types.submit_long_market_order(instrument_id, int(close_qty))
    
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
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: Optional[InstrumentId] = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)
