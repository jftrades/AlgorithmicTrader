# hier rein kommt ähnlich wie strategie in mean_5m_regimes abgesehen vonnn:
# wir ändern die entry Logik sodass wir kein prev Zscore oder so haben,
# sondern einfach sagen wir möchten dann ab dieser Schwelle einen ChoCh z.B. haben
# auch BOS genannt

# Standard Library Importe
from decimal import Decimal
from typing import Any
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import datetime
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

from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags
from tools.help_funcs.base_strategy import BaseStrategy
from nautilus_trader.common.enums import LogColor
from collections import deque
from tools.indicators.kalman_filter_2D import KalmanFilterRegression
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTF
from tools.indicators.VIX import VIX
from tools.structure.VSCBR import VSCBRReversal

class Mean5mregimesStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type_1h: str 
    bar_type_5m: str
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    vwap_lookback: int
    zscore_window: int
    kalman_process_var: float
    kalman_measurement_var: float
    kalman_window: int
    kalman_slope_thresholds: dict
    kalman_disable_price_condition_slope_long: float
    kalman_disable_price_condition_slope_short: float
    VSCBR_truerange_factor: float
    VSCBR_volume_factor: float
    VSCBR_zscore_threshold: float
    VSCBR_atr_window: int
    VSCBR_volume_window: int

    start_date: str
    end_date: str
    
    kalman_slope_sector_params: dict
    vix_fear_threshold: float = 25.0
    vix_chill_threshold: float = 15.0
    vwap_zscore_condition_long_regime1: float = 1.7
    vwap_zscore_condition_short_regime1: float = -1.5
    vwap_zscore_condition_long_regime2: float = 2.7
    vwap_zscore_condition_short_regime2: float = -2.5
    close_positions_on_stop: bool = True
    invest_percent: float = 0.10

