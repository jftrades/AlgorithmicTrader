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
from tools.indicators.kalman_filter_2D_own_ZScore import KalmanFilterRegressionWithZScore
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTFAnchored
from tools.structure.elastic_reversion_zscore_entry import ElasticReversionZScoreEntry
from tools.help_funcs.slope_distrubition_monitor import SlopeDistributionMonitor
from tools.indicators.VIX import VIX

class Mean5mregimesStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type_1h: str 
    bar_type_5m: str
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    kalman_process_var: float
    kalman_measurement_var: float
    kalman_window: int
    kalman_slope_thresholds: dict
    kalman_disable_price_condition_slope_long: float
    kalman_disable_price_condition_slope_short: float

    start_date: str
    end_date: str
    
    kalman_slope_sector_params: dict
    kalman_exit_process_var: float
    kalman_exit_measurement_var: float
    kalman_exit_window: int
    kalman_exit_zscore_window: int

    elastic_reversion_entry: dict
    
    # VWAP/ZScore Parameter
    vwap_anchor_on_kalman_cross: bool = True
    zscore_calculation: dict = None
    gap_threshold_pct: float = 0.1
    vwap_min_bars_for_zscore: int = 30
    vwap_reset_grace_period: int = 25
    vwap_require_trade_for_reset: bool = True
    
    vix_fear_threshold: float = 25.0
    vix_chill_threshold: float = 15.0
    gap_threshold_pct: float = 0.1
    test_which_slope_params: bool = False
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
        self.vwap_zscore = VWAPZScoreHTFAnchored(
            anchor_on_kalman_cross=getattr(config, 'vwap_anchor_on_kalman_cross', True),
            zscore_calculation=getattr(config, 'zscore_calculation', {"simple": {"enabled": True}}),
            gap_threshold_pct=config.gap_threshold_pct,
            min_bars_for_zscore=getattr(config, 'vwap_min_bars_for_zscore', 30),
            reset_grace_period=getattr(config, 'vwap_reset_grace_period', 25),
            require_trade_for_reset=getattr(config, 'vwap_require_trade_for_reset', True)
        )
        
        self.current_vix_value = None
        self.current_kalman_slope = None
        
        # Bestehender Kalman für Regime/Slope
        self.kalman = KalmanFilterRegression(
            process_var=config.kalman_process_var,
            measurement_var=config.kalman_measurement_var,
            window=config.kalman_window
        )
        self.current_kalman_mean = None
        self.current_kalman_slope = None

        # Neuer Kalman für Exit-Z-Score
        self.kalman_exit = KalmanFilterRegressionWithZScore(
            process_var=config.kalman_exit_process_var,
            measurement_var=config.kalman_exit_measurement_var,
            window=config.kalman_exit_window,
            zscore_window=config.kalman_exit_zscore_window
        )
        self.current_kalman_exit_mean = None
        self.current_kalman_exit_slope = None
        self.current_kalman_exit_zscore = None

        entry_config = config.elastic_reversion_entry
        self.elastic_entry = ElasticReversionZScoreEntry(
            vwap_zscore_indicator=self.vwap_zscore,
            lookback_window=entry_config.get('lookback_window', 15),
            z_min_threshold=-2.0,
            z_max_threshold=2.0,
            recovery_delta=0.6,
            reset_neutral_zone_long=1.0,
            reset_neutral_zone_short=-1.0,
            allow_multiple_recoveries=entry_config.get('allow_multiple_recoveries', True),
            recovery_cooldown_bars=entry_config.get('recovery_cooldown_bars', 5)
        )

        # NEU: Stacking-Parameter aus YAML
        stacking_config = entry_config.get('allow_stacking', {})
        self.allow_stacking = stacking_config.get('enabled', False) if isinstance(stacking_config, dict) else False
        self.max_stacked_positions = stacking_config.get('max_stacked_positions', 3)
        self.additional_zscore_min_gain = stacking_config.get('additional_zscore_min_gain', 0.5)
        self.recovery_delta_reentry = stacking_config.get('recovery_delta_reentry', 0.3)
        self.stacking_bar_cooldown = stacking_config.get('stacking_bar_cooldown', 10)
        
        # NEU: Einfaches Tracking für Stacking seit letztem Kalman Cross
        self.long_positions_since_cross = 0
        self.short_positions_since_cross = 0
        self.last_kalman_cross_direction = None  # "up" oder "down"

        self.slope_monitor = None
        if config.test_which_slope_params:
            # YAML-Thresholds an Monitor übergeben
            self.slope_monitor = SlopeDistributionMonitor(
                slope_thresholds=config.kalman_slope_thresholds
            )
            print(f"Slope Distribution Monitor: ENABLED with YAML thresholds")
            print(f"Thresholds: {config.kalman_slope_thresholds}")

        self.vix_start = config.start_date
        self.vix_end = config.end_date  
        self.vix_fear = config.vix_fear_threshold
        self.vix_chill = config.vix_chill_threshold
        self.vix = VIX(start=self.vix_start, end=self.vix_end, fear_threshold=self.vix_fear, chill_threshold=self.vix_chill)

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

        self.collector.initialise_logging_indicator("vwap", 0)
        self.collector.initialise_logging_indicator("kalman_exit_mean", 0)
        self.collector.initialise_logging_indicator("kalman_mean", 0)
        self.collector.initialise_logging_indicator("vwap_zscore", 1)
        self.collector.initialise_logging_indicator("kalman_exit_zscore", 2)
        self.collector.initialise_logging_indicator("vix", 3)
        self.collector.initialise_logging_indicator("position", 4)
        self.collector.initialise_logging_indicator("realized_pnl", 5)
        self.collector.initialise_logging_indicator("unrealized_pnl", 6)
        self.collector.initialise_logging_indicator("equity", 7)


    def get_position(self):
        return self.base_get_position()

    def on_bar(self, bar: Bar) -> None:
        zscore = None

        if bar.bar_type == self.bar_type_1h:
            bar_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            vix_value = self.vix.get_value_on_date(bar_date)
            self.current_kalman_mean, self.current_kalman_slope = self.kalman.update(float(bar.close))
            self.current_vix_value = vix_value

            if self.slope_monitor and self.current_kalman_slope is not None:
                self.slope_monitor.add_slope(self.current_kalman_slope)
                
                if self.slope_monitor.total_count % 100 == 0:
                    self.slope_monitor.print_progress_update(self.current_kalman_slope)

        if bar.bar_type == self.bar_type_5m:
            bar_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            vix_value = self.vix.get_value_on_date(bar_date)
            
            # Kalman für Exits mit Z-Score ZUERST berechnen
            self.current_kalman_exit_mean, self.current_kalman_exit_slope, self.current_kalman_exit_zscore = self.kalman_exit.update(float(bar.close))
            
            # VWAP mit Kalman-Exit-Mean für Cross-Detection
            vwap_value, zscore = self.vwap_zscore.update(bar, kalman_exit_mean=self.current_kalman_exit_mean)
            self.current_zscore = zscore

            # Prüfe auf Kalman Cross für Stacking-Reset (verwendet VWAP Cross-Detection)
            self._check_vwap_cross_for_stacking(bar)

            if zscore is not None:
                self.elastic_entry.update_state(zscore)


            bar_time = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
            if bar_time >= datetime.time(15, 40) and bar_time <= datetime.time(21, 50):
                if self.current_vix_value is not None:
                    regime = self.get_vix_regime(self.current_vix_value)

                    if regime == 3:
                        self.log.info("Markt ist zu volatil - keine Trades")
                        self.order_types.close_position_by_market_order()
                    else:
                        if self.current_kalman_exit_mean is not None and self.current_kalman_mean is not None and zscore is not None:
                            if bar.close < self.current_kalman_exit_mean:
                                self.check_for_long_trades(bar, zscore)
                            elif bar.close > self.current_kalman_exit_mean:
                                self.check_for_short_trades(bar, zscore)

        self.check_for_long_exit(bar)
        self.check_for_short_exit(bar)
        self.update_visualizer_data(bar)
        self.prev_close = bar.close
        self.prev_zscore = zscore

    def count_open_position(self) -> int:
        """Zählt die Anzahl der aktuell offenen Positionen (Stacks)"""
        pos = self.portfolio.net_position(self.instrument_id)
        return abs(int(pos)) if pos is not None else 0
    
    def _check_vwap_cross_for_stacking(self, bar):
        """Nutzt VWAP Cross-Detection für Stacking Reset (synchronisiert)"""
        # Hole VWAP Segment Info
        vwap_segment_info = self.vwap_zscore.get_segment_info()
        current_segment_start = vwap_segment_info.get('start_bar', 0)
        
        # Wenn neuer Segment begonnen hat, reset Stacking Counters
        if not hasattr(self, '_last_vwap_segment_start'):
            self._last_vwap_segment_start = current_segment_start
            return
        
        if current_segment_start != self._last_vwap_segment_start:
            # VWAP hat neues Segment gestartet - synchronisiere Stacking Reset
            self.long_positions_since_cross = 0
            self.short_positions_since_cross = 0
            
            # Bestimme Cross-Richtung basierend auf aktueller Position relativ zu Kalman
            if self.current_kalman_exit_mean is not None:
                current_above = bar.close > self.current_kalman_exit_mean
                self.last_kalman_cross_direction = "up" if current_above else "down"
                cross_direction = "UP" if current_above else "DOWN"
                
                anchor_reason = vwap_segment_info.get('anchor_reason', 'unknown')
                self.log.info(f"VWAP+Stacking Reset: {cross_direction} Cross ({anchor_reason})", color=LogColor.BLUE)
            
            self._last_vwap_segment_start = current_segment_start
    
    def can_stack_long(self, current_zscore: float) -> bool:
        """Prüft ob Long-Position gestackt werden kann"""
        if not self.allow_stacking:
            return False
        
        # Maximal erlaubte Stacks erreicht?
        if self.long_positions_since_cross >= self.max_stacked_positions:
            return False
        
        # Muss schon mindestens einen Short seit letztem Cross gegeben haben
        if self.short_positions_since_cross == 0:
            return False
        
        return True
    
    def can_stack_short(self, current_zscore: float) -> bool:
        """Prüft ob Short-Position gestackt werden kann"""
        if not self.allow_stacking:
            return False
        
        # Maximal erlaubte Stacks erreicht?
        if self.short_positions_since_cross >= self.max_stacked_positions:
            return False
        
        # Muss schon mindestens einen Long seit letztem Cross gegeben haben
        if self.long_positions_since_cross == 0:
            return False
        
        return True
    
    def should_apply_price_condition(self, direction: str) -> bool:

        if self.current_kalman_slope is None:
            return False

        slope_abs = abs(self.current_kalman_slope)

        if direction == "long":
            threshold = abs(self.config.kalman_disable_price_condition_slope_long)  # 0.025
            return slope_abs <= threshold
            
        elif direction == "short":
            threshold = abs(self.config.kalman_disable_price_condition_slope_short)  # 0.025
            return slope_abs <= threshold
            
        return False

    def get_vix_regime(self, vix_value: float) -> int:
        if vix_value < self.vix_chill:
            return 1  
        elif self.vix_chill <= vix_value < self.vix_fear:
            return 2  
        else:
            return 3
        
        
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
        kalman_zscore_exit_long = regime_params.get("kalman_zscore_exit_long", None)
        kalman_zscore_exit_short = regime_params.get("kalman_zscore_exit_short", None)
        
        return (allow_trades, long_risk_factor, short_risk_factor,
                kalman_zscore_exit_long, kalman_zscore_exit_short)
    
    def check_for_long_trades(self, bar: Bar, zscore: float):
        if self.should_apply_price_condition("long"):
            if bar.close >= self.current_kalman_mean:
                return
            
        if self.current_kalman_exit_mean is not None and bar.close >= self.current_kalman_exit_mean:
            return

        regime = self.get_vix_regime(self.current_vix_value)
        params = self.get_slope_sector_params(regime)
        allow_trades = params[0]
        long_risk_factor = params[1]
        
        if not allow_trades:
            return
        
        # GEÄNDERT: Einfache Stacking-Logik
        current_net_pos = self.count_open_position()
        
        # Wenn keine Position offen, normale Entry-Logik
        if current_net_pos == 0:
            can_enter = True
        # Wenn schon Positionen offen, prüfe Stacking-Möglichkeiten
        else:
            can_enter = self.can_stack_long(zscore)
        
        if not can_enter:
            return
        
        sector = self.get_kalman_slope_sector()
        self.elastic_entry.apply_sector_regime_params(
            config_params=self.config.kalman_slope_sector_params,
            sector=sector,
            regime=regime
        )

        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(long_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return

        # NEU: Elastic Entry Signal abrufen (ersetzt alte Z-Score-Logik)
        long_signal, _, debug_info = self.elastic_entry.check_entry_signals(zscore)
        
        if long_signal:
            entry_reason = debug_info.get('long_entry_reason', 'Recovery signal')
            current_params = debug_info.get('current_parameters', {})
            
            # VWAP benachrichtigen dass Trade erfolgt ist
            self.vwap_zscore.notify_trade_occurred()
            
            self.order_types.submit_long_market_order(qty, price=bar.close)
            
            # Erhöhe Long-Counter für Stacking
            self.long_positions_since_cross += 1
            
            stack_info = f"Stack {self.long_positions_since_cross}/{self.max_stacked_positions}" if self.long_positions_since_cross > 1 else "Initial"
            
            self.log.info(
                f"Long Entry [{sector}/regime{regime}] {stack_info}: {entry_reason} | "
                f"Params: z_min={current_params.get('z_min_threshold', 'N/A'):.2f}, "
                f"recovery_delta={current_params.get('recovery_delta', 'N/A'):.2f} | "
                f"ZScore: {zscore:.2f}", 
                color=LogColor.GREEN
            )

    def check_for_short_trades(self, bar: Bar, zscore: float):
        if self.should_apply_price_condition("short"):
            if bar.close <= self.current_kalman_mean:
                return
            
        if self.current_kalman_exit_mean is not None and bar.close <= self.current_kalman_exit_mean:
            return
    
        regime = self.get_vix_regime(self.current_vix_value)
        params = self.get_slope_sector_params(regime)
        allow_trades = params[0]
        short_risk_factor = params[2]
        
        if not allow_trades:
            return
        
        # GEÄNDERT: Einfache Stacking-Logik
        current_net_pos = self.count_open_position()
        
        # Wenn keine Position offen, normale Entry-Logik
        if current_net_pos == 0:
            can_enter = True
        # Wenn schon Positionen offen, prüfe Stacking-Möglichkeiten
        else:
            can_enter = self.can_stack_short(zscore)
        
        if not can_enter:
            return

        sector = self.get_kalman_slope_sector()
        self.elastic_entry.apply_sector_regime_params(
            config_params=self.config.kalman_slope_sector_params,
            sector=sector,
            regime=regime
        )

        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(short_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return

        # NEUuu: Elastic Entry Signal abrufen (ersetzt alte Z-Score-Logik)
        _, short_signal, debug_info = self.elastic_entry.check_entry_signals(zscore)
        
        if short_signal:
            # Erweiterte Logging-Info mit Sector/Regime und aktuellen Parametern
            entry_reason = debug_info.get('short_entry_reason', 'Recovery signal')
            current_params = debug_info.get('current_parameters', {})
            
            # VWAP benachrichtigen dass Trade erfolgt ist
            self.vwap_zscore.notify_trade_occurred()
            
            self.order_types.submit_short_market_order(qty, price=bar.close)
            
            # Erhöhe Short-Counter für Stacking
            self.short_positions_since_cross += 1
            
            stack_info = f"Stack {self.short_positions_since_cross}/{self.max_stacked_positions}" if self.short_positions_since_cross > 1 else "Initial"
            
            self.log.info(
                f"Short Entry [{sector}/regime{regime}] {stack_info}: {entry_reason} | "
                f"Params: z_max={current_params.get('z_max_threshold', 'N/A'):.2f}, "
                f"recovery_delta={current_params.get('recovery_delta', 'N/A'):.2f} | "
                f"ZScore: {zscore:.2f}", 
                color=LogColor.MAGENTA
            )

    def check_for_long_exit(self, bar):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        params = self.get_slope_sector_params(regime)
        allow_trades = params[0]
        kalman_zscore_exit_long = params[3] 
        if not allow_trades:
            self.order_types.close_position_by_market_order()
            return

        net_pos = self.portfolio.net_position(self.instrument_id)
        if (
                net_pos is not None and net_pos > 0
                and self.current_kalman_exit_zscore is not None
                and kalman_zscore_exit_long is not None
                and self.current_kalman_exit_zscore >= kalman_zscore_exit_long
            ):
                self.order_types.close_position_by_market_order()

    def check_for_short_exit(self, bar):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        params = self.get_slope_sector_params(regime)
        allow_trades = params[0]
        kalman_zscore_exit_short = params[4]
        if not allow_trades:
            self.order_types.close_position_by_market_order()
            return
        
        net_pos = self.portfolio.net_position(self.instrument_id)
        if (
            net_pos is not None and net_pos < 0
            and self.current_kalman_exit_zscore is not None
            and kalman_zscore_exit_short is not None
            and self.current_kalman_exit_zscore <= kalman_zscore_exit_short
        ):
            self.order_types.close_position_by_market_order()

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        return self.base_close_position()
    
    def on_stop(self) -> None:
        if self.slope_monitor:
            self.slope_monitor.print_distribution()

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
        kalman_exit_mean = self.current_kalman_exit_mean if self.kalman_exit.initialized else None


        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vix", value=self.current_vix_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="equity", value=equity)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_mean", value=kalman_mean)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap", value=vwap_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap_zscore", value=self.current_zscore)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_exit_mean", value=kalman_exit_mean)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_exit_zscore", value=self.current_kalman_exit_zscore)


        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

    
    def on_order_filled(self, order_filled) -> None:
        # Benachrichtige VWAP-Indikator über Trade
        self.vwap_zscore.notify_trade_occurred()
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
            kalman_exit_mean = self.current_kalman_exit_mean if self.kalman_exit.initialized else None


            self.collector.add_indicator(timestamp=bar.ts_event, name="vix", value=self.current_vix_value)
            self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_mean", value=kalman_mean)
            self.collector.add_indicator(timestamp=bar.ts_event, name="vwap", value=vwap_value)
            self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
            self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
            self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
            self.collector.add_indicator(timestamp=bar.ts_event, name="equity", value=equity)
            self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)
            self.collector.add_indicator(timestamp=bar.ts_event, name="vwap_zscore", value=self.current_zscore)
            self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_exit_mean", value=kalman_exit_mean)
            self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_exit_zscore", value=self.current_kalman_exit_zscore)
        
        elif bar.bar_type == self.bar_type_1h:

            pass


