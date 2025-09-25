import numpy as np
from collections import deque
import datetime
from typing import Optional, Tuple

class VWAPZScoreHTFAnchored:
    def __init__(
        self,
        anchor_method: str = "kalman_cross",
        zscore_calculation: dict = None,
        gap_threshold_pct: float = 0.1,
        rth_start = (15, 40),
        rth_end = (21, 50),
        min_bars_for_zscore: int = 30,
        reset_grace_period: int = 25,
        require_trade_for_reset: bool = True,
        rolling_window_bars: int = 288,
        log_callback = None,  # Add logging callback
        **kwargs
    ):
        self.anchor_method = anchor_method
        self.anchor_on_kalman_cross = anchor_method == "kalman_cross"
        self.rolling_window_bars = rolling_window_bars
        self.min_bars_for_zscore = min_bars_for_zscore
        self.zscore_config = zscore_calculation or {"simple": {"enabled": True}}
        self.zscore_method = self._determine_zscore_method()
        self.log_callback = log_callback  # Store logging callback
        
        self.last_price_above_kalman = None
        self.kalman_exit_mean = None
        self.gap_threshold_pct = gap_threshold_pct
        self.rth_start = rth_start
        self.rth_end = rth_end
        
        self.last_date = None
        self.last_week = None
        
        self.rolling_price_volume_data = deque(maxlen=rolling_window_bars)
        
        self.current_segment = {
            'start_bar': 0,
            'anchor_reason': 'initial',
            'price_volume_data': [],
            'bars_in_segment': 0,
            'vwap_value': None
        }
        
        self.last_anchor_bar = -1
        self.reset_grace_period = reset_grace_period
        # Trade requirement only applies to kalman_cross method
        self.require_trade_for_reset = require_trade_for_reset if anchor_method == "kalman_cross" else False
        self.trade_occurred_since_reset = False
        
        self.segment_diff_history = []
        self.segment_atr_history = []
        
        self.last_close = None
        self.cumulative_gap = 0.0
        self.gap_offsets = []
        self.total_bar_count = 0
        
        self.rth_session_volumes = deque(maxlen=3)
        self.current_rth_volume = 0.0
        self.last_bar_was_rth = False
        
        self.current_vwap_value = None
        self.current_zscore = None

    def _determine_zscore_method(self) -> str:
        for method, config in self.zscore_config.items():
            if config.get('enabled', False):
                return method
        return 'simple'

    def notify_trade_occurred(self):
        if self.require_trade_for_reset:
            self.trade_occurred_since_reset = True
            
    def notify_exit_trade_occurred(self):
        """Spezielle Methode für Exit-Trades - nur diese lösen VWAP Reset aus"""
        if self.require_trade_for_reset:
            self.trade_occurred_since_reset = True

    def set_kalman_exit_mean(self, kalman_exit_mean: float):
        self.kalman_exit_mean = kalman_exit_mean

    def _detect_kalman_cross(self, current_price: float, open_price: float = None) -> bool:
        if self.kalman_exit_mean is None:
            return False
            
        current_above = current_price > self.kalman_exit_mean
        
        if self.last_price_above_kalman is None:
            self.last_price_above_kalman = current_above
            return True
        
        if open_price is not None and self.last_close is not None:
            last_above = self.last_close > self.kalman_exit_mean
            open_above = open_price > self.kalman_exit_mean
            
            if last_above != open_above:
                self.last_price_above_kalman = current_above
                return True
            
        cross_detected = current_above != self.last_price_above_kalman
        
        if cross_detected:
            self.last_price_above_kalman = current_above
            return True
            
        return False

    def _detect_new_day(self, bar) -> bool:
        bar_date = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).date()
        
        if self.last_date is None:
            self.last_date = bar_date
            return False  # Don't trigger reset on first bar ever
            
        if bar_date != self.last_date:
            self.last_date = bar_date
            return True  # Trigger reset on day change
            
        return False

    def _detect_new_week(self, bar) -> bool:
        bar_datetime = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc)
        current_week = bar_datetime.isocalendar()[:2]
        
        if self.last_week is None:
            self.last_week = current_week
            return False  # Don't trigger reset on first bar ever
            
        if current_week != self.last_week:
            self.last_week = current_week
            return True  # Trigger reset on week change
            
        return False

    def is_rth(self, bar):
        t = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(*self.rth_start)
        rth_end = datetime.time(*self.rth_end)
        return rth_start <= t <= rth_end

    def _should_anchor_new_segment(self, bar, current_price: float, open_price: float = None) -> Tuple[bool, str]:
        if self.anchor_method == "rolling":
            return False, 'rolling_vwap'
            
        bars_since_last_anchor = self.total_bar_count - self.last_anchor_bar
        
        # Check anchor conditions based on method
        if self.anchor_method == "kalman_cross":
            # For kalman_cross: apply grace period AND trade requirement
            if bars_since_last_anchor < self.reset_grace_period:
                return False, 'grace_period_active'
            if self.require_trade_for_reset and not self.trade_occurred_since_reset:
                return False, 'no_trade_since_reset'
            
            if self.kalman_exit_mean is not None and self._detect_kalman_cross(current_price, open_price):
                return True, 'kalman_cross'
        elif self.anchor_method == "daily":
            # For daily: IGNORE grace period - daily resets are mandatory for clean ZScore evolution
            if self._detect_new_day(bar):
                return True, 'new_day'
        elif self.anchor_method == "weekly":
            # For weekly: IGNORE grace period - weekly resets are mandatory  
            if self._detect_new_week(bar):
                return True, 'new_week'
            
        return False, 'none'

    def _start_new_segment(self, reason: str = 'unknown'):
        """Start a new VWAP segment with complete hard reset"""
        self.current_segment = {
            'start_bar': self.total_bar_count,
            'anchor_reason': reason,
            'price_volume_data': [],
            'bars_in_segment': 0,
            'vwap_value': None
        }
        
        self.segment_diff_history = []
        self.segment_atr_history = []
        
        self.last_anchor_bar = self.total_bar_count
        self.trade_occurred_since_reset = False
        
        # Force ZScore to None for clean reset - it will start at 0.0 once calculated
        self.current_zscore = None
        
        # For daily and weekly anchoring, ensure complete clean reset
        if reason in ['new_day', 'new_week']:
            self.gap_offsets = []
            self.cumulative_gap = 0.0

    def _calculate_segment_vwap(self) -> Optional[float]:
        if self.anchor_method == "rolling":
            if not self.rolling_price_volume_data:
                return None
            total_pv = sum(adj_price * adj_volume for adj_price, adj_volume, _, _ in self.rolling_price_volume_data)
            total_volume = sum(adj_volume for _, adj_volume, _, _ in self.rolling_price_volume_data)
        else:
            if not self.current_segment['price_volume_data']:
                return None
            total_pv = sum(adj_price * adj_volume for adj_price, adj_volume, _, _ in self.current_segment['price_volume_data'])
            total_volume = sum(adj_volume for _, adj_volume, _, _ in self.current_segment['price_volume_data'])
        
        if total_volume == 0:
            return None
            
        return total_pv / total_volume

    def _calculate_simple_zscore(self, current_price: float, vwap_value: float, asymmetric_offset: float = 0.0) -> float:
        if self.anchor_method == "rolling":
            price_data = [price for price, _, _, _ in self.rolling_price_volume_data]
        else:
            price_data = [price for price, _, _, _ in self.current_segment['price_volume_data']]
            
        bars_available = len(price_data)
        
        # More aggressive early ZScore calculation - allow calculation from bar 2 onwards
        if bars_available < 2:
            base_zscore = 0.0
        else:
            # Calculate standard deviation
            std_price = np.std(price_data, ddof=1) if bars_available > 1 else abs(current_price - vwap_value)
            
            # Ultra-aggressive scaling that starts immediately with substantial values
            if bars_available < 10:
                # Start at 0.8 and reach 1.0 by bar 10 - much more aggressive evolution
                scaling_factor = 0.8 + (0.2 * (bars_available - 2) / 8)
                scaling_factor = max(0.8, min(1.0, scaling_factor))
            else:
                scaling_factor = 1.0
            
            # Make threshold much more lenient - use relative threshold based on price level
            # For SPY ~500, this gives threshold ~0.05 instead of ~0.5
            threshold = vwap_value * 0.0001  # 10x more sensitive threshold
            
            if std_price == 0 or std_price < threshold:
                # Even if std is small, force some ZScore if there's price difference
                if bars_available >= 2 and abs(current_price - vwap_value) > (vwap_value * 0.00001):
                    base_zscore = (current_price - vwap_value) * scaling_factor * 10  # Force evolution
                else:
                    base_zscore = 0.0
            else:
                # Calculate raw ZScore
                raw_zscore = (current_price - vwap_value) / std_price
                
                # Apply scaling factor - much more aggressive
                base_zscore = raw_zscore * scaling_factor
        
        return base_zscore + asymmetric_offset

    def _calculate_segment_zscore(self, current_price: float, vwap_value: float, high: float = None, low: float = None, asymmetric_offset: float = 0.0) -> Optional[float]:
        if self.anchor_method == "rolling":
            bars_available = len(self.rolling_price_volume_data)
        else:
            bars_available = self.current_segment['bars_in_segment']
            
        # Always apply min_bars requirement for all anchor methods
        if bars_available < self.min_bars_for_zscore:
            return None
            
        if self.zscore_method == 'simple':
            return self._calculate_simple_zscore(current_price, vwap_value, asymmetric_offset)
        else:
            return self._calculate_simple_zscore(current_price, vwap_value, asymmetric_offset)
            return self._calculate_simple_zscore(current_price, vwap_value, asymmetric_offset)

    def update(self, bar, asymmetric_offset: float = 0.0) -> Tuple[Optional[float], Optional[float]]:
        price = float(bar.close)
        volume = float(bar.volume)
        high = float(bar.high)
        low = float(bar.low)
        
        # Only apply gap detection for kalman_cross and rolling methods
        if self.anchor_method in ["kalman_cross", "rolling"] and self.last_close is not None:
            gap = float(bar.open) - float(self.last_close)
            gap_pct = abs(gap) / float(self.last_close) * 100
            if gap_pct > self.gap_threshold_pct:
                self.cumulative_gap += gap
                self.gap_offsets.append((self.total_bar_count, self.cumulative_gap))

        # Only apply gap offset for kalman_cross and rolling methods
        offset = 0.0
        if self.anchor_method in ["kalman_cross", "rolling"] and self.gap_offsets:
            for idx, gap in reversed(self.gap_offsets):
                if idx <= self.total_bar_count:
                    offset = gap
                    break

        is_rth = self.is_rth(bar)
        if is_rth:
            self.current_rth_volume += volume
            self.last_bar_was_rth = True
        else:
            if self.last_bar_was_rth:
                self.rth_session_volumes.append(self.current_rth_volume)
                self.current_rth_volume = 0.0
                self.last_bar_was_rth = False

        adj_price = price - offset
        adj_high = high - offset
        adj_low = low - offset
        
        if is_rth:
            adj_volume = volume
        else:
            avg_rth_volume = np.mean(self.rth_session_volumes) if self.rth_session_volumes else volume
            adj_volume = avg_rth_volume

        adj_open = float(bar.open) - offset
        
        if self.anchor_method == "rolling":
            self.rolling_price_volume_data.append((adj_price, adj_volume, price, volume))
        else:
            should_anchor, anchor_reason = self._should_anchor_new_segment(bar, adj_price, adj_open)
            
            if should_anchor:
                self._start_new_segment(anchor_reason)
                
                # For daily and weekly anchoring, ensure completely clean start
                if anchor_reason in ['new_day', 'new_week']:
                    self.gap_offsets = []
                    self.cumulative_gap = 0.0
                    adj_price = price
                    adj_high = high
                    adj_low = low
                    adj_open = float(bar.open)
                    if is_rth:
                        adj_volume = volume
                    else:
                        avg_rth_volume = np.mean(self.rth_session_volumes) if self.rth_session_volumes else volume
                        adj_volume = avg_rth_volume
            
            bars_before = self.current_segment['bars_in_segment']
            self.current_segment['price_volume_data'].append((adj_price, adj_volume, price, volume))
            self.current_segment['bars_in_segment'] += 1

        vwap_value = self._calculate_segment_vwap()
        
        if self.anchor_method != "rolling":
            self.current_segment['vwap_value'] = vwap_value
        self.current_vwap_value = vwap_value

        zscore = None
        if vwap_value is not None:
            zscore = self._calculate_segment_zscore(adj_price, vwap_value, adj_high, adj_low, asymmetric_offset)

        self.last_close = price
        self.total_bar_count += 1
        self.current_zscore = zscore

        return vwap_value, zscore

    def get_segment_info(self) -> dict:
        if self.anchor_method == "rolling":
            bars_since_anchor = len(self.rolling_price_volume_data)
            grace_remaining = 0
            return {
                'anchor_method': self.anchor_method,
                'bars_in_segment': bars_since_anchor,
                'total_bars_processed': self.total_bar_count,
                'current_vwap': self.current_vwap_value,
                'current_zscore': self.current_zscore,
                'zscore_method': self.zscore_method,
                'rolling_window_bars': self.rolling_window_bars,
                'grace_period_active': False,
                'reset_conditions_met': True
            }
        else:
            bars_since_anchor = self.total_bar_count - self.last_anchor_bar
            grace_remaining = max(0, self.reset_grace_period - bars_since_anchor)
            
            # Trade requirement only applies to kalman_cross
            trade_requirement_met = True
            if self.anchor_method == "kalman_cross":
                trade_requirement_met = not self.require_trade_for_reset or self.trade_occurred_since_reset
            
            return {
                'anchor_method': self.anchor_method,
                'segment_start_bar': self.current_segment['start_bar'],
                'anchor_reason': self.current_segment['anchor_reason'],
                'bars_in_segment': self.current_segment['bars_in_segment'],
                'total_bars_processed': self.total_bar_count,
                'current_vwap': self.current_segment['vwap_value'],
                'current_zscore': self.current_zscore,
                'zscore_method': self.zscore_method,
                'kalman_exit_mean': self.kalman_exit_mean,
                'anchor_on_kalman_cross': self.anchor_on_kalman_cross,
                'last_anchor_bar': self.last_anchor_bar,
                'bars_since_anchor': bars_since_anchor,
                'grace_period_remaining': grace_remaining,
                'grace_period_active': grace_remaining > 0,
                'require_trade_for_reset': self.require_trade_for_reset if self.anchor_method == "kalman_cross" else False,
                'trade_occurred_since_reset': self.trade_occurred_since_reset if self.anchor_method == "kalman_cross" else True,
                'reset_conditions_met': grace_remaining == 0 and trade_requirement_met
            }

    def force_new_segment(self, reason: str = 'forced'):
        self._start_new_segment(reason)

    def update_anchor_interval(self, new_interval: int):
        pass
        
    def reset_kalman_state(self):
        self.last_price_above_kalman = None

# Backward compatibility alias
VWAPZScoreHTF = VWAPZScoreHTFAnchored