class Mean5mregimesStrategy(BaseStrategy, Strategy):
    def __init__(self, config:Mean5mregimesStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
        self.bar_type_1h = BarType.from_str(config.bar_type_1h)
        self.bar_type_5m = BarType.from_str(config.bar_type_5m)
        self.zscore_neutral_counter = 3
        self.prev_zscore = None
        self.current_kalman_mean = None
        self.stopped = False
        self.realized_pnl = 0
        self.bar_counter = 0
        self.prev_close = None
        self.current_zscore = None
        self.collector = BacktestDataCollector()
        self.vwap_zscore = VWAPZScoreHTF(
            zscore_window=config.zscore_window,
            zscore_condition_long=config.vwap_zscore_condition_long_regime1,
            zscore_condition_short=config.vwap_zscore_condition_short_regime1,
            vwap_lookback=config.vwap_lookback)
        self.kalman = KalmanFilterRegression(
            process_var=config.kalman_process_var,
            measurement_var=config.kalman_measurement_var,
            window=config.kalman_window
        )
        self.vscbr = VSCBRReversal(config)
        self.current_kalman_mean = None
        self.current_kalman_slope = None
        self.current_kalman_slope = None
        self.vix_start = str(config.start_date)[:10]
        self.vix_end = str(config.end_date)[:10]
        self.vix_fear = float(config.vix_fear_threshold)
        self.vix_chill = float(config.vix_chill_threshold)
        self.current_vix_value = None
        self.vix = None
        self.ready_for_long_entry = False
        self.ready_for_short_entry = False 


    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type_1h)
        self.subscribe_bars(self.bar_type_5m)
        self.log.info("Strategy started!")

        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)
        self.vix = VIX(start=self.vix_start, end=self.vix_end, fear_threshold=self.vix_fear, chill_threshold=self.vix_chill)

        self.collector.initialise_logging_indicator("vwap", 0)
        self.collector.initialise_logging_indicator("kalman_mean", 0)
        self.collector.initialise_logging_indicator("vwap_zscore", 1)
        self.collector.initialise_logging_indicator("vix", 2)
        self.collector.initialise_logging_indicator("position", 3)
        self.collector.initialise_logging_indicator("realized_pnl", 4)
        self.collector.initialise_logging_indicator("unrealized_pnl", 5)
        self.collector.initialise_logging_indicator("equity", 6)

    def get_position(self):
        return self.base_get_position()

    def on_bar(self, bar: Bar) -> None:
        zscore = None

        if bar.bar_type == self.bar_type_1h:
            bar_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            vix_value = self.vix.get_value_on_date(bar_date)
            self.current_kalman_mean, self.current_kalman_slope = self.kalman.update(float(bar.close))
            self.current_vix_value = vix_value

        if bar.bar_type == self.bar_type_5m:
            bar_time = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
            if bar_time >= datetime.time(15, 40) and bar_time <= datetime.time(21, 50):
                bar_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
                vix_value = self.vix.get_value_on_date(bar_date)
                vwap_value, zscore = self.vwap_zscore.update(bar)
                self.current_zscore = zscore
                self.vscbr.update(bar)

                if self.current_vix_value is not None:
                    regime = self.get_vix_regime(self.current_vix_value)
                    zscore_condition_long, zscore_condition_short = self.get_zscore_condition_thresholds(regime)
                    self.zscore_long_active = zscore is not None and zscore_condition_long is not None and zscore < zscore_condition_long
                    self.zscore_short_active = (zscore is not None and zscore_condition_short is not None and zscore > zscore_condition_short)

                    if regime == 3:
                        self.log.info("Markt ist zu volatil - keine Trades")
                        self.order_types.close_position_by_market_order()
                    else:
                        if (
                            vwap_value is not None and
                            bar.close is not None and
                            zscore is not None and
                            zscore_condition_long is not None and
                            bar.close < vwap_value and
                            zscore < zscore_condition_long
                        ):
                            self.check_for_long_trades(bar, zscore)
                        
                        if (
                            vwap_value is not None and
                            bar.close is not None and
                            zscore is not None and
                            zscore_condition_short is not None and
                            bar.close > vwap_value and
                            zscore > zscore_condition_short
                        ):
                            self.check_for_short_trades(bar, zscore)

        self.check_for_long_exit(bar)
        self.check_for_short_exit(bar)
        self.update_visualizer_data(bar)
        self.prev_close = bar.close
        self.prev_zscore = zscore
    
    def should_apply_price_condition(self, direction: str) -> bool:
        if direction == "long":
            threshold = abs(self.config.kalman_disable_price_condition_slope_long)
            return abs(self.current_kalman_slope) < threshold
        elif direction == "short":
            threshold = abs(self.config.kalman_disable_price_condition_slope_short)
            return abs(self.current_kalman_slope) < threshold
        return True

    def get_vix_regime(self, vix_value: float) -> int:
        if vix_value is None:
            # Default-Regime 3 (kein Trading)
            return 3
        if vix_value < self.vix_chill:
            return 1  
        elif self.vix_chill <= vix_value < self.vix_fear:
            return 2  
        else:
            return 3
        
    def get_zscore_condition_thresholds(self, regime: int):
        if regime == 1:
            return (
                float(self.config.vwap_zscore_condition_long_regime1),
                float(self.config.vwap_zscore_condition_short_regime1),
            )
        elif regime == 2:
            return (
                float(self.config.vwap_zscore_condition_long_regime2),
                float(self.config.vwap_zscore_condition_short_regime2),
            )
        else:
            return (None, None)
        
    def get_kalman_slope_sector(self):
        slope = self.current_kalman_slope
        thresholds = self.config.kalman_slope_thresholds
        if slope < thresholds["strong_down"]:
            return "strong_down"
        elif slope < thresholds["moderate_down"]:
            return "moderate_down"
        elif slope <= thresholds["sideways"]:
            return "sideways"
        elif slope <= thresholds["moderate_up"]:
            return "moderate_up"
        else:
            return "strong_up"
        
    def get_slope_sector_params(self, regime: int):
        sector = self.get_kalman_slope_sector()
        params = self.config.kalman_slope_sector_params.get(sector, {})
        allow_trades = params.get("allow_trades", True)
        long_risk_factor = params.get("long_risk_factor", 1.0)
        short_risk_factor = params.get("short_risk_factor", 1.0)
        regime_key = f"regime{regime}"
        regime_params = params.get("regime_params", {}).get(regime_key, {})
        zscore_condition_long = regime_params.get("zscore_condition_long", None)
        zscore_condition_short = regime_params.get("zscore_condition_short", None)
        zscore_exit_long = regime_params.get("zscore_exit_long", None)
        zscore_exit_short = regime_params.get("zscore_exit_short", None)
        return (allow_trades, long_risk_factor, short_risk_factor,
                zscore_condition_long, zscore_condition_short,
                zscore_exit_long, zscore_exit_short)
    
    def check_for_long_trades(self, bar: Bar, zscore: float):
        net_pos = self.portfolio.net_position(self.instrument_id)
        if net_pos is None:
            net_pos = 0
        
        # Stacking erlauben ->
        if not self.zscore_long_active and net_pos <= 0:
            return
        
        if self.should_apply_price_condition("long"):
            if bar.close >= self.current_kalman_mean:
                return

        regime = self.get_vix_regime(self.current_vix_value)
        allow_trades, long_risk_factor, _, zscore_condition_long, _, _, _ = self.get_slope_sector_params(regime)
        if not allow_trades:
            return
        
        if zscore_condition_long is None or zscore is None or zscore >= zscore_condition_long:
            return
        
        long_signal, _ = self.vscbr.is_signal(bar, zscore)
        if not long_signal:
            return
                
        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(long_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return
        
        self.order_types.submit_long_market_order(qty, price=bar.close)
            

    def check_for_short_trades(self, bar: Bar, zscore: float):
        net_pos = self.portfolio.net_position(self.instrument_id)
        if net_pos is None:
            net_pos = 0

        # stacking auf den falls setup oft
        if not self.zscore_short_active and net_pos >= 0:
            return

        if self.should_apply_price_condition("short"):
            if bar.close <= self.current_kalman_mean:
                return

        regime = self.get_vix_regime(self.current_vix_value)
        allow_trades, _, short_risk_factor, _, zscore_condition_short, _, _ = self.get_slope_sector_params(regime)
        if not allow_trades:
            return

        if net_pos >= 0 and (zscore_condition_short is None or zscore is None or zscore <= zscore_condition_short):
            return

        _, short_signal = self.vscbr.is_signal(bar, zscore)
        if not short_signal:
            return

        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(short_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return

        self.order_types.submit_short_market_order(qty, price=bar.close)

    def check_for_long_exit(self, bar):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        params = self.get_slope_sector_params(regime)
        allow_trades = params[0]
        zscore_exit_long = params[5]
        if not allow_trades:
            self.order_types.close_position_by_market_order()
            return

        prev_zscore = self.prev_zscore
        zscore = self.current_zscore
        net_pos = self.portfolio.net_position(self.instrument_id)
        if (
            net_pos is not None and net_pos > 0
            and prev_zscore is not None and zscore is not None
            and zscore_exit_long is not None
            and prev_zscore < zscore_exit_long and zscore >= zscore_exit_long
        ):
            self.order_types.close_position_by_market_order()


    def check_for_short_exit(self, bar):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        params = self.get_slope_sector_params(regime)
        allow_trades = params[0]
        zscore_exit_short = params[6]
        if not allow_trades:
            self.order_types.close_position_by_market_order()
            return

        prev_zscore = self.prev_zscore
        zscore = self.current_zscore
        net_pos = self.portfolio.net_position(self.instrument_id)
        if (
            net_pos is not None and net_pos < 0
            and prev_zscore is not None and zscore is not None
            and zscore_exit_short is not None
            and prev_zscore > zscore_exit_short and zscore <= zscore_exit_short
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
        usd_balance = account.balance_total()
        equity = usd_balance.as_double() + float(unrealized_pnl) if unrealized_pnl is not None else usd_balance.as_double()
        vwap_value = self.vwap_zscore.current_vwap_value
        kalman_mean = self.current_kalman_mean if self.kalman.initialized else None

        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vix", value=self.current_vix_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="equity", value=equity)
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
        if bar.bar_type == self.bar_type_5m:
            net_position = self.portfolio.net_position(self.instrument_id)
            unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
            venue = self.instrument_id.venue
            account = self.portfolio.account(venue)
            usd_balance = account.balance_total()
            equity = usd_balance.as_double() + float(unrealized_pnl) if unrealized_pnl is not None else usd_balance.as_double()
            
            kalman_mean = self.current_kalman_mean if self.kalman.initialized else None
            vwap_value = self.vwap_zscore.current_vwap_value

            self.collector.add_indicator(timestamp=bar.ts_event, name="vix", value=self.current_vix_value)
            self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_mean", value=kalman_mean)
            self.collector.add_indicator(timestamp=bar.ts_event, name="vwap", value=vwap_value)
            self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
            self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
            self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
            self.collector.add_indicator(timestamp=bar.ts_event, name="equity", value=equity)
            self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
            self.collector.add_indicator(timestamp=bar.ts_event, name="vwap_zscore", value=self.current_zscore)
        
        elif bar.bar_type == self.bar_type_1h:

            pass
