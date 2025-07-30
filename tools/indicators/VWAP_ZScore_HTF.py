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

        diff = price - vwap_value
        self.diff_window.append(diff)

        # Z-Score auf (Preis - VWAP)
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

    def set_zscore_window(self, window: int):
        self.zscore_window = window
        self.diff_window = deque(maxlen=window)

