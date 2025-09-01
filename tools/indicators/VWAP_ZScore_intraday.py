from nautilus_trader.indicators.vwap import VolumeWeightedAveragePrice
from collections import deque
import numpy as np

class VWAPZScoreIntraday:
    def __init__(self, zscore_window: int = 20):
        self.zscore_window = zscore_window
        self.vwap = VolumeWeightedAveragePrice()
        self.daily_vwaps = deque(maxlen=zscore_window)  # Store end-of-day VWAPs
        self.last_day = None

    def update(self, bar):
        # Check if new day - store previous day's final VWAP
        current_day = bar.ts_init.to_pydatetime().day
        if self.last_day is not None and current_day != self.last_day:
            if self.vwap.value > 0:  # Valid VWAP from previous day
                self.daily_vwaps.append(self.vwap.value)
        
        self.last_day = current_day
        
        # Nautilus handles daily reset automatically
        self.vwap.handle_bar(bar)
        
        # Calculate Z-Score if we have enough historical daily VWAPs
        if len(self.daily_vwaps) < 2:
            return self.vwap.value, None
            
        mean = np.mean(self.daily_vwaps)
        std = np.std(self.daily_vwaps)
        zscore = (self.vwap.value - mean) / std if std > 0 else 0.0
        
        return self.vwap.value, zscore

    def get_bands(self, levels=(1, 2)):
        if len(self.daily_vwaps) < 2:
            return {f"upper_{lvl}": None for lvl in levels} | {f"lower_{lvl}": None for lvl in levels}
        
        mean = np.mean(self.daily_vwaps)
        std = np.std(self.daily_vwaps)
        
        return {f"upper_{lvl}": mean + lvl * std for lvl in levels} | {f"lower_{lvl}": mean - lvl * std for lvl in levels}