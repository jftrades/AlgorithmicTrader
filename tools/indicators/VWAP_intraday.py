from nautilus_trader.indicators.vwap import VolumeWeightedAveragePrice
import numpy as np
import pandas as pd

class VWAPIntraday:
    def __init__(self):
        self.vwap = VolumeWeightedAveragePrice()
        self.prices = []
        self.volumes = []
        self.weighted_prices = []
        self.last_day = None
        
    def update(self, bar):
        """Update VWAP with new bar data."""
        # Let Nautilus VWAP handle daily reset automatically
        self.vwap.handle_bar(bar)
        
        # Check for new day to reset our data
        current_day = pd.Timestamp(bar.ts_init, tz="UTC").day
        if self.last_day is not None and current_day != self.last_day:
            self.prices.clear()
            self.volumes.clear()
            self.weighted_prices.clear()
        self.last_day = current_day
        
        # Store data for band calculation
        typical_price = (bar.high.as_double() + bar.low.as_double() + bar.close.as_double()) / 3.0
        volume = bar.volume.as_double()
        
        if volume > 0:
            self.prices.append(typical_price)
            self.volumes.append(volume)
            self.weighted_prices.append(typical_price * volume)
    
    def get_bands(self, multiplier=1.0):
        """Get VWAP bands with specified multiplier."""
        if len(self.prices) < 2 or sum(self.volumes) == 0:
            return self.value, None, None
            
        # Calculate volume-weighted variance
        total_volume = sum(self.volumes)
        vwap_value = sum(self.weighted_prices) / total_volume
        
        weighted_variance = sum(
            vol * (price - vwap_value) ** 2 
            for price, vol in zip(self.prices, self.volumes)
        ) / total_volume
        
        std_dev = np.sqrt(weighted_variance)
        upper_band = vwap_value + (multiplier * std_dev)
        lower_band = vwap_value - (multiplier * std_dev)
        
        return self.value, upper_band, lower_band
    
    @property
    def value(self):
        return self.vwap.value
    
    @property
    def initialized(self):
        return self.vwap.initialized
