from decimal import Decimal
import time
from typing import Any, Dict, Optional, List

from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.events import PositionEvent

from tools.structure.TTTbreakout import TTTBreakout_Analyser
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from tools.help_funcs.base_strategy import BaseStrategy
from nautilus_trader.indicators.rsi import RelativeStrengthIndex


class MeanRSITTTStrategyConfig(StrategyConfig):
    instruments: list[dict]
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    ttt_lookback: int
    ttt_atr_mult: float
    ttt_max_counter: int
    run_id: str
    close_positions_on_stop: bool = True

class MeanRSITTTStrategy(BaseStrategy, Strategy):
    def __init__(self, config: MeanRSITTTStrategyConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config)
        
        # Initialize managers
        self.risk_manager = None
        self.order_types = None
        self.add_instrument_context()

    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            rsi_period = current_instrument.get("rsi_period", getattr(self.config, "rsi_period"))
            rsi_overbought = current_instrument.get("rsi_overbought", getattr(self.config, "rsi_overbought"))
            rsi_oversold = current_instrument.get("rsi_oversold", getattr(self.config, "rsi_oversold"))
            
            # Initialize collector for RSI logging
            current_instrument["collector"].initialise_logging_indicator("RSI", 1)
            
            # Store RSI parameters
            current_instrument["rsi_period"] = rsi_period
            current_instrument["rsi_overbought"] = rsi_overbought
            current_instrument["rsi_oversold"] = rsi_oversold
            current_instrument["rsi"] = RelativeStrengthIndex(period=rsi_period)
            current_instrument["last_rsi_cross"] = None
            
            # Initialize TTT breakout analyzer
            current_instrument["breakout_analyser"] = TTTBreakout_Analyser(
                lookback=self.config.ttt_lookback,
                atr_mult=self.config.ttt_atr_mult,
                max_counter=self.config.ttt_max_counter
            )

    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            # Subscribe to bars for RSI and TTT calculations
            for bar_type in ctx['bar_types']:
                if isinstance(bar_type, str):
                    bar_type = BarType.from_str(bar_type)
                self.subscribe_bars(bar_type)
        
        # Initialize risk manager
        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)
        
        self.log.info("Multi-Instrument RSI TTT Strategy started!")

    # -------------------------------------------------
    # Ereignis Routing
    # -------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return
                    
        # Update indicators
        current_instrument['breakout_analyser'].update_bars(bar)
        current_instrument['rsi'].handle_bar(bar) 
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

        # Check for TTT Breakout
        is_breakout, breakout_dir = current_instrument['breakout_analyser'].is_tttbreakout()

        # Check for open orders
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return

        if not current_instrument['rsi'].initialized:
            self.log.warning(f"RSI not initialized yet for {instrument_id} - skipping trading logic")
            return

        # Trading logic with RSI filter
        if is_breakout:
            current_rsi = current_instrument['rsi'].value
            overbought = current_instrument["rsi_overbought"] 
            oversold = current_instrument["rsi_oversold"]
            
            if breakout_dir == "long" and current_rsi is not None and current_rsi < oversold:
                self.execute_long_trade(bar, instrument_id, current_instrument)
            elif breakout_dir == "short" and current_rsi is not None and current_rsi > overbought:
                self.execute_short_trade(bar, instrument_id, current_instrument)

    def execute_long_trade(self, bar: Bar, instrument_id: InstrumentId, current_instrument: dict):
        self.log.info(f"Executing LONG trade for {instrument_id}: RSI oversold + TTT breakout")
        entry_price = Decimal(str(bar.close))
        atr = current_instrument['breakout_analyser']._calc_atr()
        stop_loss = entry_price - 3 * atr
        take_profit = entry_price + 25 * atr

        # Calculate investment percentage based on risk management
        # Using risk_percent to determine position size
        invest_percent = Decimal(str(self.config.risk_percent * 10))  # Convert risk to investment
        
        position_size, valid_position = self.risk_manager.calculate_investment_size(
            invest_percent, entry_price, instrument_id
        )
        
        if not valid_position or position_size <= 0:
            self.log.warning(f"Invalid position size for {instrument_id}: {position_size}")
            return

        self.order_types.submit_long_bracket_order(instrument_id, position_size, entry_price, stop_loss, take_profit)

    def execute_short_trade(self, bar: Bar, instrument_id: InstrumentId, current_instrument: dict):
        self.log.info(f"Executing SHORT trade for {instrument_id}: RSI overbought + TTT breakout")
        entry_price = Decimal(str(bar.close))
        atr = current_instrument['breakout_analyser']._calc_atr()
        stop_loss = entry_price + 3 * atr
        take_profit = entry_price - 5 * atr

        # Calculate investment percentage based on risk management
        # Using risk_percent to determine position size
        invest_percent = Decimal(str(self.config.risk_percent * 10))  # Convert risk to investment
        
        position_size, valid_position = self.risk_manager.calculate_investment_size(
            invest_percent, entry_price, instrument_id
        )
        
        if not valid_position or position_size <= 0:
            self.log.warning(f"Invalid position size for {instrument_id}: {position_size}")
            return

        self.order_types.submit_short_bracket_order(instrument_id, position_size, entry_price, stop_loss, take_profit)

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self, instrument_id: InstrumentId = None) -> None:
        if instrument_id:
            return self.base_close_position(instrument_id)
        else:
            # Close all positions
            for instrument_dict in self.config.instruments:
                inst_id = InstrumentId.from_str(instrument_dict['instrument_id'])
                self.base_close_position(inst_id)
    
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        instrument_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, instrument_id)
        
        # Custom indicators - access from current_instrument where we store them
        rsi_value = float(current_instrument['rsi'].value) if current_instrument['rsi'].value is not None else None
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
