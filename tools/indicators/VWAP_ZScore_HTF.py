import numpy as np
from collections import deque

class VWAPZScoreHTF:
    def __init__(
        self,
        zscore_window: int = 60,
        vwap_lookback: int = 20,
        gap_base_blend_bars: int = 20,   # Basiswert, kann fix bleiben -> könnte man in die yaml packen aber so auch recht robust
        max_blend_bars: int = 80,        # Obergrenze für Blend-Bars -> könnte man in die yaml packen aber so auch recht robust
        min_blend_bars: int = 6,         # Untergrenze für Blend-Bars -> könnte man in die yaml packen aber so auch recht robust
        **kwargs
    ):
        self.zscore_window = zscore_window
        self.vwap_lookback = vwap_lookback
        self.price_volume_window = deque(maxlen=vwap_lookback)
        self.volume_window = deque(maxlen=vwap_lookback)
        self.diff_window = deque(maxlen=zscore_window)
        self.current_vwap_value = None
        self.last_close = None
        self.gap_active = False
        self.gap_value = 0.0
        self.gap_counter = 0
        self.gap_blend_bars = gap_base_blend_bars
        self.max_blend_bars = max_blend_bars
        self.min_blend_bars = min_blend_bars

    def update(self, bar):
        price = float(bar.close)
        volume = float(bar.volume)

        # 1. Gap-Erkennung & adaptive Blend-Bars
        if self.last_close is not None:
            gap = price - self.last_close
            gap_pct = abs(gap) / self.last_close * 100
            # Dynamische Blend-Bars: z.B. 1 Bar pro 0.2% Gap, min/max clampen
            if gap_pct > 0.1:
                blend_bars = int(min(max(gap_pct / 0.2, self.min_blend_bars), self.max_blend_bars))
                self.gap_active = True
                self.gap_value = gap
                self.gap_counter = 0
                self.gap_blend_bars = blend_bars

        # 2. Gap sanft ausblenden (Blend-Phase, adaptive Länge & Gewichtung)
        if self.gap_active and self.gap_counter < self.gap_blend_bars:
            w = 1.0 - self.gap_counter / self.gap_blend_bars
            # Erste Bar nach Gap: Gewicht noch stärker reduzieren
            if self.gap_counter == 0:
                w *= 0.15 if self.gap_blend_bars > 20 else 0.5  # noch schwächer bei großen Gaps
            adj_price = price - self.gap_value * w
            self.gap_counter += 1
        else:
            adj_price = price
            self.gap_active = False

        price_volume = adj_price * volume
        self.price_volume_window.append(price_volume)
        self.volume_window.append(volume)

        if len(self.price_volume_window) < self.vwap_lookback or sum(self.volume_window) == 0:
            self.current_vwap_value = None
            self.last_close = price
            return None, None

        vwap_value = sum(self.price_volume_window) / sum(self.volume_window)
        self.current_vwap_value = vwap_value

        diff = price - vwap_value
        self.diff_window.append(diff)

        if len(self.diff_window) < self.zscore_window:
            self.last_close = price
            return vwap_value, None

        mean = np.mean(self.diff_window)
        std = np.std(self.diff_window)
        zscore = (diff - mean) / std if std > 0 else 0.0

        self.last_close = price
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

    def set_zscore_window(self, window: int):
        self.zscore_window = window
        self.diff_window = deque(maxlen=window)
