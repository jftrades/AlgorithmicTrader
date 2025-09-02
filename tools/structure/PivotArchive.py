# PivotArchive.py - Simple pivot point storage using Nautilus Swings as basis
# Stores and sorts significant swing highs and lows for trend/range analysis

from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum

from nautilus_trader.model.data import Bar
from nautilus_trader.indicators.swings import Swings


class PivotType(Enum):
    HIGH = "high"
    LOW = "low"


@dataclass
class Pivot:
    price: float
    timestamp: int
    bar_index: int
    pivot_type: PivotType
    
    @property
    def is_high(self) -> bool:
        return self.pivot_type == PivotType.HIGH
    
    @property
    def is_low(self) -> bool:
        return self.pivot_type == PivotType.LOW


class PivotArchive:
    def __init__(self, max_pivots: int = 100, swing_strength: int = 3):
        self.max_pivots = max_pivots
        self.swing_strength = swing_strength
        
        # Nautilus Swings indicator for pivot detection
        self.swings = Swings(period=swing_strength)
        
        # Pivot storage - chronological order (oldest to newest)
        self.pivots: List[Pivot] = []
        
        # Tracking for duplicate prevention
        self.last_swing_high_price: Optional[float] = None
        self.last_swing_low_price: Optional[float] = None
        
        # Bar counter for indexing
        self.bar_count: int = 0
        
    def update(self, bar: Bar) -> Optional[Pivot]:
        self.bar_count += 1
        
        # Update Nautilus Swings
        self.swings.handle_bar(bar)
        
        if not self.swings.initialized:
            return None
            
        new_pivot = None
        
        # Check for new swing high
        if (self.swings.changed and self.swings.direction == 1 and 
            (not self.last_swing_high_price or self.swings.high_price != self.last_swing_high_price)):
            
            new_pivot = Pivot(
                price=float(self.swings.high_price),
                timestamp=int(bar.ts_event),
                bar_index=self.bar_count,
                pivot_type=PivotType.HIGH
            )
            self.last_swing_high_price = self.swings.high_price
            self._add_pivot(new_pivot)
            
        # Check for new swing low
        elif (self.swings.changed and self.swings.direction == -1 and 
              (not self.last_swing_low_price or self.swings.low_price != self.last_swing_low_price)):
            
            new_pivot = Pivot(
                price=float(self.swings.low_price),
                timestamp=int(bar.ts_event),
                bar_index=self.bar_count,
                pivot_type=PivotType.LOW
            )
            self.last_swing_low_price = self.swings.low_price
            self._add_pivot(new_pivot)
            
        return new_pivot
    
    def _add_pivot(self, pivot: Pivot) -> None:
        self.pivots.append(pivot)
        
        # Keep only the most recent pivots
        if len(self.pivots) > self.max_pivots:
            self.pivots.pop(0)  # Remove oldest
    
    def get_recent_pivots(self, count: int = 10) -> List[Pivot]:
        return self.pivots[-count:] if self.pivots else []
    
    def get_swing_highs(self, count: int = 10) -> List[Pivot]:
        highs = [p for p in self.pivots if p.is_high]
        # Sort by price descending (highest first)
        highs.sort(key=lambda x: x.price, reverse=True)
        return highs[:count]
    
    def get_swing_lows(self, count: int = 10) -> List[Pivot]:
        lows = [p for p in self.pivots if p.is_low]
        # Sort by price ascending (lowest first)
        lows.sort(key=lambda x: x.price)
        return lows[:count]
    
    def get_chronological_highs(self, count: int = 5) -> List[Pivot]:
        highs = [p for p in self.pivots if p.is_high]
        return highs[-count:] if highs else []
    
    def get_chronological_lows(self, count: int = 5) -> List[Pivot]:
        lows = [p for p in self.pivots if p.is_low]
        return lows[-count:] if lows else []
    
    def get_last_swing_high(self) -> Optional[Pivot]:
        highs = self.get_chronological_highs(1)
        return highs[-1] if highs else None
    
    def get_last_swing_low(self) -> Optional[Pivot]:
        lows = self.get_chronological_lows(1)
        return lows[-1] if lows else None
    
    def analyze_trend_from_pivots(self, lookback_pivots: int = 6) -> Tuple[str, float]:
        recent_pivots = self.get_recent_pivots(lookback_pivots)
        
        if len(recent_pivots) < 4:
            return "unknown", 0.0
            
        # Get recent highs and lows in chronological order
        recent_highs = [p for p in recent_pivots if p.is_high]
        recent_lows = [p for p in recent_pivots if p.is_low]
        
        if len(recent_highs) < 2 or len(recent_lows) < 2:
            return "unknown", 0.0
            
        # Compare most recent vs previous
        latest_high = recent_highs[-1]
        previous_high = recent_highs[-2]
        latest_low = recent_lows[-1]
        previous_low = recent_lows[-2]
        
        # Trend analysis
        higher_high = latest_high.price > previous_high.price
        higher_low = latest_low.price > previous_low.price
        lower_high = latest_high.price < previous_high.price
        lower_low = latest_low.price < previous_low.price
        
        if higher_high and higher_low:
            return "uptrend", 1.0
        elif lower_high and lower_low:
            return "downtrend", 1.0
        elif higher_high and lower_low:
            return "sideways", 0.5
        elif lower_high and higher_low:
            return "sideways", 0.5
        else:
            return "unknown", 0.0
    
    def get_key_levels(self) -> dict:
        last_high = self.get_last_swing_high()
        last_low = self.get_last_swing_low()
        
        # Get previous levels
        highs = self.get_chronological_highs(2)
        lows = self.get_chronological_lows(2)
        
        return {
            "last_swing_high": last_high.price if last_high else None,
            "last_swing_low": last_low.price if last_low else None,
            "previous_swing_high": highs[-2].price if len(highs) >= 2 else None,
            "previous_swing_low": lows[-2].price if len(lows) >= 2 else None,
            "total_pivots": len(self.pivots),
            "initialized": self.swings.initialized
        }
    
    def reset(self) -> None:
        self.swings = Swings(period=self.swing_strength)
        self.pivots.clear()
        self.last_swing_high_price = None
        self.last_swing_low_price = None
        self.bar_count = 0