# in here is the coin short strategy to short coins that have been listed for 14 days
from decimal import Decimal
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional, List
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.common.enums import LogColor

from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
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

    fast_ema_period: int = 12
    slow_ema_period: int = 26

    only_trade_rth: bool = True
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
            current_instrument["collector"].initialise_logging_indicator("slow_ema", 0)
            current_instrument["collector"].initialise_logging_indicator("fast_ema", 0)
            current_instrument["slow_ema"] = ExponentialMovingAverage(self.config.slow_ema_period)
            current_instrument["fast_ema"] = ExponentialMovingAverage(self.config.fast_ema_period)
            current_instrument ["slow_ema_period"] = 26
            current_instrument ["fast_ema_period"] = 12
            current_instrument["prev_fast_ema"] = None
            current_instrument["prev_slow_ema"] = None
            
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
        if current_instrument is None:
            self.log.warning(f"No instrument found for {instrument_id}", LogColor.RED)
            return
        slow_ema = current_instrument["slow_ema"]
        fast_ema = current_instrument["fast_ema"]
        fast_ema.handle_bar(bar)
        slow_ema.handle_bar(bar)

        if not fast_ema.initialized or not slow_ema.initialized:
            return

        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        
        if not self.is_rth_time(bar, current_instrument):
            return

        self.entry_logic(bar, current_instrument)
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

    def entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))

        slow_ema_value = current_instrument["slow_ema"].value
        fast_ema_value = current_instrument["fast_ema"].value
        prev_slow_ema = current_instrument.get("prev_slow_ema")
        prev_fast_ema = current_instrument.get("prev_fast_ema")

        if slow_ema_value is None or fast_ema_value is None:
            return

        if slow_ema_value is None:
            return
        if fast_ema_value is None:
            return
        
        if (prev_fast_ema is not None and prev_slow_ema is not None and
            prev_fast_ema > prev_slow_ema and
            fast_ema_value < slow_ema_value):
            
            self.log.info(f"Bearish EMA Crossover detected for {instrument_id}. Going SHORT.", LogColor.MAGENTA)
            self.submit_short_market_order(instrument_id, int(qty))

        current_instrument["prev_fast_ema"] = fast_ema_value
        current_instrument["prev_slow_ema"] = slow_ema_value 

    def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_long_market_order(instrument_id, qty)

    def submit_short_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)
        #custom indicators

        slow_ema_value = float(current_instrument["slow_ema"].value) if current_instrument["slow_ema"].value is not None else None
        fast_ema_value = float(current_instrument["fast_ema"].value) if current_instrument["fast_ema"].value is not None else None
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="Slow EMA", value=slow_ema_value)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="Fast EMA", value=fast_ema_value)

    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: Optional[InstrumentId] = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)
