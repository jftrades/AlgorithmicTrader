import numpy as np
from collections import deque
import datetime
from typing import Optional, Tuple

class VWAPZScoreHTFAnchored:
    def __init__(
        self,
        anchor_on_kalman_cross: bool = True,
        zscore_calculation: dict = None,
        gap_threshold_pct: float = 0.1,
        rth_start = (15, 40),
        rth_end = (21, 50),
        min_bars_for_zscore: int = 30,
        reset_grace_period: int = 25,
        require_trade_for_reset: bool = True,
        **kwargs
    ):
        self.anchor_on_kalman_cross = anchor_on_kalman_cross
        self.min_bars_for_zscore = min_bars_for_zscore
        self.zscore_config = zscore_calculation or {"simple": {"enabled": True}}
        self.zscore_method = self._determine_zscore_method()
        
        self.last_price_above_kalman = None
        self.kalman_exit_mean = None
        self.gap_threshold_pct = gap_threshold_pct
        self.rth_start = rth_start
        self.rth_end = rth_end
        
        self.current_segment = {
            'start_bar': 0,
            'anchor_reason': 'initial',
            'price_volume_data': [],
            'bars_in_segment': 0,
            'vwap_value': None
        }
        
        self.last_anchor_bar = -1
        self.reset_grace_period = reset_grace_period
        self.require_trade_for_reset = require_trade_for_reset
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

    def is_rth(self, bar):
        t = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(*self.rth_start)
        rth_end = datetime.time(*self.rth_end)
        return rth_start <= t <= rth_end

    def _should_anchor_new_segment(self, current_price: float, open_price: float = None) -> Tuple[bool, str]:
        bars_since_last_anchor = self.total_bar_count - self.last_anchor_bar
        if bars_since_last_anchor < self.reset_grace_period:
            return False, 'grace_period_active'
        
        if self.require_trade_for_reset and not self.trade_occurred_since_reset:
            return False, 'no_trade_since_reset'
        
        if self.anchor_on_kalman_cross:
            if self._detect_kalman_cross(current_price, open_price):
                return True, 'kalman_cross'
            
        return False, 'none'

    def _start_new_segment(self, reason: str = 'unknown'):
        self.current_segment = {
            'start_bar': self.total_bar_count,
            'anchor_reason': reason,
            'price_volume_data': [],
            'bars_in_segment': 0,
            'vwap_value': None
        }
        
        if reason in ['kalman_cross', 'gap', 'initial', 'forced']:
            self.segment_diff_history = []
            self.segment_atr_history = []
        
        self.last_anchor_bar = self.total_bar_count
        self.trade_occurred_since_reset = False

    def _calculate_segment_vwap(self) -> Optional[float]:
        if not self.current_segment['price_volume_data']:
            return None
            
        total_pv = sum(adj_price * adj_volume for adj_price, adj_volume, _, _ in self.current_segment['price_volume_data'])
        total_volume = sum(adj_volume for _, adj_volume, _, _ in self.current_segment['price_volume_data'])
        
        if total_volume == 0:
            return None
            
        return total_pv / total_volume

    def _calculate_simple_zscore(self, current_price: float, vwap_value: float, asymmetric_offset: float = 0.0) -> float:
        """
        Berechnet simple Z-Score mit asymmetrischem Offset als direkte Z-Score-Units
        
        Args:
            current_price: Aktueller Preis
            vwap_value: VWAP Wert
            asymmetric_offset: Direkter Z-Score Offset (z.B. 0.5 = +0.5 Z-Score Units)
        """
        # Standardabweichung der Preise im aktuellen Segment berechnen
        if len(self.current_segment['price_volume_data']) < 10:
            # Fallback: einfache Prozent-Differenz als Pseudo-Z-Score
            base_zscore = ((current_price - vwap_value) / vwap_value) * 100
        else:
            # Echte Z-Score Berechnung mit Standardabweichung
            prices = [price for price, _, _, _ in self.current_segment['price_volume_data']]
            std_price = np.std(prices)
            
            if std_price == 0:
                base_zscore = 0.0
            else:
                base_zscore = (current_price - vwap_value) / std_price
        
        # Asymmetrischer Offset wird direkt zu Z-Score addiert
        return base_zscore + asymmetric_offset

    def _calculate_atr_zscore(self, current_price: float, vwap_value: float, high: float, low: float, asymmetric_offset: float = 0.0) -> Optional[float]:
        """
        Berechnet ATR-normalisierte Z-Score mit asymmetrischem Offset als direkte Z-Score-Units
        """
        atr_window = self.zscore_config.get('atr', {}).get('atr_window', 14)
        
        if self.segment_atr_history:
            prev_close = self.segment_atr_history[-1]['close']
            true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        else:
            true_range = high - low
            
        self.segment_atr_history.append({'true_range': true_range, 'close': current_price})
        
        if len(self.segment_atr_history) < atr_window:
            return None
            
        recent_tr = [item['true_range'] for item in self.segment_atr_history[-atr_window:]]
        atr = np.mean(recent_tr)
        
        if atr == 0:
            return 0.0
            
        # Basis Z-Score (ATR-normalisiert) berechnen
        base_zscore = (current_price - vwap_value) / atr
        # Asymmetrischer Offset wird direkt zu Z-Score addiert
        return base_zscore + asymmetric_offset

    def _calculate_std_zscore(self, current_price: float, vwap_value: float, asymmetric_offset: float = 0.0) -> Optional[float]:
        """
        Berechnet Standardabweichungs-normalisierte Z-Score mit asymmetrischem Offset als direkte Z-Score-Units
        """
        std_window = self.zscore_config.get('std', {}).get('std_window', 20)
        
        # Basis-Differenz berechnen (ohne Offset für Standardabweichung)
        current_diff = current_price - vwap_value
        self.segment_diff_history.append(current_diff)
        
        if len(self.segment_diff_history) < std_window:
            return None
            
        recent_diffs = self.segment_diff_history[-std_window:]
        std_diff = np.std(recent_diffs)
        
        if std_diff == 0:
            return 0.0
            
        # Basis Z-Score (Standardabweichungs-normalisiert) berechnen
        base_zscore = current_diff / std_diff
        # Asymmetrischer Offset wird direkt zu Z-Score addiert
        return base_zscore + asymmetric_offset

    def _calculate_segment_zscore(self, current_price: float, vwap_value: float, high: float = None, low: float = None, asymmetric_offset: float = 0.0) -> Optional[float]:
        if self.current_segment['bars_in_segment'] < self.min_bars_for_zscore:
            return None
            
        if self.zscore_method == 'simple':
            return self._calculate_simple_zscore(current_price, vwap_value, asymmetric_offset)
        elif self.zscore_method == 'atr':
            if high is None or low is None:
                return None
            atr_zscore = self._calculate_atr_zscore(current_price, vwap_value, high, low, asymmetric_offset)
            if atr_zscore is None:
                return self._calculate_simple_zscore(current_price, vwap_value, asymmetric_offset)
            return atr_zscore
        elif self.zscore_method == 'std':
            std_zscore = self._calculate_std_zscore(current_price, vwap_value, asymmetric_offset)
            if std_zscore is None:
                return self._calculate_simple_zscore(current_price, vwap_value, asymmetric_offset)
            return std_zscore
        else:
            return self._calculate_simple_zscore(current_price, vwap_value, asymmetric_offset)

    def update(self, bar, kalman_exit_mean: float = None, asymmetric_offset: float = 0.0) -> Tuple[Optional[float], Optional[float]]:
        price = float(bar.close)
        volume = float(bar.volume)
        high = float(bar.high)
        low = float(bar.low)
        
        if kalman_exit_mean is not None:
            self.set_kalman_exit_mean(kalman_exit_mean)
        
        if self.last_close is not None:
            gap = float(bar.open) - float(self.last_close)
            gap_pct = abs(gap) / float(self.last_close) * 100
            if gap_pct > self.gap_threshold_pct:
                self.cumulative_gap += gap
                self.gap_offsets.append((self.total_bar_count, self.cumulative_gap))

        offset = 0.0
        if self.gap_offsets:
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
        should_anchor, anchor_reason = self._should_anchor_new_segment(adj_price, adj_open)
        if should_anchor:
            self._start_new_segment(anchor_reason)

        self.current_segment['price_volume_data'].append((adj_price, adj_volume, price, volume))
        self.current_segment['bars_in_segment'] += 1

        vwap_value = self._calculate_segment_vwap()
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
        bars_since_anchor = self.total_bar_count - self.last_anchor_bar
        grace_remaining = max(0, self.reset_grace_period - bars_since_anchor)
        
        return {
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
            'require_trade_for_reset': self.require_trade_for_reset,
            'trade_occurred_since_reset': self.trade_occurred_since_reset,
            'reset_conditions_met': grace_remaining == 0 and (not self.require_trade_for_reset or self.trade_occurred_since_reset)
        }

    def force_new_segment(self, reason: str = 'forced'):
        self._start_new_segment(reason)

    def update_anchor_interval(self, new_interval: int):
        pass
        
    def reset_kalman_state(self):
        self.last_price_above_kalman = None