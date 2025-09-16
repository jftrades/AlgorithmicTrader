
from dataclasses import dataclass
from typing import Optional, List
from nautilus_trader.model.data import Bar
from nautilus_trader.indicators.swings import Swings


@dataclass
class SwingPoint:
    price: float
    timestamp: int
    is_high: bool


class PivotArchive:
    def __init__(self, strength: int = 5):
        self.swings = Swings(period=strength)
        self.last_high_value = None
        self.last_low_value = None
        
        # Critical points (max 3 each) - our main anchoring points
        self.critical_highs: List[SwingPoint] = []
        self.critical_lows: List[SwingPoint] = []
        
        # Store last 300 highs and lows for finding most extreme points
        self.all_highs: List[SwingPoint] = []
        self.all_lows: List[SwingPoint] = []
        
        # Track current running extremes
        self.highest_high = None
        self.lowest_low = None
        
        self.ema_reset = None
        
        # Trending readjustment tracking
        self.below_ema_lows: List[SwingPoint] = []  # Lows made below EMA in uptrend
        self.above_ema_highs: List[SwingPoint] = []  # Highs made above EMA in downtrend
        
        self.initialized = False
        self.nautilus_initialized = False 
    
    def set_ema_reset(self, ema_value: float):
        self.ema_reset = ema_value 
    
    def update(self, bar: Bar) -> bool:
        # Always feed Nautilus for initial swing detection
        self.swings.handle_bar(bar)
        
        # Store EVERY high and low from this candle for our own tracking
        bar_high = float(bar.high)
        bar_low = float(bar.low)
        timestamp = int(bar.ts_event)
        
        # Add to our complete records (keep last 300)
        high_point = SwingPoint(bar_high, timestamp, True)
        low_point = SwingPoint(bar_low, timestamp, False)
        self.all_highs.append(high_point)
        self.all_lows.append(low_point)
        if len(self.all_highs) > 300:
            self.all_highs.pop(0)
        if len(self.all_lows) > 300:
            self.all_lows.pop(0)
        
        # Phase 1: Try to get initial critical points from Nautilus swings
        if not self.nautilus_initialized:
            if self._initialize_from_nautilus_swings(bar):
                return True 
            return False
        
        # Phase 2: Extreme tracking with trending readjustment
        changed = False
        current_direction, _ = self.get_direction_with_confidence()
        
        # Track EMA-based lows/highs for trending readjustment
        if self.ema_reset is not None:
            if current_direction == "up" and bar_low < self.ema_reset:
                # In uptrend: Track lows below EMA
                self.below_ema_lows.append(low_point)
            elif current_direction == "down" and bar_high > self.ema_reset:
                # In downtrend: Track highs above EMA
                self.above_ema_highs.append(high_point)
        
        # Simple rule: If this bar's high is higher than critical high, update it
        if bar_high > self.critical_highs[-1].price:
            old_critical_high = self.critical_highs[-1]
            self._add_critical_high(high_point)
            self.highest_high = bar_high
            changed = True
            
            # Trending readjustment for uptrend: Find lowest point in timespan
            if current_direction == "up" and self.below_ema_lows:
                lowest_in_timespan = self._find_lowest_in_timespan(
                    old_critical_high.timestamp, timestamp)
                if lowest_in_timespan:
                    self._add_critical_low(lowest_in_timespan)
                    self.below_ema_lows.clear()  # Clear after using
            
        # Simple rule: If this bar's low is lower than critical low, update it
        if bar_low < self.critical_lows[-1].price:
            old_critical_low = self.critical_lows[-1]
            self._add_critical_low(low_point)
            self.lowest_low = bar_low
            changed = True
            
            # Trending readjustment for downtrend: Find highest point in timespan
            if current_direction == "down" and self.above_ema_highs:
                highest_in_timespan = self._find_highest_in_timespan(
                    old_critical_low.timestamp, timestamp)
                if highest_in_timespan:
                    self._add_critical_high(highest_in_timespan)
                    self.above_ema_highs.clear()  # Clear after using
        
        # Update running extremes
        if self.highest_high is None or bar_high > self.highest_high:
            self.highest_high = bar_high
        if self.lowest_low is None or bar_low < self.lowest_low:
            self.lowest_low = bar_low
        
        return changed
    
    def _initialize_from_nautilus_swings(self, bar: Bar) -> bool:
        new_swing = self._get_new_swing(bar)
        if new_swing:
            if new_swing.is_high and len(self.critical_highs) == 0:
                self.critical_highs.append(new_swing)
                self.highest_high = new_swing.price
                # Check if we have both high and low now
                if len(self.critical_lows) > 0:
                    self.nautilus_initialized = True
                    self.initialized = True
                return True
            elif not new_swing.is_high and len(self.critical_lows) == 0:
                self.critical_lows.append(new_swing)
                self.lowest_low = new_swing.price
                # Check if we have both high and low now
                if len(self.critical_highs) > 0:
                    self.nautilus_initialized = True
                    self.initialized = True
                return True
        return False

    def _get_new_swing(self, bar: Bar) -> Optional[SwingPoint]:
        if (self.swings.changed and self.swings.direction == 1 and 
            self.last_high_value != self.swings.high_price):
            self.last_high_value = self.swings.high_price
            return SwingPoint(float(self.swings.high_price), int(bar.ts_event), True)
            
        # Check for new swing low  
        elif (self.swings.changed and self.swings.direction == -1 and 
              self.last_low_value != self.swings.low_price):
            self.last_low_value = self.swings.low_price
            return SwingPoint(float(self.swings.low_price), int(bar.ts_event), False)
        
        return None

    def _find_lowest_in_timespan(self, start_time: int, end_time: int) -> Optional[SwingPoint]:
        candidates = [low for low in self.all_lows if start_time <= low.timestamp <= end_time]
        if not candidates:
            return None
        return min(candidates, key=lambda x: x.price)

    def _find_highest_in_timespan(self, start_time: int, end_time: int) -> Optional[SwingPoint]:
        candidates = [high for high in self.all_highs if start_time <= high.timestamp <= end_time]
        if not candidates:
            return None
        return max(candidates, key=lambda x: x.price)

    def _add_critical_high(self, swing: SwingPoint) -> None: # max 3
        self.critical_highs.append(swing)
        if len(self.critical_highs) > 3:
            self.critical_highs.pop(0)

    def _add_critical_low(self, swing: SwingPoint) -> None:
        self.critical_lows.append(swing)
        if len(self.critical_lows) > 3:
            self.critical_lows.pop(0)
    
    def get_last_swing_high(self) -> Optional[SwingPoint]:
        return self.critical_highs[-1] if self.critical_highs else None
    
    def get_last_swing_low(self) -> Optional[SwingPoint]:
        return self.critical_lows[-1] if self.critical_lows else None
    
    def get_direction_with_confidence(self):
        if not self.critical_highs or not self.critical_lows:
            return "unknown", 0.0
        
        last_high = self.critical_highs[-1]
        last_low = self.critical_lows[-1]
        
        if last_high.timestamp > last_low.timestamp:
            return "up", 1.0
        else:
            return "down", 1.0
    
    def get_key_levels(self) -> dict:
        return {
            "last_swing_high": self.critical_highs[-1].price if self.critical_highs else None,
            "last_swing_low": self.critical_lows[-1].price if self.critical_lows else None,
            "highest_high": self.highest_high,
            "lowest_low": self.lowest_low,
            "initialized": self.initialized,
            "nautilus_initialized": self.nautilus_initialized,
            "critical_highs_count": len(self.critical_highs),
            "critical_lows_count": len(self.critical_lows),
            "total_highs_tracked": len(self.all_highs),
            "total_lows_tracked": len(self.all_lows)
        }
    
    def reset(self) -> None:
        self.swings = Swings(period=5)  # Reset Nautilus for new initialization
        self.last_high_value = None
        self.last_low_value = None
        self.critical_highs.clear()
        self.critical_lows.clear()
        self.all_highs.clear()
        self.all_lows.clear()
        self.below_ema_lows.clear()
        self.above_ema_highs.clear()
        self.ema_reset = None
        self.highest_high = None
        self.lowest_low = None
        self.initialized = False
        self.nautilus_initialized = False
