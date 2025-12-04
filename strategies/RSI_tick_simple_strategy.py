from decimal import Decimal
from typing import Any, Dict, List

from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, TradeTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.common.enums import LogColor
from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from nautilus_trader.indicators.momentum import RelativeStrengthIndex


class RSITickSimpleStrategyConfig(StrategyConfig):
    instruments: List[dict]
    risk_percent: float
    max_leverage: float     
    min_account_balance: float
    tick_buffer_size: int
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    run_id: str
    close_positions_on_stop: bool = True

class RSITickSimpleStrategy(BaseStrategy, Strategy):
    def __init__(self, config: RSITickSimpleStrategyConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config)
        self.risk_manager = None
        self.order_types = None
        self.add_instrument_context()

    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            rsi_period = current_instrument.get("rsi_period", getattr(self.config, "rsi_period"))
            rsi_overbought = current_instrument.get("rsi_overbought", getattr(self.config, "rsi_overbought"))
            rsi_oversold = current_instrument.get("rsi_oversold", getattr(self.config, "rsi_oversold"))
            tick_buffer_size = current_instrument.get("tick_buffer_size", getattr(self.config, "tick_buffer_size"))
            
            current_instrument["collector"].initialise_logging_indicator("RSI", 1)
            current_instrument["rsi_period"] = rsi_period
            current_instrument["rsi_overbought"] = rsi_overbought
            current_instrument["rsi_oversold"] = rsi_oversold
            current_instrument["tick_buffer_size"] = tick_buffer_size
            current_instrument["rsi"] = RelativeStrengthIndex(period=rsi_period)
            current_instrument["last_rsi_cross"] = None
            current_instrument["last_rsi"] = None
            current_instrument["trade_ticks"] = []
            current_instrument["tick_counter"] = 0

    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            # Subscribe to trade ticks for tick-based strategy
            self.subscribe_trade_ticks(inst_id)
            self.log.info(f"Subscribed to trade ticks for {inst_id}")
            
            # Subscribe to bars for RSI calculation
            for bar_type in ctx["bar_types"]:
                self.log.info(f"Subscribing to bars: {str(bar_type)}", color=LogColor.GREEN)
                self.subscribe_bars(bar_type)
            
            # Initialize last RSI value
            ctx['last_rsi'] = ctx['rsi'].value
        
        self.log.info(f"Strategy started. Instruments: {', '.join(str(i) for i in self.instrument_ids())}")
        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)

    # -------------------------------------------------
    # Ereignis Routing
    # -------------------------------------------------
    def on_bar(self, bar: Bar):
        # Only update RSI with bar data, no trading logic on bars
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return

        # RSI needs bar data to calculate properly
        current_instrument['rsi'].handle_bar(bar)
        current_instrument['last_rsi'] = current_instrument['rsi'].value if current_instrument['rsi'].initialized else None
        
        # Collect bar data for base strategy functionality
        self.base_collect_bar_data(bar, current_instrument)

    def on_trade_tick(self, tick: TradeTick) -> None:  
        instrument_id = tick.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return
        
        current_instrument['tick_counter'] += 1
        # Update tick data
        current_instrument['trade_ticks'].append(tick)
        if len(current_instrument['trade_ticks']) > current_instrument["tick_buffer_size"]:
            current_instrument['trade_ticks'].pop(0)
        
        rsi = current_instrument["rsi"]
            
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
            
        self.entry_logic(tick, current_instrument)
        self.update_visualizer_data(tick, current_instrument)

    # -------------------------------------------------
    # Entry Logic pro Instrument
    # -------------------------------------------------
    def entry_logic(self, tick: TradeTick, current_instrument: Dict[str, Any]):
        instrument_id = tick.instrument_id
        trade_size_usdt = float(current_instrument.get("trade_size_usdt", 1000))  # Default fallback
        qty = max(1, int(trade_size_usdt // float(tick.price)))
        rsi_value = current_instrument["rsi"].value
        
        if rsi_value is None:
            return
            
        last_cross = current_instrument["last_rsi_cross"]
        overbought = current_instrument["rsi_overbought"]
        oversold = current_instrument["rsi_oversold"]

        # Entry/Exit Logic - tick-precise
        if rsi_value > overbought:
            if last_cross != "rsi_overbought":
                self.close_position(instrument_id)
                self.submit_short_market_order(instrument_id, qty)
            current_instrument["last_rsi_cross"] = "rsi_overbought"
        elif rsi_value < oversold:
            if last_cross != "rsi_oversold":
                self.close_position(instrument_id)
                self.submit_long_market_order(instrument_id, qty)
            current_instrument["last_rsi_cross"] = "rsi_oversold"

    # -------------------------------------------------
    # Order Submission Wrapper (Instrument-Aware, intern noch Single)
    # -------------------------------------------------
    def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_long_market_order(instrument_id, qty)

    def submit_short_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    # -------------------------------------------------
    # Visualizer / Logging pro Instrument (Tick-Based)
    # -------------------------------------------------        
    def update_visualizer_data(self, tick: TradeTick, current_instrument: Dict[str, Any]) -> None:
        instrument_id = tick.instrument_id
        self.base_update_standard_indicators(tick.ts_event, current_instrument, instrument_id)

        # Custom indicators - RSI value from tick-based updates
        rsi_value = float(current_instrument['rsi'].value) if current_instrument['rsi'].value is not None else None
        current_instrument["collector"].add_indicator(timestamp=tick.ts_event, name="RSI", value=rsi_value)
        
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def on_stop(self) -> None:
        # Override to avoid KeyError in base_strategy on_stop
        self.log.info("RSI Tick Strategy stopped successfully!")
    
    def close_position(self, instrument_id: InstrumentId = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)
