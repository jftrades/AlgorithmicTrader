from decimal import Decimal
from typing import Any, Dict, Optional, List

from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType, TradeTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.events import PositionEvent
from nautilus_trader.model.currencies import Currency

from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from nautilus_trader.indicators.rsi import RelativeStrengthIndex


class RSITickSimpleStrategyConfig(StrategyConfig):
    instruments: list[dict]
    risk_percent: float
    max_leverage: float     
    min_account_balance: float
    trade_size_usdt: Decimal
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
        self.trade_size_usdt = config.trade_size_usdt
        self.close_positions_on_stop = config.close_positions_on_stop
        self.tick_buffer_size = config.tick_buffer_size 
        self.rsi_period = config.rsi_period
        self.rsi_overbought = config.rsi_overbought
        self.rsi_oversold = config.rsi_oversold
        self.stopped = False
        self.tick_counter = 0
        self.realized_pnl = 0
        
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
                'last_rsi': None,
                'trade_ticks': [],
                'last_logged_balance': None,
                'tick_counter': 0
            }

    def on_start(self) -> None:
        # Initialize managers
        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)
        
        for inst_id, ctx in self.instrument_dict.items():
            # Subscribe to trade ticks for tick-based strategy
            self.subscribe_trade_ticks(inst_id)
            
            # Subscribe to bars for RSI calculation
            for bar_type in ctx['bar_types']:
                if isinstance(bar_type, str):
                    bar_type = BarType.from_str(bar_type)
                self.subscribe_bars(bar_type)
            
            # Initialize last RSI value
            self.instrument_state[inst_id]['last_rsi'] = self.instrument_state[inst_id]['rsi'].value
            
            # Log starting balance for each venue
            venue = inst_id.venue
            account = self.portfolio.account(venue)
            if account:
                usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double()
                self.instrument_state[inst_id]['last_logged_balance'] = usdt_balance
                self.log.info(f"USDT balance for {inst_id}: {usdt_balance}")
            else:
                self.log.warning(f"No account found for venue: {venue}")
        
        self.log.info("Multi-Instrument Tick Strategy started!")

    def on_bar(self, bar: Bar):
        instrument_id = bar.bar_type.instrument_id
        if instrument_id in self.instrument_state:
            state = self.instrument_state[instrument_id]
            instrument_dict = self.instrument_dict[instrument_id]
            state['rsi'].handle_bar(bar)
            state['last_rsi'] = state['rsi'].value if state['rsi'].initialized else None
            self.base_collect_bar_data(bar, instrument_dict)

    def on_trade_tick(self, tick: TradeTick) -> None:  
        instrument_id = tick.instrument_id
        if instrument_id not in self.instrument_state:
            return
            
        state = self.instrument_state[instrument_id]
        
        trade_size_usdt = float(self.trade_size_usdt)
        qty = max(1, int(trade_size_usdt // float(tick.price)))
        rsi_value = state['rsi'].value if state['rsi'].initialized else None
        
        if rsi_value is None:
            return
            
        state['tick_counter'] += 1
        state['trade_ticks'].append(tick)
        if len(state['trade_ticks']) > self.tick_buffer_size:
            state['trade_ticks'].pop(0)
        
        # Check for open orders to avoid endless orders
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        
        # Entry/Exit Logic - tick-precise
        if rsi_value > self.rsi_overbought:
            if state['last_rsi_cross'] != "rsi_overbought":
                self.close_position(instrument_id)
                self.order_types.submit_short_market_order(qty, instrument_id)
            state['last_rsi_cross'] = "rsi_overbought"
        elif rsi_value < self.rsi_oversold:
            if state['last_rsi_cross'] != "rsi_oversold":
                self.close_position(instrument_id)
                self.order_types.submit_long_market_order(qty, instrument_id)
            state['last_rsi_cross'] = "rsi_oversold"

        venue = instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(Currency.from_str("USDT")).as_double() if account else 0

        self.update_visualizer_data(tick, usdt_balance, rsi_value, instrument_id)

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

    def update_visualizer_data(self, tick: TradeTick, usdt_balance: float, rsi_value: float, instrument_id: InstrumentId) -> None:
        state = self.instrument_state[instrument_id]
        net_position = self.portfolio.net_position(instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(instrument_id)
        venue = instrument_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balances_total()
        
        state['tick_counter'] += 1
        if state['tick_counter'] % 1000 == 0:
            self.collector.add_indicator(timestamp=tick.ts_event, name="position", value=net_position)
            self.collector.add_indicator(timestamp=tick.ts_event, name="RSI", value=float(rsi_value))
            self.collector.add_indicator(timestamp=tick.ts_event, name="unrealized_pnl", 
                                       value=float(unrealized_pnl) if unrealized_pnl else None)
            self.collector.add_indicator(timestamp=tick.ts_event, name="realized_pnl", value=float(self.realized_pnl))
            self.collector.add_indicator(timestamp=tick.ts_event, name="balance", value=usdt_balance.as_double())
