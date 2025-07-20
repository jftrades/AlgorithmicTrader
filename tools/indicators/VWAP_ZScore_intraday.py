from nautilus_trader.indicators.volume_weighted_average_price import VolumeWeightedAveragePrice
from collections import deque
import numpy as np

class VWAPZScoreIntraday:
    """
    VWAP + Z-Score für Intraday-Bars, basierend auf dem Nautilus VWAP.
    Bänder werden wie beim HTF-ZScore berechnet.
    """
    def __init__(self, zscore_window: int = 60, zscore_entry: float = 1.0):
        self.zscore_window = zscore_window
        self.zscore_entry = zscore_entry
        self.vwap = VolumeWeightedAveragePrice()
        self.vwaps = deque(maxlen=zscore_window)
        self.current_vwap_value = None

    def update(self, bar):
        # bar muss .close und .volume haben
        self.vwap.update(bar)
        vwap_value = self.vwap.value
        self.current_vwap_value = vwap_value
        if vwap_value is not None:
            self.vwaps.append(vwap_value)
        else:
            return None, None

        if len(self.vwaps) < self.zscore_window:
            return vwap_value, None

        mean = np.mean(self.vwaps)
        std = np.std(self.vwaps)
        zscore = (vwap_value - mean) / std if std > 0 else 0.0

        return vwap_value, zscore

    def reset(self):
        self.vwap = VolumeWeightedAveragePrice()
        self.vwaps.clear()
        self.current_vwap_value = None

    def set_zscore_window(self, window: int):
        self.zscore_window = window
        self.vwaps = deque(maxlen=window)

    def get_bands(self, levels=(1, 2)):
        if len(self.vwaps) < self.zscore_window:
            return {f"upper_{lvl}": None for lvl in levels} | {f"lower_{lvl}": None for lvl in levels}
        mean = np.mean(self.vwaps)
        std = np.std(self.vwaps)
        bands = {}
        for lvl in levels:
            bands[f"upper_{lvl}"] = mean + lvl * std
            bands[f"lower_{lvl}"] = mean - lvl * std
        return bands