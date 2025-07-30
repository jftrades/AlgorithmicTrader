import numpy as np
from collections import deque

class VWAPZScoreHTF:
    """
    Kein Basic Nautilus-Intraday-VWAP, sondern eigene Rolling-Berechnung!
    Z-Score wird auf der Differenz (Preis - VWAP) berechnet, nicht auf dem VWAP selbst!
    """
    def __init__(
        self,
        zscore_window: int = 60,
        zscore_entry_long: float = 1.0,
        zscore_entry_short: float = 1.0,
        zscore_condition_long: float = 1.0,
        zscore_condition_short: float = 1.0,
        vwap_lookback: int = 20,
        gap_interp_threshold: float = 0.01,
    ):
        self.zscore_window = zscore_window
        self.zscore_entry_long = zscore_entry_long
        self.zscore_entry_short = zscore_entry_short
        self.zscore_condition_long = zscore_condition_long
        self.zscore_condition_short = zscore_condition_short
        self.vwap_lookback = vwap_lookback
        self.price_volume_window = deque(maxlen=vwap_lookback)
        self.volume_window = deque(maxlen=vwap_lookback)
        self.diff_window = deque(maxlen=zscore_window)
        self.current_vwap_value = None
        self.interpolate_next_diff = False
        self.interpolate_steps = 0
        self.interpolate_count = 0
        self.skip_next_diff = False
        self.last_diff = None
        self.gap_interp_threshold = gap_interp_threshold
        
    def skip_or_interpolate_gap_for_zscore(self, prev_close, new_open, steps=3):
        gap = abs(new_open - prev_close) / prev_close if prev_close else 0
        if gap > self.gap_interp_threshold:
            # Interpolation aktivieren
            self.interpolate_next_diff = True
            self.interpolate_steps = steps
            self.interpolate_count = 0
            self._interp_target = new_open  # für update()
        else:
            # Normales Skippen
            self.skip_next_diff = True

    def update(self, bar):
        price = float(bar.close)
        volume = float(bar.volume)
        price_volume = price * volume

        self.price_volume_window.append(price_volume)
        self.volume_window.append(volume)

        if len(self.price_volume_window) < self.vwap_lookback or sum(self.volume_window) == 0:
            self.current_vwap_value = None
            return None, None

        vwap_value = sum(self.price_volume_window) / sum(self.volume_window)
        self.current_vwap_value = vwap_value

        diff = price - vwap_value

        # Interpolation bei großem Gap
        if self.interpolate_next_diff and self.last_diff is not None and self.interpolate_count < self.interpolate_steps:
            weight = (self.interpolate_count + 1) / (self.interpolate_steps + 1)
            interpolated_diff = (1 - weight) * self.last_diff + weight * diff
            self.diff_window.append(interpolated_diff)
            self.interpolate_count += 1
            if self.interpolate_count >= self.interpolate_steps:
                self.interpolate_next_diff = False
                self.interpolate_count = 0
        # Normales Skippen bei kleinem Gap
        elif self.skip_next_diff and self.last_diff is not None:
            self.diff_window.append(self.last_diff)
            self.skip_next_diff = False
        else:
            self.diff_window.append(diff)

        self.last_diff = diff

        if len(self.diff_window) < self.zscore_window:
            return vwap_value, None

        mean = np.mean(self.diff_window)
        std = np.std(self.diff_window)
        zscore = (diff - mean) / std if std > 0 else 0.0

        return vwap_value, zscore
    
    def reset(self):
        self.price_volume_window.clear()
        self.volume_window.clear()
        self.diff_window.clear()
        self.current_vwap_value = None

    def reset_vwap_to_gap(self, open_price: float, volume: float = 1.0):
        self.price_volume_window.clear()
        self.volume_window.clear()
        for _ in range(self.vwap_lookback):
            self.price_volume_window.append(open_price * volume)
            self.volume_window.append(volume)
        self.current_vwap_value = open_price

    def adjust_diff_window_for_gap(self, gap_value: float):
        gap_value = float(gap_value)  # <-- Fix: Stelle sicher, dass gap_value ein float ist!
        self.diff_window = deque([float(d) + gap_value for d in self.diff_window], maxlen=self.zscore_window)
        
    def set_zscore_window(self, window: int):
        self.zscore_window = window
        self.diff_window = deque(maxlen=window)


