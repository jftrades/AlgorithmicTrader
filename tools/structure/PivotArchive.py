
from dataclasses import dataclass
from typing import Optional, List
from nautilus_trader.model.data import Bar
from nautilus_trader.indicators.swings import Swings


@dataclass
class SwingPoint:
    """Simple price point with timestamp"""
    price: float
    timestamp: int
    is_high: bool


class PivotArchive:
    """
    Pure High/Low Fibonacci Archive:
    1. Use Nautilus Swings for INITIAL critical high and low only
    2. After initialization: Compare EVERY bar's high to critical_high, low to critical_low
    3. If bar.high > critical_high: Update critical_high immediately
    4. If bar.low < critical_low: Update critical_low immediately  
    5. No bar.close logic, no patterns - just pure high/low extremes
    """
    
    def __init__(self, strength: int = 5):
        # Use Nautilus ONLY for initial swing detection
        self.swings = Swings(period=strength)
        
        # Track last swing values to detect new ones
        self.last_high_value = None
        self.last_low_value = None
        
        # Critical points (max 3 each) - our main anchoring points
        self.critical_highs: List[SwingPoint] = []
        self.critical_lows: List[SwingPoint] = []
        
        # Store ALL highs and lows for finding most extreme points
        self.all_highs: List[SwingPoint] = []
        self.all_lows: List[SwingPoint] = []
        
        # Track current running extremes
        self.highest_high = None
        self.lowest_low = None
        
        # Initialization flags
        self.initialized = False
        self.nautilus_initialized = False  # Track if we got initial swings from Nautilus
    
    def update(self, bar: Bar) -> bool:
        """
        Hybrid update: Use Nautilus for initial points, then our own logic.
        Returns True if critical points changed.
        """
        # Always feed Nautilus for initial swing detection
        self.swings.handle_bar(bar)
        
        # Store EVERY high and low from this candle for our own tracking
        bar_high = float(bar.high)
        bar_low = float(bar.low)
        timestamp = int(bar.ts_event)
        
        # Add to our complete records
        high_point = SwingPoint(bar_high, timestamp, True)
        low_point = SwingPoint(bar_low, timestamp, False)
        self.all_highs.append(high_point)
        self.all_lows.append(low_point)
        
        # Phase 1: Try to get initial critical points from Nautilus swings
        if not self.nautilus_initialized:
            if self._initialize_from_nautilus_swings(bar):
                return True  # We got initial points from Nautilus
            # Wait for Nautilus to provide swings - no fallback
            return False
        
        # Phase 2: Ultra-simple extreme tracking - only bar.high/bar.low comparison
        changed = False
        
        # Simple rule: If this bar's high is higher than critical high, update it
        if bar_high > self.critical_highs[-1].price:
            self._add_critical_high(high_point)
            self.highest_high = bar_high
            changed = True
            
        # Simple rule: If this bar's low is lower than critical low, update it
        if bar_low < self.critical_lows[-1].price:
            self._add_critical_low(low_point)
            self.lowest_low = bar_low
            changed = True
        
        # Update running extremes
        if self.highest_high is None or bar_high > self.highest_high:
            self.highest_high = bar_high
        if self.lowest_low is None or bar_low < self.lowest_low:
            self.lowest_low = bar_low
        
        return changed
    
    def _initialize_from_nautilus_swings(self, bar: Bar) -> bool:
        """Initialize critical points from first Nautilus swings"""
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
        """Check for new swing from Nautilus"""
        # Check for new swing high
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

    def _add_critical_high(self, swing: SwingPoint) -> None:
        """Add critical high (max 3)"""
        self.critical_highs.append(swing)
        if len(self.critical_highs) > 3:
            self.critical_highs.pop(0)

    def _add_critical_low(self, swing: SwingPoint) -> None:
        """Add critical low (max 3)"""
        self.critical_lows.append(swing)
        if len(self.critical_lows) > 3:
            self.critical_lows.pop(0)
    
    # Simple interface methods for Fibonacci tool and strategy
    def get_last_swing_high(self) -> Optional[SwingPoint]:
        """Get current critical high"""
        return self.critical_highs[-1] if self.critical_highs else None
    
    def get_last_swing_low(self) -> Optional[SwingPoint]:
        """Get current critical low"""
        return self.critical_lows[-1] if self.critical_lows else None
    
    def get_direction_with_confidence(self):
        """Get direction based on most recent critical point"""
        if not self.critical_highs or not self.critical_lows:
            return "unknown", 0.0
        
        last_high = self.critical_highs[-1]
        last_low = self.critical_lows[-1]
        
        if last_high.timestamp > last_low.timestamp:
            return "up", 1.0
        else:
            return "down", 1.0
    
    def get_key_levels(self) -> dict:
        """Get key levels for strategy use"""
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
        """Reset the archive"""
        self.swings = Swings(period=5)  # Reset Nautilus for new initialization
        self.last_high_value = None
        self.last_low_value = None
        self.critical_highs.clear()
        self.critical_lows.clear()
        self.all_highs.clear()
        self.all_lows.clear()
        self.highest_high = None
        self.lowest_low = None
        self.initialized = False
        self.nautilus_initialized = False
