import numpy as np
from collections import deque
import datetime
from typing import Optional, Tuple, List

class VWAPZScoreHTFAnchored:
    def __init__(
        self,
        anchor_on_kalman_cross: bool = True,
        zscore_calculation: dict = None,
        gap_threshold_pct: float = 0.1,
        rth_start = (15, 40),
        rth_end = (21, 50),
        min_bars_for_zscore: int = 30,
        **kwargs
    ):
        # Anchoring-Parameter
        self.anchor_on_kalman_cross = anchor_on_kalman_cross
        self.min_bars_for_zscore = min_bars_for_zscore
        
        # Z-Score Calculation Method
        self.zscore_config = zscore_calculation or {"simple": {"enabled": True}}
        self.zscore_method = self._determine_zscore_method()
        
        # Kalman-Cross Tracking
        self.last_price_above_kalman = None
        self.kalman_exit_mean = None
        
        # Gap/RTH Parameter
        self.gap_threshold_pct = gap_threshold_pct
        self.rth_start = rth_start
        self.rth_end = rth_end
        
        # Aktuelles Segment
        self.current_segment = {
            'start_bar': 0,
            'anchor_reason': 'initial',
            'price_volume_data': [],
            'bars_in_segment': 0,
            'vwap_value': None
        }
        
        # History für Z-Score-Berechnungen
        self.segment_price_history = []
        self.segment_diff_history = []
        self.segment_atr_history = []  # Für ATR-basierte Z-Score
        
        # Gap Tracking (global)
        self.last_close = None
        self.cumulative_gap = 0.0
        self.gap_offsets = []
        self.total_bar_count = 0
        
        # RTH Tracking (global)
        self.rth_session_volumes = deque(maxlen=3)
        self.current_rth_volume = 0.0
        self.last_bar_was_rth = False
        
        # Current Values
        self.current_vwap_value = None
        self.current_zscore = None
        
        print(f"[ANCHORED VWAP] Initialized - Cross-triggered: {anchor_on_kalman_cross}, "
              f"ZScore method: {self.zscore_method}, Min bars: {min_bars_for_zscore}")

    def _determine_zscore_method(self) -> str:
        for method, config in self.zscore_config.items():
            if config.get('enabled', False):
                return method
        return 'simple'  # Default fallback

    def set_kalman_exit_mean(self, kalman_exit_mean: float):
        self.kalman_exit_mean = kalman_exit_mean

    def _detect_kalman_cross(self, current_price: float) -> bool:
        if self.kalman_exit_mean is None:
            return False
            
        current_above = current_price > self.kalman_exit_mean
        
        # Erster Bar - initialisiere State
        if self.last_price_above_kalman is None:
            self.last_price_above_kalman = current_above
            return True  # Initial anchor
            
        # Cross Detection
        cross_detected = current_above != self.last_price_above_kalman
        
        if cross_detected:
            direction = "above" if current_above else "below"
            print(f"[KALMAN CROSS] Price crossed {direction} Kalman-Exit-Mean {self.kalman_exit_mean:.4f} at price {current_price:.4f}")
            
        self.last_price_above_kalman = current_above
        return cross_detected

    def is_rth(self, bar):
        t = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(*self.rth_start)
        rth_end = datetime.time(*self.rth_end)
        return rth_start <= t <= rth_end

    def _should_anchor_new_segment(self, current_price: float) -> Tuple[bool, str]:
        # Primary: Kalman-Cross Detection
        if self.anchor_on_kalman_cross:
            if self._detect_kalman_cross(current_price):
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
        
        # History für neues Segment zurücksetzen
        self.segment_price_history = []
        self.segment_diff_history = []
        self.segment_atr_history = []
        
        print(f"[ANCHORED VWAP] New segment started at bar {self.total_bar_count} - Reason: {reason}")

    def _calculate_segment_vwap(self) -> Optional[float]:
        if not self.current_segment['price_volume_data']:
            return None
            
        total_pv = sum(price * volume for price, volume, _, _ in self.current_segment['price_volume_data'])
        total_volume = sum(volume for _, volume, _, _ in self.current_segment['price_volume_data'])
        
        if total_volume == 0:
            return None
            
        return total_pv / total_volume

    def _calculate_simple_zscore(self, current_price: float, vwap_value: float) -> float:
        return current_price - vwap_value

    def _calculate_atr_zscore(self, current_price: float, vwap_value: float, high: float, low: float) -> Optional[float]:
        atr_window = self.zscore_config.get('atr', {}).get('atr_window', 14)
        
        # True Range für aktuellen Bar
        if self.segment_atr_history:
            prev_close = self.segment_atr_history[-1]['close']
            true_range = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
        else:
            true_range = high - low
            
        # ATR History speichern
        self.segment_atr_history.append({
            'true_range': true_range,
            'close': current_price
        })
        
        # ATR berechnen (brauchen mindestens atr_window Werte)
        if len(self.segment_atr_history) < atr_window:
            return None
            
        recent_tr = [item['true_range'] for item in self.segment_atr_history[-atr_window:]]
        atr = np.mean(recent_tr)
        
        if atr == 0:
            return 0.0
            
        return (current_price - vwap_value) / atr

    def _calculate_std_zscore(self, current_price: float, vwap_value: float) -> Optional[float]:
        std_window = self.zscore_config.get('std', {}).get('std_window', 20)
        
        # Aktueller Diff
        current_diff = current_price - vwap_value
        self.segment_diff_history.append(current_diff)
        
        # Brauchen mindestens std_window Werte
        if len(self.segment_diff_history) < std_window:
            return None
            
        # Standard Deviation der letzten N Diffs
        recent_diffs = self.segment_diff_history[-std_window:]
        std_diff = np.std(recent_diffs)
        
        if std_diff == 0:
            return 0.0
            
        return current_diff / std_diff

    def _calculate_segment_zscore(self, current_price: float, vwap_value: float, high: float = None, low: float = None) -> Optional[float]:
        # Mindest-Bars Check
        if self.current_segment['bars_in_segment'] < self.min_bars_for_zscore:
            return None
            
        # Je nach Methode berechnen
        if self.zscore_method == 'simple':
            return self._calculate_simple_zscore(current_price, vwap_value)
            
        elif self.zscore_method == 'atr':
            if high is None or low is None:
                return None
            return self._calculate_atr_zscore(current_price, vwap_value, high, low)
            
        elif self.zscore_method == 'std':
            return self._calculate_std_zscore(current_price, vwap_value)
            
        else:
            # Fallback zu simple
            return self._calculate_simple_zscore(current_price, vwap_value)

    def update(self, bar, kalman_exit_mean: float = None) -> Tuple[Optional[float], Optional[float]]:
        price = float(bar.close)
        volume = float(bar.volume)
        high = float(bar.high)
        low = float(bar.low)
        
        # 1. Kalman-Exit-Mean aktualisieren
        if kalman_exit_mean is not None:
            self.set_kalman_exit_mean(kalman_exit_mean)
        
        # 2. Gap-Behandlung (global über alle Segmente)
        if self.last_close is not None:
            gap = float(bar.open) - float(self.last_close)
            gap_pct = abs(gap) / float(self.last_close) * 100
            if gap_pct > self.gap_threshold_pct:
                self.cumulative_gap += gap
                self.gap_offsets.append((self.total_bar_count, self.cumulative_gap))

        # 3. Gap-Offset berechnen
        offset = 0.0
        if self.gap_offsets:
            for idx, gap in reversed(self.gap_offsets):
                if idx <= self.total_bar_count:
                    offset = gap
                    break

        # 4. RTH-Session Tracking (global)
        is_rth = self.is_rth(bar)
        if is_rth:
            self.current_rth_volume += volume
            self.last_bar_was_rth = True
        else:
            if self.last_bar_was_rth:
                self.rth_session_volumes.append(self.current_rth_volume)
                self.current_rth_volume = 0.0
                self.last_bar_was_rth = False

        # 5. Adjusted Values
        if is_rth:
            adj_price = price - offset
            adj_volume = volume
            adj_high = high - offset
            adj_low = low - offset
        else:
            avg_rth_volume = np.mean(self.rth_session_volumes) if self.rth_session_volumes else volume
            adj_price = price - offset
            adj_volume = avg_rth_volume
            adj_high = high - offset
            adj_low = low - offset

        # 6. Segment Management - Prüfe ob neues Segment nötig
        should_anchor, anchor_reason = self._should_anchor_new_segment(adj_price)
        if should_anchor:
            self._start_new_segment(anchor_reason)

        # 7. Daten zum aktuellen Segment hinzufügen
        self.current_segment['price_volume_data'].append((adj_price, adj_volume, price, volume))
        self.current_segment['bars_in_segment'] += 1

        # 8. VWAP für aktuelles Segment berechnen
        vwap_value = self._calculate_segment_vwap()
        self.current_segment['vwap_value'] = vwap_value
        self.current_vwap_value = vwap_value

        # 9. Z-Score berechnen
        zscore = None
        if vwap_value is not None:
            zscore = self._calculate_segment_zscore(adj_price, vwap_value, adj_high, adj_low)

        # 10. Update global counters
        self.last_close = price
        self.total_bar_count += 1
        self.current_zscore = zscore

        return vwap_value, zscore

    def get_segment_info(self) -> dict:
        """Debug-Info über aktuelles Segment"""
        return {
            'segment_start_bar': self.current_segment['start_bar'],
            'anchor_reason': self.current_segment['anchor_reason'],
            'bars_in_segment': self.current_segment['bars_in_segment'],
            'total_bars_processed': self.total_bar_count,
            'current_vwap': self.current_segment['vwap_value'],
            'current_zscore': self.current_zscore,
            'zscore_method': self.zscore_method,
            'kalman_exit_mean': self.kalman_exit_mean,
            'anchor_on_kalman_cross': self.anchor_on_kalman_cross
        }

    def force_new_segment(self, reason: str = 'forced'):
        print(f"[ANCHORED VWAP] Forced new segment at bar {self.total_bar_count} - Reason: {reason}")
        self._start_new_segment(reason)

    def update_anchor_interval(self, new_interval: int):
        pass
        
    def reset_kalman_state(self):
        self.last_price_above_kalman = None