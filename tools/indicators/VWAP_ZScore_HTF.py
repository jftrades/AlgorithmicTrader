import numpy as np
from collections import deque

class VWAPZScoreHTF:
    def __init__(
        self,
        zscore_window: int = 60,
        vwap_lookback: int = 20,
        gap_threshold_pct: float = 0.1,  # ab wie viel Prozent ein Gap als signifikant gilt
        **kwargs
    ):
        self.zscore_window = zscore_window
        self.vwap_lookback = vwap_lookback
        self.price_volume_window = deque(maxlen=vwap_lookback)
        self.volume_window = deque(maxlen=vwap_lookback)
        self.diff_window = deque(maxlen=zscore_window)
        self.current_vwap_value = None
        self.last_close = None
        self.gap_offsets = []  # List of (bar_index, cumulative_gap)
        self.cumulative_gap = 0.0
        self.bar_index = 0
        self.gap_threshold_pct = gap_threshold_pct

    def update_gap_list(self, bar, prev_close):
        raw_gap = float(bar.open) - float(prev_close)
        gap_pct = abs(raw_gap) / float(prev_close) * 100 if prev_close else 0.0
        if gap_pct > self.gap_threshold_pct:
            self.cumulative_gap += raw_gap
            self.gap_offsets.append((self.bar_index, self.cumulative_gap))

    def cumulative_gap_at(self, bar_index):
        # Returns the latest cumulative gap up to this bar_index
        if not self.gap_offsets:
            return 0.0
        # Find the last gap offset <= bar_index
        for idx, gap in reversed(self.gap_offsets):
            if idx <= bar_index:
                return gap
        return 0.0

    def update(self, bar):
        price = float(bar.close)
        volume = float(bar.volume)

        # Gap-Erkennung (nutze open/close, nicht close/close!)
        if self.last_close is not None:
            self.update_gap_list(bar, self.last_close)

        # Kumulierten Gap-Offset für diese Bar berechnen
        offset = self.cumulative_gap_at(self.bar_index)
        adjusted_close = price - offset

        price_volume = adjusted_close * volume
        self.price_volume_window.append(price_volume)
        self.volume_window.append(volume)

        if len(self.price_volume_window) < self.vwap_lookback or sum(self.volume_window) == 0:
            self.current_vwap_value = None
            self.last_close = price
            self.bar_index += 1
            return None, None

        vwap_value = sum(self.price_volume_window) / sum(self.volume_window)
        self.current_vwap_value = vwap_value

        diff = adjusted_close - vwap_value
        self.diff_window.append(diff)

        if len(self.diff_window) < self.zscore_window:
            self.last_close = price
            self.bar_index += 1
            return vwap_value, None

        mean = np.mean(self.diff_window)
        std = np.std(self.diff_window)
        zscore = (diff - mean) / std if std > 0 else 0.0

        self.last_close = price
        self.bar_index += 1
        return vwap_value, zscore