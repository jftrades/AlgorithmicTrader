# Roadmap:
# 1. Kalman Mean 10d oder Residual-Based Mean (Regression SPY vs Sektoren) als MEAN
# 2. 5d VWAP mit Z- Score aus nur RTH bars (diese auch gerade auf meinem rechner) -> da ETH sonst Ergebnis verfälscht (vllt auch feiner VWAP aus m bars)
# 3. GARCH (generalized autoregressive conditional heteroscedasticity) um nicht das "fallende Messer" zu kaufen 
# 4. wenn GARCH wieder stabil/ sich beruhigt + VWAP Z-Score passt -> Trade
# 5. Long Exit z.B. bis mean halten & Short Exit z.B. an Z-Scores partially auflösen

# Standard Library Importe
from decimal import Decimal
from typing import Any
import sys
from pathlib import Path
import numpy as np
# Nautilus Kern offizielle Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import MarketOrder, LimitOrder, StopMarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderEvent, PositionEvent
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.currencies import USDT, BTC

# Nautilus Kern eigene Importe !!! immer
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags
from tools.help_funcs.base_strategy import BaseStrategy
from nautilus_trader.common.enums import LogColor
from collections import deque
from tools.indicators.kalman_filter_1D import KalmanFilter1D
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTF
from tools.indicators.GARCH import GARCH

class Mean3ReversionHTFStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: str 
    trade_size: Decimal
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    vwap_zscore_entry_long: float
    vwap_zscore_entry_short: float
    vwap_lookback: int
    zscore_window: int
    kalman_process_var: float
    kalman_measurement_var: float
    kalman_window: int
    close_positions_on_stop: bool = True

class Mean3ReversionHTFStrategy(BaseStrategy, Strategy):
    def __init__(self, config:Mean3ReversionHTFStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.bar_type = BarType.from_str(config.bar_type)
        self.zscore_neutral_counter = 3
        self.prev_zscore = None
        self.current_kalman_mean = None
        self.stopped = False
        self.realized_pnl = 0
        self.bar_counter = 0
        self.prev_close = None
        self.vwap_zscore = VWAPZScoreHTF(
            zscore_window=config.zscore_window,
            zscore_entry_long = config.vwap_zscore_entry_long,
            zscore_entry_short = config.vwap_zscore_entry_short,
            vwap_lookback=config.vwap_lookback
        )
        self.kalman = KalmanFilter1D(process_var=config.kalman_process_var, measurement_var=config.kalman_measurement_var, window=config.kalman_window)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)
        self.log.info("Strategy started!")

        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)
        self.collector = BacktestDataCollector() 

        self.collector.initialise_logging_indicator("vwap", 0)
        self.collector.initialise_logging_indicator("kalman_mean", 0)
        self.collector.initialise_logging_indicator("vwap_zscore", 1)
        self.collector.initialise_logging_indicator("position", 2)
        self.collector.initialise_logging_indicator("realized_pnl", 3)
        self.collector.initialise_logging_indicator("unrealized_pnl", 4)
        self.collector.initialise_logging_indicator("balance", 5)

    def get_position(self):
        return self.base_get_position()
    
    def on_bar(self, bar: Bar) -> None:
        self.current_kalman_mean = self.kalman.update(float(bar.close))
        vwap_value, zscore = self.vwap_zscore.update(bar)
        self.current_zscore = zscore

        if self.current_kalman_mean is not None and zscore is not None:
            if bar.close < vwap_value and bar.close < self.current_kalman_mean:
                self.check_for_long_trades(bar, zscore)
            elif bar.close > vwap_value and bar.close > self.current_kalman_mean:
                self.check_for_short_trades(bar, zscore)

        self.check_for_long_exit(bar)
        self.check_for_short_exit(bar)
            
        self.update_visualizer_data(bar)

        self.prev_close = bar.close
        self.prev_zscore = zscore

    def check_for_long_trades(self, bar: Bar, zscore: float):
        zscore_entry_long = self.config.vwap_zscore_entry_long
        if self.prev_zscore is not None and self.prev_zscore > zscore_entry_long and zscore < zscore_entry_long:
            self.order_types.submit_long_market_order(self.config.trade_size, price=bar.close)

    def check_for_short_trades(self, bar: Bar, zscore: float):
        zscore_entry_short = self.config.vwap_zscore_entry_short
        if self.prev_zscore is not None and self.prev_zscore <= zscore_entry_short and zscore > zscore_entry_short:
            self.order_types.submit_short_market_order(self.config.trade_size, price=bar.close)

    def check_for_long_exit(self, bar):
        kalman_mean = self.kalman.mean
        net_pos = self.portfolio.net_position(self.instrument_id)
        if (
            net_pos is not None and net_pos > 0
            and self.prev_close is not None
            and self.prev_close < kalman_mean
            and bar.close >= kalman_mean
        ):
            self.order_types.close_position_by_market_order()

    def check_for_short_exit(self, bar):
        prev_zscore = self.prev_zscore
        zscore = self.current_zscore
        net_pos = self.portfolio.net_position(self.instrument_id)
        if (
            net_pos is not None and net_pos < 0
            and prev_zscore is not None and zscore is not None
            and prev_zscore > 0 and zscore <= 0
        ):
            self.order_types.close_position_by_market_order()

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        return self.base_close_position()
    
    def on_stop(self) -> None:
        self.base_on_stop()
        try:
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        except Exception as e:
            self.log.warning(f"Could not calculate unrealized PnL: {e}")
            unrealized_pnl = None
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balances_total()
        vwap_value = self.vwap_zscore.current_vwap_value
        kalman_mean = self.current_kalman_mean if self.kalman.initialized else None


        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="balance", value=usd_balance)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_mean", value=kalman_mean)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap", value=vwap_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap_zscore", value=self.current_zscore)

        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        self.log.info(f"Position closed: {position_closed}")
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)

    def update_visualizer_data(self, bar: Bar) -> None:
        if bar.bar_type == self.bar_type:
            net_position = self.portfolio.net_position(self.instrument_id)
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
            venue = self.instrument_id.venue
            account = self.portfolio.account(venue)
            usd_balance = account.balances_total()
            
            kalman_mean = self.current_kalman_mean if self.kalman.initialized else None
            vwap_value = self.vwap_zscore.current_vwap_value


            self.log.info(f"VISUAL: ts={bar.ts_event}, close={bar.close}, vwap={vwap_value}, kalman={kalman_mean}")
            self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_mean", value=kalman_mean)
            self.collector.add_indicator(timestamp=bar.ts_event, name="vwap", value=vwap_value)
            self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
            self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
            self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
            self.collector.add_indicator(timestamp=bar.ts_event, name="balance", value=usd_balance)
            self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
            self.collector.add_indicator(timestamp=bar.ts_event, name="vwap_zscore", value=self.current_zscore)