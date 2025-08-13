# Standard Library Importe
from decimal import Decimal
from typing import Any
import datetime
# Nautilus Kern offizielle Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.events import PositionEvent
from nautilus_trader.common.enums import LogColor

from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.base_strategy import BaseStrategy
from tools.indicators.kalman_filter_2D_own_ZScore import KalmanFilterRegressionWithZScore
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTFAnchored
from tools.structure.elastic_reversion_zscore_entry import ElasticReversionZScoreEntry
from tools.indicators.VIX import VIX
from tools.help_funcs.adaptive_parameter_manager_new import AdaptiveParameterManager

class Mean5mregimesStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type_5m: str
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    
    start_date: str
    end_date: str
    
    # New adaptive system
    base_parameters: dict
    adaptive_factors: dict
    
    # VWAP/ZScore Parameter
    vwap_anchor_on_kalman_cross: bool = True
    zscore_calculation: dict = None
    gap_threshold_pct: float = 0.1
    
    vix_fear_threshold: float = 25.0
    close_positions_on_stop: bool = True
    invest_percent: float = 0.10
    only_trade_rth: bool = True

class Mean5mregimesStrategy(BaseStrategy, Strategy):
    def __init__(self, config:Mean5mregimesStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None
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
        
        # Dashboard indicators
        self.current_kalman_mean = None
        self.current_combined_factor = None
        self.entry_combined_factor = None
        
        self.adaptive_manager = AdaptiveParameterManager(
            base_params=config.base_parameters,
            adaptive_factors=config.adaptive_factors
        )
        
        adaptive_params, _, _, _ = self.adaptive_manager.get_adaptive_parameters()
        vwap_params = adaptive_params['vwap']
        self.vwap_zscore = VWAPZScoreHTFAnchored(
            anchor_on_kalman_cross=vwap_params['vwap_anchor_on_kalman_cross'],
            zscore_calculation=getattr(config, 'zscore_calculation', {"simple": {"enabled": True}}),
            gap_threshold_pct=config.gap_threshold_pct,
            min_bars_for_zscore=vwap_params['vwap_min_bars_for_zscore'],
            reset_grace_period=vwap_params['vwap_reset_grace_period'],
            require_trade_for_reset=vwap_params['vwap_require_trade_for_reset']
        )
        
        self.current_vix_value = None
        
        self.kalman = KalmanFilterRegressionWithZScore(
            process_var=adaptive_params['kalman_process_var'],
            measurement_var=adaptive_params['kalman_measurement_var'],
            window=10,
            zscore_window=adaptive_params['kalman_zscore_window']
        )
        self.current_kalman_mean = None
        self.current_kalman_slope = None
        self.current_kalman_zscore = None

        # Initialize with adaptive parameters
        adaptive_elastic_params = adaptive_params['elastic_entry']
        self.elastic_entry = ElasticReversionZScoreEntry(
            vwap_zscore_indicator=self.vwap_zscore,
            z_min_threshold=adaptive_elastic_params['zscore_long_threshold'],
            z_max_threshold=adaptive_elastic_params['zscore_short_threshold'],
            recovery_delta=adaptive_elastic_params['recovery_delta'],
            reset_neutral_zone_long=1.0,
            reset_neutral_zone_short=-1.0,
            allow_multiple_recoveries=adaptive_elastic_params['allow_multiple_recoveries'],
            recovery_cooldown_bars=adaptive_elastic_params['recovery_cooldown_bars']
        )

        self.allow_stacking = adaptive_elastic_params.get('alllow_stacking', False)
        self.max_stacked_positions = adaptive_elastic_params.get('max_stacked_positions', 3)
        self.additional_zscore_min_gain = adaptive_elastic_params.get('additional_zscore_min_gain', 0.5)
        self.recovery_delta_reentry = adaptive_elastic_params.get('recovery_delta_reentry', 0.3)
        self.stacking_bar_cooldown = adaptive_elastic_params.get('stacking_bar_cooldown', 10)
        
        self.long_positions_since_cross = 0
        self.short_positions_since_cross = 0
        self.last_kalman_cross_direction = None
        self.long_entry_zscores = []
        self.short_entry_zscores = []
        self.bars_since_last_long_entry = 0
        self.bars_since_last_short_entry = 0

        # VIX initialization
        self.vix_start = config.start_date
        self.vix_end = config.end_date  
        self.vix_fear = config.vix_fear_threshold
        self.vix = VIX(start=self.vix_start, end=self.vix_end, fear_threshold=self.vix_fear)
        
        # RTH configuration
        self.only_trade_rth = config.only_trade_rth
        self.rth_start_hour = 15
        self.rth_start_minute = 40
        self.rth_end_hour = 21
        self.rth_end_minute = 50

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type_5m)
        self.log.info("Strategy started!")

        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)

        self.collector.initialise_logging_indicator("kalman_mean", 0)
        self.collector.initialise_logging_indicator("vwap", 0)
        self.collector.initialise_logging_indicator("combined_factor", 1)
        self.collector.initialise_logging_indicator("kalman_mean", 0)
        self.collector.initialise_logging_indicator("vwap_zscore", 2)
        self.collector.initialise_logging_indicator("kalman_zscore", 3)
        self.collector.initialise_logging_indicator("vix", 4)
        self.collector.initialise_logging_indicator("position", 5)
        self.collector.initialise_logging_indicator("realized_pnl", 6)
        self.collector.initialise_logging_indicator("unrealized_pnl", 7)
        self.collector.initialise_logging_indicator("equity", 8)


    def get_position(self):
        return self.base_get_position()

    def is_rth_time(self, bar: Bar) -> bool:
        if not self.only_trade_rth:
            return True
            
        bar_time = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(self.rth_start_hour, self.rth_start_minute)
        rth_end = datetime.time(self.rth_end_hour, self.rth_end_minute)
        
        return rth_start <= bar_time <= rth_end

    def on_bar(self, bar: Bar) -> None:
        zscore = None
        bar_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")

        vix_value = self.vix.get_value_on_date(bar_date)
        if vix_value is not None:
            self.current_vix_value = float(vix_value)
        else:
            self.current_vix_value = None

        self.current_kalman_mean, self.current_kalman_slope, self.current_kalman_zscore = self.kalman.update(float(bar.close))
        
        self.adaptive_manager.update_atr(float(bar.high), float(bar.low), float(self.prev_close) if self.prev_close else None)
        self.adaptive_manager.update_slope(self.current_kalman_mean, self.current_kalman_slope)
        adaptive_params, slope_factor, atr_factor, combined_factor = self.adaptive_manager.get_adaptive_parameters()
        self.current_combined_factor = combined_factor
        
        linear_config = self.adaptive_manager.adaptive_factors.get('linear_adjustments', {})
        trend_sensitivity = linear_config.get('trend_sensitivity', 0.3)
        vol_sensitivity = linear_config.get('vol_sensitivity', 0.4)
        max_trend_strength = linear_config.get('max_trend_strength', 0.8)
        
        elastic_base = adaptive_params['elastic_entry']
        
        adjusted_long_threshold = self.adaptive_manager.get_linear_adjustment(
            base_value=elastic_base['zscore_long_threshold'],
            trend_sensitivity=trend_sensitivity,
            vol_sensitivity=vol_sensitivity
        )
        
        adjusted_short_threshold = self.adaptive_manager.get_linear_adjustment(
            base_value=elastic_base['zscore_short_threshold'],
            trend_sensitivity=-trend_sensitivity,
            vol_sensitivity=vol_sensitivity
        )
        
        adjusted_recovery_delta = self.adaptive_manager.get_linear_adjustment(
            base_value=elastic_base['recovery_delta'],
            trend_sensitivity=0,
            vol_sensitivity=vol_sensitivity * 0.5
        )
        
        self.elastic_entry.update_parameters(
            z_min_threshold=adjusted_long_threshold,
            z_max_threshold=adjusted_short_threshold,
            recovery_delta=adjusted_recovery_delta
        )
        
        self.additional_zscore_min_gain = elastic_base['additional_zscore_min_gain']
        self.recovery_delta_reentry = elastic_base['recovery_delta_reentry']
            
        # Update VWAP with asymmetric offset
        asymmetric_offset = self.adaptive_manager.get_asymmetric_offset(self.current_kalman_mean)
        vwap_segment_info_before = self.vwap_zscore.get_segment_info()
        vwap_value, zscore = self.vwap_zscore.update(bar, kalman_exit_mean=self.current_kalman_mean, asymmetric_offset=asymmetric_offset)
        self.current_zscore = zscore
        vwap_segment_info_after = self.vwap_zscore.get_segment_info()

        if zscore is not None:
            self.elastic_entry.update_state(zscore)

        self._check_vwap_cross_for_stacking(bar, vwap_segment_info_before, vwap_segment_info_after)
        self.bar_counter += 1

        # Update entry tracking counters
        self.bars_since_last_long_entry += 1
        self.bars_since_last_short_entry += 1

        # Trading logic - nur während RTH handeln
        if self.is_rth_time(bar):
            if self.current_vix_value is not None:
                regime = self.get_vix_regime(self.current_vix_value)

                if regime == 2:  # Fear regime - close positions
                    self.vwap_zscore.notify_exit_trade_occurred()
                    self.order_types.close_position_by_market_order()
                else:
                    if self.current_kalman_mean is not None and zscore is not None:
                        trend_strength = abs(self.adaptive_manager.get_trend_factor())
                        if trend_strength < max_trend_strength:
                            self.current_long_risk_factor = adaptive_params['long_risk_factor']
                            self.current_short_risk_factor = adaptive_params['short_risk_factor']
                            
                            if bar.close < self.current_kalman_mean:
                                self.check_for_long_trades(bar, zscore, adaptive_params)
                            elif bar.close > self.current_kalman_mean:
                                self.check_for_short_trades(bar, zscore, adaptive_params)

        self.check_for_long_exit(bar, adaptive_params)
        self.check_for_short_exit(bar, adaptive_params)
        self.update_visualizer_data(bar)
        self.prev_close = bar.close
        self.prev_zscore = zscore

    def count_open_position(self) -> int:
        pos = self.portfolio.net_position(self.instrument_id)
        return abs(int(pos)) if pos is not None else 0
    
    def _check_vwap_cross_for_stacking(self, bar, vwap_segment_info_before, vwap_segment_info_after):
        start_before = vwap_segment_info_before.get('segment_start_bar', 0)
        start_after = vwap_segment_info_after.get('segment_start_bar', 0)
        
        if start_before != start_after:
            # Reset Position Tracking
            self.long_positions_since_cross = 0
            self.short_positions_since_cross = 0
            
            # Reset Entry ZScore Tracking
            self.long_entry_zscores = []
            self.short_entry_zscores = []
            self.bars_since_last_long_entry = 0
            self.bars_since_last_short_entry = 0
            
            self.elastic_entry.reset_on_cross()
            
            if self.current_kalman_mean is not None:
                current_above = bar.close > self.current_kalman_mean
                self.last_kalman_cross_direction = "up" if current_above else "down"
                
                anchor_reason = vwap_segment_info_after.get('anchor_reason', 'unknown')
                self.log.info(f"VWAP anchor reset: {anchor_reason} | Stacking counters reset", color=LogColor.BLUE)
    
    def can_stack_long(self, current_zscore: float) -> bool:
        # Erste Position ist immer erlaubt, auch wenn Stacking deaktiviert ist
        if self.long_positions_since_cross == 0:
            return True
            
        # Wenn Stacking deaktiviert ist, keine weiteren Positionen erlauben
        if not self.allow_stacking:
            return False
        
        if self.long_positions_since_cross >= self.max_stacked_positions:
            return False
                    
        if self.bars_since_last_long_entry < self.stacking_bar_cooldown:
            return False
            
        if self.long_entry_zscores and current_zscore is not None:
            last_entry_zscore = self.long_entry_zscores[-1]
            zscore_deterioration = last_entry_zscore - current_zscore  # Für Long: negativer = schlechter
            
            if zscore_deterioration < self.additional_zscore_min_gain:
                return False
        
        return True  
    
    def can_stack_short(self, current_zscore: float) -> bool:
        # Erste Position ist immer erlaubt, auch wenn Stacking deaktiviert ist
        if self.short_positions_since_cross == 0:
            return True
            
        # Wenn Stacking deaktiviert ist, keine weiteren Positionen erlauben
        if not self.allow_stacking:
            return False
        
        if self.short_positions_since_cross >= self.max_stacked_positions:
            return False
            
        if self.bars_since_last_short_entry < self.stacking_bar_cooldown:
            return False
            
        if self.short_entry_zscores and current_zscore is not None:
            last_entry_zscore = self.short_entry_zscores[-1]
            zscore_deterioration = current_zscore - last_entry_zscore  # Für Short: positiver = schlechter
            
            if zscore_deterioration < self.additional_zscore_min_gain:
                return False
        
        return True

    def get_vix_regime(self, vix_value: float) -> int:
        if vix_value is None:
            return 1  # Default to normal regime
        
        vix_val = float(vix_value) if not isinstance(vix_value, (int, float)) else vix_value
        
        if vix_val >= self.vix_fear:
            return 2  # Fear regime
        else:
            return 1  # Normal regime
    
    def check_for_long_trades(self, bar: Bar, zscore: float, adaptive_params: dict):
        if self.current_kalman_mean is not None and bar.close >= self.current_kalman_mean:
            return

        regime = self.get_vix_regime(self.current_vix_value)
        if regime == 2:  # Fear regime - no trades
            return
        
        can_enter = self.can_stack_long(zscore)
        if not can_enter:
            return

        # Use adaptive risk factor
        long_risk_factor = adaptive_params['long_risk_factor']
        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(long_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return

        long_signal, _, debug_info = self.elastic_entry.check_entry_signals(zscore)
        
        if long_signal:
            entry_reason = debug_info.get('long_entry_reason', 'Recovery signal')
            stack_info = f"Stack {self.long_positions_since_cross + 1}/{self.max_stacked_positions}" if self.long_positions_since_cross > 0 else "Initial"
            
            # Log trade state
            self.adaptive_manager.log_trade_state(
                "LONG", float(bar.close), zscore, entry_reason, stack_info, regime, 
                adaptive_params, self.long_positions_since_cross, self.short_positions_since_cross, 
                self.allow_stacking
            )
            
            self.order_types.submit_long_market_order(qty, price=bar.close)
            self.long_positions_since_cross += 1
            self.entry_combined_factor = self.current_combined_factor
            
            # Track entry ZScore for stacking
            self.long_entry_zscores.append(zscore)
            self.bars_since_last_long_entry = 0

    def check_for_short_trades(self, bar: Bar, zscore: float, adaptive_params: dict):
        if self.current_kalman_mean is not None and bar.close <= self.current_kalman_mean:
            return
    
        regime = self.get_vix_regime(self.current_vix_value)
        if regime == 2:  # Fear regime - no trades
            return
        
        can_enter = self.can_stack_short(zscore)
        if not can_enter:
            return

        # Use adaptive risk factor
        short_risk_factor = adaptive_params['short_risk_factor']
        invest_percent = Decimal(str(self.config.invest_percent)) * Decimal(str(short_risk_factor))
        entry_price = Decimal(str(bar.close))
        qty, valid_position = self.risk_manager.calculate_investment_size(invest_percent, entry_price)
        if not valid_position or qty <= 0:
            return

        _, short_signal, debug_info = self.elastic_entry.check_entry_signals(zscore)
        
        if short_signal:
            entry_reason = debug_info.get('short_entry_reason', 'Recovery signal')
            stack_info = f"Stack {self.short_positions_since_cross + 1}/{self.max_stacked_positions}" if self.short_positions_since_cross > 0 else "Initial"
            
            # Log trade state
            self.adaptive_manager.log_trade_state(
                "SHORT", float(bar.close), zscore, entry_reason, stack_info, regime, 
                adaptive_params, self.long_positions_since_cross, self.short_positions_since_cross, 
                self.allow_stacking
            )
            
            self.order_types.submit_short_market_order(qty, price=bar.close)
            self.short_positions_since_cross += 1
            self.entry_combined_factor = self.current_combined_factor
            
            # Track entry ZScore for stacking
            self.short_entry_zscores.append(zscore)
            self.bars_since_last_short_entry = 0

    def check_for_long_exit(self, bar, adaptive_params: dict):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        
        if regime == 2:
            self.vwap_zscore.notify_exit_trade_occurred()
            self.order_types.close_position_by_market_order()
            return

        net_pos = self.portfolio.net_position(self.instrument_id)
        
        if net_pos is not None and net_pos > 0 and self.current_kalman_zscore is not None:
            long_exit, _ = self.adaptive_manager.get_adaptive_exit_thresholds(self.entry_combined_factor)
            
            if self.current_kalman_zscore >= long_exit:
                self.vwap_zscore.notify_exit_trade_occurred()
                self.order_types.close_position_by_market_order()

    def check_for_short_exit(self, bar, adaptive_params: dict):
        if self.current_vix_value is None:
            return
        regime = self.get_vix_regime(self.current_vix_value)
        
        if regime == 2:
            self.vwap_zscore.notify_exit_trade_occurred()
            self.order_types.close_position_by_market_order()
            return
        
        net_pos = self.portfolio.net_position(self.instrument_id)
        
        if net_pos is not None and net_pos < 0 and self.current_kalman_zscore is not None:
            _, short_exit = self.adaptive_manager.get_adaptive_exit_thresholds(self.entry_combined_factor)
            
            if self.current_kalman_zscore <= short_exit:
                self.vwap_zscore.notify_exit_trade_occurred()
                self.order_types.close_position_by_market_order()

    def on_position_event(self, event: PositionEvent) -> None:
        pass

    def on_event(self, event: Any) -> None:
        pass

    def close_position(self) -> None:
        self.vwap_zscore.notify_exit_trade_occurred()
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

        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_mean", value=self.current_kalman_mean)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="combined_factor", value=self.current_combined_factor)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap", value=vwap_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_mean", value=kalman_mean)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vwap_zscore", value=self.current_zscore)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="kalman_zscore", value=self.current_kalman_zscore)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="vix", value=self.current_vix_value)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="position", value=self.portfolio.net_position(self.instrument_id) if self.portfolio.net_position(self.instrument_id) is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl is not None else None)
        self.collector.add_indicator(timestamp=self.clock.timestamp_ns(), name="equity", value=equity)

        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)
        
        self.adaptive_manager.print_slope_distribution()
    
    def on_order_filled(self, order_filled) -> None:
        # KEIN automatischer VWAP Reset bei allen Order Fills
        # self.vwap_zscore.notify_trade_occurred()
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        self.log.info(f"Position closed: {position_closed}")
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def update_visualizer_data(self, bar: Bar) -> None:
        net_position = self.portfolio.net_position(self.instrument_id)
        unrealized_pnl = self.portfolio.unrealized_pnl(self.instrument_id)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        usd_balance = account.balance_total()
        equity = usd_balance.as_double() + float(unrealized_pnl) if unrealized_pnl is not None else usd_balance.as_double()
            
        vwap_value = self.vwap_zscore.current_vwap_value
        kalman_mean = self.current_kalman_mean if self.kalman.initialized else None

        self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_mean", value=self.current_kalman_mean)
        self.collector.add_indicator(timestamp=bar.ts_event, name="combined_factor", value=self.current_combined_factor)
        self.collector.add_indicator(timestamp=bar.ts_event, name="vwap", value=vwap_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_mean", value=kalman_mean)
        self.collector.add_indicator(timestamp=bar.ts_event, name="vwap_zscore", value=self.current_zscore)
        self.collector.add_indicator(timestamp=bar.ts_event, name="kalman_zscore", value=self.current_kalman_zscore)
        self.collector.add_indicator(timestamp=bar.ts_event, name="vix", value=self.current_vix_value)
        self.collector.add_indicator(timestamp=bar.ts_event, name="position", value=net_position)
        self.collector.add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(self.realized_pnl) if self.realized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        self.collector.add_indicator(timestamp=bar.ts_event, name="equity", value=equity)
        self.collector.add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close)


