import numpy as np
from collections import deque

class VWAPZScoreHTF:
    """
    Kein Basic Nautilus-Intraday-VWAP, sondern eigene Rolling-Berechnung!
    """
    def __init__(self, zscore_window: int = 60, zscore_entry_long: float = 1.0, zscore_entry_short: float = 1.0, vwap_lookback: int = 20):
        self.zscore_window = zscore_window
        self.zscore_entry_long = zscore_entry_long
        self.zscore_entry_long = zscore_entry_short
        self.vwap_lookback = vwap_lookback
        self.price_volume_window = deque(maxlen=vwap_lookback)
        self.volume_window = deque(maxlen=vwap_lookback)
        self.vwaps = deque(maxlen=zscore_window)
        self.current_vwap_value = None

    def update(self, bar):
        price = float(bar.close)
        volume = float(bar.volume)
        price_volume = price * volume

        self.price_volume_window.append(price_volume)
        self.volume_window.append(volume)

        # Rolling VWAP über Lookback
        if len(self.price_volume_window) < self.vwap_lookback or sum(self.volume_window) == 0:
            self.current_vwap_value = None
            return None, None

        vwap_value = sum(self.price_volume_window) / sum(self.volume_window)
        self.current_vwap_value = vwap_value
        self.vwaps.append(vwap_value)

        # Z-Score auf VWAP
        if len(self.vwaps) < self.zscore_window:
            return vwap_value, None

        mean = np.mean(self.vwaps)
        std = np.std(self.vwaps)
        zscore = (vwap_value - mean) / std if std > 0 else 0.0

        return vwap_value, zscore

    def reset(self):
        self.price_volume_window.clear()
        self.volume_window.clear()
        self.vwaps.clear()
        self.current_vwap_value = None

    def set_zscore_window(self, window: int):
        self.zscore_window = window
        self.vwaps = deque(maxlen=window)

