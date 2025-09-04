# PivotArchive.py - Ultra-Simple Fibonacci Archive with 5-Step Validation
# ALWAYS maintains ONE critical high and ONE critical low for stable Fibonacci levels

from dataclasses import dataclass
from typing import Optional
from nautilus_trader.model.data import Bar
from nautilus_trader.indicators.swings import Swings


@dataclass
class SwingPoint:
    """Simple swing point from Nautilus"""
    price: float
    timestamp: int
    is_high: bool


class PivotArchive:
    """
    Ultra-simplified archive maintaining EXACTLY 2 critical points:
    - ONE critical high
    - ONE critical low
    
    5-step validation ONLY updates these when strict conditions are met.
    Fibonacci tool ALWAYS has stable anchor points.
    """
    
    def __init__(self, lookback_swings: int = 250, strength: int = 5):
        # Nautilus swings - our only swing source
        self.swings = Swings(period=strength)
        
        # THE TWO CRITICAL POINTS - always available for Fibonacci
        self.critical_high: Optional[SwingPoint] = None
        self.critical_low: Optional[SwingPoint] = None
        
        # Simple state tracking
        self.last_high_value = None
        self.last_low_value = None
        self.swing_sequence = []  # Recent swings for validation
        self.max_sequence_length = 20  # Keep validation simple
    
    def update(self, bar: Bar) -> bool:
        """
        Update with new bar. 
        Returns True if critical points changed (Fibonacci needs recalculation)
        """
        # Update Nautilus swings
        self.swings.handle_bar(bar)
        
        if not self.swings.initialized:
            return False
        
        # Check for new swings from Nautilus
        new_swing_detected = False
        
        # New high detected
        if (self.swings.changed and self.swings.direction == 1 and 
            self.last_high_value != self.swings.high_price):
            
            new_high = SwingPoint(
                price=float(self.swings.high_price),
                timestamp=int(bar.ts_event),
                is_high=True
            )
            self._process_new_swing(new_high)
            self.last_high_value = self.swings.high_price
            new_swing_detected = True
            
        # New low detected  
        elif (self.swings.changed and self.swings.direction == -1 and 
              self.last_low_value != self.swings.low_price):
            
            new_low = SwingPoint(
                price=float(self.swings.low_price),
                timestamp=int(bar.ts_event),
                is_high=False
            )
            self._process_new_swing(new_low)
            self.last_low_value = self.swings.low_price
            new_swing_detected = True
        
        return new_swing_detected
    
    def _process_new_swing(self, swing: SwingPoint) -> None:
        """Process new swing and apply 5-step validation"""
        
        # Add to sequence for validation
        self.swing_sequence.append(swing)
        if len(self.swing_sequence) > self.max_sequence_length:
            self.swing_sequence.pop(0)
        
        # Initialize critical points if not set
        if swing.is_high and not self.critical_high:
            self.critical_high = swing
            return
        if not swing.is_high and not self.critical_low:
            self.critical_low = swing
            return
            
        # Both critical points must exist for validation
        if not (self.critical_high and self.critical_low):
            return
        
        # Apply 5-step validation
        if swing.is_high:
            self._check_bullish_update(swing)
        else:
            self._check_bearish_update(swing)
    
    def _check_bullish_update(self, new_high: SwingPoint) -> None:
        """
        5-step bullish validation:
        1. New high breaks above critical high
        2. Sequence of lows after critical high were progressively lower
        3. No intermediate breaks of critical low
        4. If all met -> update critical_low to most extreme low in sequence
        """
        if new_high.price <= self.critical_high.price:
            return  # No break above critical high
        
        # Get lows after current critical high
        critical_high_time = self.critical_high.timestamp
        lows_after_high = [s for s in self.swing_sequence 
                          if not s.is_high and s.timestamp > critical_high_time]
        
        if len(lows_after_high) < 1:
            return  # Need at least 1 low after high
        
        # Check progressively lower + no critical low breaks
        if self._are_lows_progressively_lower(lows_after_high):
            # SUCCESS! Update critical points
            extreme_low = min(lows_after_high, key=lambda x: x.price)
            self.critical_high = new_high
            self.critical_low = extreme_low
    
    def _check_bearish_update(self, new_low: SwingPoint) -> None:
        """
        5-step bearish validation:
        1. New low breaks below critical low  
        2. Sequence of highs after critical low were progressively higher
        3. No intermediate breaks of critical high
        4. If all met -> update critical_high to most extreme high in sequence
        """
        if new_low.price >= self.critical_low.price:
            return  # No break below critical low
        
        # Get highs after current critical low
        critical_low_time = self.critical_low.timestamp
        highs_after_low = [s for s in self.swing_sequence 
                          if s.is_high and s.timestamp > critical_low_time]
        
        if len(highs_after_low) < 1:
            return  # Need at least 1 high after low
        
        # Check progressively higher + no critical high breaks  
        if self._are_highs_progressively_higher(highs_after_low):
            # SUCCESS! Update critical points
            extreme_high = max(highs_after_low, key=lambda x: x.price)
            self.critical_high = extreme_high
            self.critical_low = new_low
    
    def _are_lows_progressively_lower(self, lows) -> bool:
        """Check if lows are progressively lower (with small tolerance)"""
        if len(lows) < 2:
            return True
            
        # Also check no critical low breaks
        for low in lows:
            if low.price < self.critical_low.price * 0.999:  # Small tolerance
                return False  # Critical low broken
        
        # Check progressive lowering
        sorted_lows = sorted(lows, key=lambda x: x.timestamp)
        for i in range(1, len(sorted_lows)):
            if sorted_lows[i].price > sorted_lows[i-1].price * 1.001:  # Small tolerance
                return False
        return True
    
    def _are_highs_progressively_higher(self, highs) -> bool:
        """Check if highs are progressively higher (with small tolerance)"""
        if len(highs) < 2:
            return True
            
        # Also check no critical high breaks
        for high in highs:
            if high.price > self.critical_high.price * 1.001:  # Small tolerance  
                return False  # Critical high broken
        
        # Check progressive elevation
        sorted_highs = sorted(highs, key=lambda x: x.timestamp)
        for i in range(1, len(sorted_highs)):
            if sorted_highs[i].price < sorted_highs[i-1].price * 0.999:  # Small tolerance
                return False
        return True
    
    # Simple interface methods for Fibonacci tool and strategy
    def get_last_swing_high(self) -> Optional[SwingPoint]:
        """Get critical high for Fibonacci calculation (always available)"""
        return self.critical_high
    
    def get_last_swing_low(self) -> Optional[SwingPoint]:
        """Get critical low for Fibonacci calculation (always available)"""
        return self.critical_low
    
    def get_direction_with_confidence(self):
        """Get direction for Fibonacci calculation"""
        if self.critical_high and self.critical_low:
            if self.critical_high.timestamp > self.critical_low.timestamp:
                return "up", 1.0  # High is more recent = bullish
            else:
                return "down", 1.0  # Low is more recent = bearish
        return "unknown", 0.0
    
    def get_key_levels(self) -> dict:
        """Get key levels for strategy use"""
        return {
            "last_swing_high": self.critical_high.price if self.critical_high else None,
            "last_swing_low": self.critical_low.price if self.critical_low else None,
            "total_swings": len(self.swing_sequence),
            "initialized": self.swings.initialized and self.critical_high is not None and self.critical_low is not None
        }
    
    def reset(self) -> None:
        """Reset the archive"""
        self.swings = Swings(period=5)
        self.swing_sequence.clear()
        self.critical_high = None
        self.critical_low = None
        self.last_high_value = None
        self.last_low_value = None
