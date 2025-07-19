# using the nautilus VWAP but applying standart daviation on it
import numpy as np
from nautilus_trader.indicators.vwap import VolumeWeightedAveragePrice

class VWAPZScore:
    def __init__(self, zscore_window: int = 60, zscore_entry: float = 1.0, vwap_lookback: int = None):
        self.vwap = VolumeWeightedAveragePrice()
        self.zscore_window = zscore_window
        self.zscore_entry = zscore_entry
        self.spread_window = []
        self.vwap_lookback = vwap_lookback
        self.price_volume_window = []
        self.volume_window = []
        self.current_vwap_value = None

    def update(self, bar):
        self.vwap.handle_bar(bar)
        price = float(bar.close)
        volume = float(bar.volume)
        price_volume = price * volume

        # Rolling VWAP
        if self.vwap_lookback is not None:
            self.price_volume_window.append(price_volume)
            self.volume_window.append(volume)
            if len(self.price_volume_window) > self.vwap_lookback:
                self.price_volume_window.pop(0)
                self.volume_window.pop(0)
            vwap_value = sum(self.price_volume_window) / sum(self.volume_window) if sum(self.volume_window) > 0 else price
        else:
            vwap_value = self.vwap.value

        self.current_vwap_value = vwap_value

        # Spread und Z-Score wie gehabt
        spread = price - vwap_value
        self.spread_window.append(spread)
        if len(self.spread_window) > self.zscore_window:
            self.spread_window.pop(0)

        if len(self.spread_window) >= 2:
            mean = np.mean(self.spread_window)
            std = np.std(self.spread_window)
            zscore = (self.spread_window[-1] - mean) / std if std > 0 else 0.0
        else:
            zscore = 0.0

        return vwap_value, zscore

    def reset(self):
        self.vwap = VolumeWeightedAveragePrice()
        self.spread_window = []

    def set_zscore_window(self, window: int):
        self.zscore_window = window

    def get_bands(self, sigma: int = 2):
        if len(self.spread_window) >= 2:
            mean = np.mean(self.spread_window)
            std = np.std(self.spread_window)
            vwap = self.current_vwap_value 
            bands = {
                "upper_1": vwap + std,
                "lower_1": vwap - std,
                "upper_2": vwap + 2 * std,
                "lower_2": vwap - 2 * std,
            }
        else:
            bands = {
                "upper_1": None,
                "lower_1": None,
                "upper_2": None,
                "lower_2": None,
            }
        return bands
