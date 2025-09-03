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


class StructuralState(Enum):
    HIGHER_HIGH = "higher_high"
    LOWER_LOW = "lower_low" 
    HIGHER_LOW = "higher_low"
    LOWER_HIGH = "lower_high"
    INITIAL = "initial"


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


@dataclass
class KeySwing:
    pivot: Pivot
    structural_state: StructuralState
    confirmation_bar: int


class PivotArchive:
    def __init__(self, max_pivots: int = 500, swing_strength: int = 3):
        self.max_pivots = max_pivots
        self.swing_strength = swing_strength
        self.tolerance = 0.001  # 0.1% tolerance for equal levels
        
        # Nautilus Swings indicator for pivot detection
        self.swings = Swings(period=swing_strength)
        
        # ALL pivot storage - chronological order (oldest to newest)
        self.all_pivots: List[Pivot] = []
        
        # KEY swing storage - the basis swings that only update according to your rules
        self.key_swing_high: Optional[Pivot] = None
        self.key_swing_low: Optional[Pivot] = None
        
        # State tracking
        self.last_state: str = "INITIAL"  # "HIGHER_HIGH", "LOWER_LOW", "INITIAL"
        self.price_broke_above_key_high: bool = False
        self.price_broke_below_key_low: bool = False
        
        # Tracking for duplicate prevention
        self.last_swing_high_price: Optional[float] = None
        self.last_swing_low_price: Optional[float] = None
        
        # Bar counter for indexing
        self.bar_count: int = 0
        
    def update(self, bar: Bar) -> Optional[Pivot]:
        self.bar_count += 1
        current_price = float(bar.close)
        
        # Update Nautilus Swings
        self.swings.handle_bar(bar)
        
        if not self.swings.initialized:
            return None
            
        # Track price breaks for confirmation
        if self.key_swing_high and current_price > self.key_swing_high.price:
            self.price_broke_above_key_high = True
        if self.key_swing_low and current_price < self.key_swing_low.price:
            self.price_broke_below_key_low = True
            
        # Check for new swings and add to ALL pivots
        new_pivot = self._detect_new_pivot(bar)
        if new_pivot:
            self._add_to_all_pivots(new_pivot)
            self._update_key_swings_based_on_rules(new_pivot, current_price)
            
        return new_pivot
        
    def _detect_new_pivot(self, bar: Bar) -> Optional[Pivot]:
        new_pivot = None
        
        # Check for new swing high
        if (self.swings.changed and self.swings.direction == 1 and 
            (not self.last_swing_high_price or 
             not self._is_equal(self.swings.high_price, self.last_swing_high_price))):
            
            new_pivot = Pivot(
                price=float(self.swings.high_price),
                timestamp=int(bar.ts_event),
                bar_index=self.bar_count,
                pivot_type=PivotType.HIGH
            )
            self.last_swing_high_price = self.swings.high_price
            
        # Check for new swing low
        elif (self.swings.changed and self.swings.direction == -1 and 
              (not self.last_swing_low_price or 
               not self._is_equal(self.swings.low_price, self.last_swing_low_price))):
            
            new_pivot = Pivot(
                price=float(self.swings.low_price),
                timestamp=int(bar.ts_event),
                bar_index=self.bar_count,
                pivot_type=PivotType.LOW
            )
            self.last_swing_low_price = self.swings.low_price
            
        return new_pivot
    
    def _add_to_all_pivots(self, pivot: Pivot) -> None:
        self.all_pivots.append(pivot)
        if len(self.all_pivots) > self.max_pivots:
            self.all_pivots.pop(0)
    
    def _is_equal(self, price1: float, price2: float) -> bool:
        return abs(price1 - price2) / max(price1, price2) < self.tolerance
    
    def _update_key_swings_based_on_rules(self, new_pivot: Pivot, current_price: float) -> None:
        """
        Update key swings based on your exact rules:
        1. Take first swing high and low as basis
        2. After higher high: only create swing low if we break above that last high OR 
           we made a lower high (but before that, we first had to close below our last lower low)
        3. After lower low: only create swing high if we break below that last low OR 
           we made a higher low (but before that, we first had to close above our last higher high)
        """
        
        # Initialize first key swings
        if not self.key_swing_high and new_pivot.is_high:
            self.key_swing_high = new_pivot
            return
        if not self.key_swing_low and new_pivot.is_low:
            self.key_swing_low = new_pivot
            return
            
        # If we don't have both key swings yet, return
        if not self.key_swing_high or not self.key_swing_low:
            return
        
        # Determine current state based on last key swing
        if self.key_swing_high.bar_index > self.key_swing_low.bar_index:
            current_state = "AFTER_HIGHER_HIGH"
        else:
            current_state = "AFTER_LOWER_LOW"
        
        if new_pivot.is_high:
            self._handle_new_high(new_pivot, current_state)
        else:
            self._handle_new_low(new_pivot, current_state)
    
    def _handle_new_high(self, new_high: Pivot, current_state: str) -> None:
        """Handle a new swing high according to rules"""
        
        if current_state == "AFTER_HIGHER_HIGH":
            # Rule: After higher high, only update swing low if we break above that last high 
            # OR we made a lower high (but before that, we first had to close below our last lower low)
            
            if self.price_broke_above_key_high:
                # We broke above the key high, so this confirms the trend
                # Update the key high to this new higher high
                self.key_swing_high = new_high
                self.last_state = "HIGHER_HIGH"
                self.price_broke_above_key_high = False
                self.price_broke_below_key_low = False
                
            elif (self.price_broke_below_key_low and 
                  new_high.price < self.key_swing_high.price):
                # Lower high after breaking below key low
                self.key_swing_high = new_high
                self.last_state = "LOWER_HIGH"
                self.price_broke_below_key_low = False
                
        elif current_state == "AFTER_LOWER_LOW":
            # After lower low, any higher high is significant
            if new_high.price > self.key_swing_high.price:
                self.key_swing_high = new_high
                self.last_state = "HIGHER_HIGH"
                self.price_broke_above_key_high = False
                self.price_broke_below_key_low = False
    
    def _handle_new_low(self, new_low: Pivot, current_state: str) -> None:
        """Handle a new swing low according to rules"""
        
        if current_state == "AFTER_LOWER_LOW":
            # Rule: After lower low, only update swing high if we break below that last low
            # OR we made a higher low (but before that, we first had to close above our last higher high)
            
            if self.price_broke_below_key_low:
                # We broke below the key low, so this confirms the trend
                # Update the key low to this new lower low
                self.key_swing_low = new_low
                self.last_state = "LOWER_LOW"
                self.price_broke_below_key_low = False
                self.price_broke_above_key_high = False
                
            elif (self.price_broke_above_key_high and 
                  new_low.price > self.key_swing_low.price):
                # Higher low after breaking above key high
                self.key_swing_low = new_low
                self.last_state = "HIGHER_LOW"
                self.price_broke_above_key_high = False
                
        elif current_state == "AFTER_HIGHER_HIGH":
            # After higher high, any lower low is significant
            if new_low.price < self.key_swing_low.price:
                self.key_swing_low = new_low
                self.last_state = "LOWER_LOW"
                self.price_broke_above_key_high = False
                self.price_broke_below_key_low = False
    
    def get_recent_pivots(self, count: int = 10) -> List[Pivot]:
        return self.all_pivots[-count:] if self.all_pivots else []
    
    def get_swing_highs(self, count: int = 10) -> List[Pivot]:
        highs = [p for p in self.all_pivots if p.is_high]
        highs.sort(key=lambda x: x.price, reverse=True)
        return highs[:count]
    
    def get_swing_lows(self, count: int = 10) -> List[Pivot]:
        lows = [p for p in self.all_pivots if p.is_low]
        lows.sort(key=lambda x: x.price)
        return lows[:count]
    
    def get_chronological_highs(self, count: int = 5) -> List[Pivot]:
        highs = [p for p in self.all_pivots if p.is_high]
        return highs[-count:] if highs else []
    
    def get_chronological_lows(self, count: int = 5) -> List[Pivot]:
        lows = [p for p in self.all_pivots if p.is_low]
        return lows[-count:] if lows else []
    
    def get_last_swing_high(self) -> Optional[Pivot]:
        return self.key_swing_high
    
    def get_last_swing_low(self) -> Optional[Pivot]:
        return self.key_swing_low
    
    def analyze_trend_from_pivots(self, lookback_pivots: int = 6) -> Tuple[str, float]:
        if not self.key_swing_high or not self.key_swing_low:
            return "unknown", 0.0
            
        # Use last state for trend analysis
        if self.last_state == "HIGHER_HIGH":
            return "uptrend", 1.0
        elif self.last_state == "LOWER_LOW":
            return "downtrend", 1.0
        elif self.last_state in ["HIGHER_LOW", "LOWER_HIGH"]:
            return "sideways", 0.5
        else:
            return "unknown", 0.0
    
    def get_key_levels(self) -> dict:
        last_high = self.get_last_swing_high()
        last_low = self.get_last_swing_low()
        
        # Get previous key levels from chronological all_pivots
        highs = self.get_chronological_highs(2)
        lows = self.get_chronological_lows(2)
        
        return {
            "last_swing_high": last_high.price if last_high else None,
            "last_swing_low": last_low.price if last_low else None,
            "previous_swing_high": highs[-2].price if len(highs) >= 2 else None,
            "previous_swing_low": lows[-2].price if len(lows) >= 2 else None,
            "total_pivots": len(self.all_pivots),
            "initialized": self.swings.initialized and self.key_swing_high is not None and self.key_swing_low is not None
        }
    
    def reset(self) -> None:
        self.swings = Swings(period=self.swing_strength)
        self.all_pivots.clear()
        self.key_swing_high = None
        self.key_swing_low = None
        self.last_state = "INITIAL"
        self.price_broke_above_key_high = False
        self.price_broke_below_key_low = False
        self.last_swing_high_price = None
        self.last_swing_low_price = None
        self.bar_count = 0