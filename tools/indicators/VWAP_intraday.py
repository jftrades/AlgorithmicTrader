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
        
        # VWAP extremes tracking state
        self.bars_above_long_band = 0
        self.bars_below_short_band = 0
        self.long_trend_validated = False
        self.short_trend_validated = False
        self.extremes_config = {
            'min_bars_vwap_extremes': 10,
            'min_band_trend_long': 1.0,
            'min_band_trend_short': 1.0
        }
        
    def update(self, bar, is_rth=True):
        """Update VWAP with new bar data."""
        # Let Nautilus VWAP handle daily reset automatically
        self.vwap.handle_bar(bar)
        
        # Check for new day to reset our data
        current_day = pd.Timestamp(bar.ts_init, tz="UTC").day
        if self.last_day is not None and current_day != self.last_day:
            self.prices.clear()
            self.volumes.clear()
            self.weighted_prices.clear()
            # Reset VWAP extremes tracking on new day
            self.reset_extremes_tracking()
        self.last_day = current_day
        
        # Store data for band calculation
        typical_price = (bar.high.as_double() + bar.low.as_double() + bar.close.as_double()) / 3.0
        volume = bar.volume.as_double()
        
        if volume > 0:
            self.prices.append(typical_price)
            self.volumes.append(volume)
            self.weighted_prices.append(typical_price * volume)
        
        # Track VWAP extremes after updating data - ONLY during RTH
        if is_rth:
            self._track_vwap_extremes(bar.close.as_double())
    
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
    
    def configure_extremes(self, min_bars_vwap_extremes: int = 10, 
                          min_band_trend_long: float = 1.0, 
                          min_band_trend_short: float = 1.0):
        """Configure VWAP extremes tracking parameters."""
        self.extremes_config = {
            'min_bars_vwap_extremes': min_bars_vwap_extremes,
            'min_band_trend_long': min_band_trend_long,
            'min_band_trend_short': min_band_trend_short
        }
    
    def reset_extremes_tracking(self):
        """Reset VWAP extremes tracking state."""
        self.bars_above_long_band = 0
        self.bars_below_short_band = 0
        self.long_trend_validated = False
        self.short_trend_validated = False
    
    def _track_vwap_extremes(self, close_price: float):
        """Track consecutive bars above/below VWAP trend bands for trend validation."""
        if not self.initialized:
            return
            
        # Get trend validation bands
        _, upper_band_long, lower_band_long = self.get_bands(self.extremes_config['min_band_trend_long'])
        _, upper_band_short, lower_band_short = self.get_bands(self.extremes_config['min_band_trend_short'])
        
        # Track bars above long trend band (for bullish trend validation)
        if upper_band_long and close_price >= upper_band_long:
            self.bars_above_long_band += 1
            self.bars_below_short_band = 0  # Reset opposite counter
        # Track bars below short trend band (for bearish trend validation)  
        elif lower_band_short and close_price <= lower_band_short:
            self.bars_below_short_band += 1
            self.bars_above_long_band = 0  # Reset opposite counter
        else:
            # Price is between bands - reset both counters
            self.bars_above_long_band = 0
            self.bars_below_short_band = 0
        
        # Validate trends based on minimum bar requirements
        if self.bars_above_long_band >= self.extremes_config['min_bars_vwap_extremes']:
            if not self.long_trend_validated:
                self.long_trend_validated = True
                self.short_trend_validated = False
        
        if self.bars_below_short_band >= self.extremes_config['min_bars_vwap_extremes']:
            if not self.short_trend_validated:
                self.short_trend_validated = True
                self.long_trend_validated = False
    
    def get_trend_validation_status(self):
        """Get current trend validation status."""
        return {
            'long_trend_validated': self.long_trend_validated,
            'short_trend_validated': self.short_trend_validated,
            'bars_above_long_band': self.bars_above_long_band,
            'bars_below_short_band': self.bars_below_short_band
        }
