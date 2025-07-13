# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------
 
from decimal import Decimal
from typing import Any

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import ExecAlgorithmId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_dt

from tools.help_funcs.base_strategy import BaseStrategy
from tools.help_funcs.help_funcs_strategy import create_tags
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager

# *** THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
# *** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***


class EMACrossTWAPConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    fast_ema_period: PositiveInt = 10
    slow_ema_period: PositiveInt = 20
    twap_horizon_secs: PositiveFloat = 30.0
    twap_interval_secs: PositiveFloat = 3.0
    close_positions_on_stop: bool = True


class EMACrossTWAP(BaseStrategy, Strategy):

    def __init__(self, config: EMACrossTWAPConfig) -> None:
        super().__init__(config)
        self.collector = BacktestDataCollector()
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.realized_pnl = 0
        PyCondition.is_true(
            config.fast_ema_period < config.slow_ema_period,
            "{config.fast_ema_period=} must be less than {config.slow_ema_period=}",
        )
        PyCondition.is_true(
            config.twap_interval_secs <= config.twap_horizon_secs,
            "{config.twap_interval_secs=} must be less than or equal to {config.twap_horizon_secs=}",
        )

        
        # Create the indicators for the strategy
        self.fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(config.slow_ema_period)

        # Order management
        self.twap_exec_algorithm_id = ExecAlgorithmId("TWAP")
        self.twap_exec_algorithm_params: dict[str, Any] = {
            "horizon_secs": config.twap_horizon_secs,
            "interval_secs": config.twap_interval_secs,
        }

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        
        self.risk_manager = RiskManager(self)
        self.order_types = OrderTypes(self)
        self.collector.initialise_logging_indicator("fast_ema", 0)
        self.collector.initialise_logging_indicator("slow_ema", 0)
        self.collector.initialise_logging_indicator("position", 1)
        self.collector.initialise_logging_indicator("realized_pnl", 2)
        self.collector.initialise_logging_indicator("unrealized_pnl", 3)
        self.collector.initialise_logging_indicator("balance", 4)

        # Register the indicators for updating
        self.register_indicator_for_bars(self.config.bar_type, self.fast_ema)
        self.register_indicator_for_bars(self.config.bar_type, self.slow_ema)

        # Get historical data
        self.request_bars(self.config.bar_type)

        # Subscribe to live data
        self.subscribe_bars(self.config.bar_type)
        self.subscribe_quote_ticks(self.config.instrument_id)
        self._plot_log = []

    def get_position(self):
        return self.base_get_position()

    def on_instrument(self, instrument: Instrument) -> None:
        pass

    def on_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        pass

    def on_order_book(self, order_book: OrderBook) -> None:
        pass

    def on_quote_tick(self, tick: QuoteTick) -> None:
        pass

    def on_trade_tick(self, tick: TradeTick) -> None:
        pass
    
    def on_bar(self, bar: Bar) -> None:
        self.log.info(repr(bar), LogColor.CYAN)

        # Check if indicators ready
        if not self.indicators_initialized():
            self.log.info(
                f"Waiting for indicators to warm up [{self.cache.bar_count(self.config.bar_type)}]",
                color=LogColor.BLUE,
            )
            return  # Wait for indicators to warm up...

        if bar.is_single_price():
            # Implies no market information for this bar
            return
        
        signal = "HOLD"

        # BUY LOGIC
        if self.fast_ema.value >= self.slow_ema.value:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
                signal = "BUY"
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
                signal = "BUY"
        # SELL LOGIC
        elif self.fast_ema.value < self.slow_ema.value:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.sell()
                signal = "SELL"
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.sell()
                signal = "SELL"

        # Log indicator values and signal for visualization
        self.collector.add_indicator(timestamp=bar.ts_event, name="fast_ema", value=float(self.fast_ema.value) if self.fast_ema.value is not None else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="slow_ema", value=float(self.slow_ema.value) if self.slow_ema.value is not None else None)
        self.collector.add_bar(timestamp=bar.ts_event,open_=bar.open, high=bar.high, low=bar.low, close=bar.close)

    def on_order_filled(self, order_filled) -> None:
        ret = self.collector.add_trade_details(order_filled)
    
    def buy(self) -> None:
        self.order_types.submit_long_market_order(self.config.trade_size)

    def sell(self) -> None:
        self.order_types.submit_short_market_order(self.config.trade_size)

    def on_data(self, data: Data) -> None:
        pass

    def on_event(self, event: Event) -> None:
        pass

    def close_position(self) -> None:
        return self.base_close_position()
    
    def on_stop(self) -> None:
        self.base_on_stop()
        # VISUALIZER UPDATEN
        try:
            unrealized_pnl = self.portfolio.unrealized_pnl(self.config.instrument_id)
        except Exception as e:
            self.log.warning(f"Could not calculate unrealized PnL: {e}")
            unrealized_pnl = None
        venue = self.config.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()

        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="balance", value=usd_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.config.instrument_id) if self.portfolio.net_position(self.config.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        #self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="RSI", value=float(self.rsi.value) if self.rsi.value is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="fast_ema", value=float(self.fast_ema.value) if self.fast_ema.value is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="slow_ema", value=float(self.slow_ema.value) if self.slow_ema.value is not None else None)

        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

    def on_reset(self) -> None:
        self.fast_ema.reset()
        self.slow_ema.reset()

    def on_save(self) -> dict[str, bytes]:
        return {}

    def on_load(self, state: dict[str, bytes]) -> None:
        pass

    def on_dispose(self) -> None:
        pass