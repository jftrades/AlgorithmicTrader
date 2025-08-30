from decimal import Decimal
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
        self.close_positions_on_stop = config.close_positions_on_stop
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.stopped = False
        self.realized_pnl = 0
        self.bar_counter = 0
        
        # Initialize managers
        self.risk_manager = None
        self.order_types = None
        
        # Initialize per-instrument state tracking
        self.instrument_state = {}
        
        # Add instrument context after BaseStrategy is initialized
        self.add_instrument_context()

    def add_instrument_context(self):
        # Per-instrument state tracking using instrument_dict (populated by BaseStrategy)
        for current_instrument in self.instrument_dict.values():
            instrument_id = current_instrument["instrument_id"]
            self.instrument_state[instrument_id] = {
                'rsi': RelativeStrengthIndex(period=self.rsi_period),
                'last_rsi_cross': None,
                'breakout_analyser': TTTBreakout_Analyser(
                    lookback=self.config.ttt_lookback,
                    atr_mult=self.config.ttt_atr_mult,
                    max_counter=self.config.ttt_max_counter
                )
            }

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

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        if instrument_id not in self.instrument_state:
            return
            
        state = self.instrument_state[instrument_id]
        instrument_dict = self.instrument_dict[instrument_id]
        
        # Update indicators
        state['breakout_analyser'].update_bars(bar)
        state['rsi'].handle_bar(bar) 
        self.base_collect_bar_data(bar, instrument_dict)
        self.update_visualizer_data(bar, instrument_dict)

        # Check for TTT Breakout
        is_breakout, breakout_dir = state['breakout_analyser'].is_tttbreakout()

        # Check for open orders
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return

        if not state['rsi'].initialized:
            self.log.warning(f"RSI not initialized yet for {instrument_id} - skipping trading logic")
            return

        # Trading logic with RSI filter
        if is_breakout:
            current_rsi = state['rsi'].value
            if breakout_dir == "long" and current_rsi is not None and 0.6 <= current_rsi <= 0.9:
                self.execute_long_trade(bar, instrument_id, state, instrument_dict)
            elif breakout_dir == "short" and current_rsi is not None and 0.1 <= current_rsi <= 0.4:
                self.execute_short_trade(bar, instrument_id, state, instrument_dict)

    def execute_long_trade(self, bar: Bar, instrument_id: InstrumentId, state: dict, instrument_dict: dict):
        self.log.info(f"Executing LONG trade for {instrument_id}: RSI oversold + TTT breakout")
        entry_price = Decimal(str(bar.close))
        atr = state['breakout_analyser']._calc_atr()
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

    def execute_short_trade(self, bar: Bar, instrument_id: InstrumentId, state: dict, instrument_dict: dict):
        self.log.info(f"Executing SHORT trade for {instrument_id}: RSI overbought + TTT breakout")
        entry_price = Decimal(str(bar.close))
        atr = state['breakout_analyser']._calc_atr()
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
        
        # Custom indicators - access from instrument_state where we store them
        state = self.instrument_state[instrument_id]
        rsi_value = float(state['rsi'].value) if state['rsi'].value is not None else None
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
