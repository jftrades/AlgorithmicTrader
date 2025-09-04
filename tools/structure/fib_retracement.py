from typing import Optional, List
from dataclasses import dataclass
from tools.structure.PivotArchive import PivotArchive, SwingPoint
from nautilus_trader.model.data import Bar


@dataclass
class FibLevel:
    ratio: float
    price: float
    label: str


@dataclass
class FibRetracement:
    swing_high: SwingPoint
    swing_low: SwingPoint
    levels: List[FibLevel]
    direction: str  # "bullish" or "bearish"
    price_range: float
    
    def get_level_price(self, ratio: float) -> float:
        if self.direction == "bullish":
            # Bullish: measuring retracement from low to high
            return self.swing_low.price + (self.price_range * ratio)
        else:
            # Bearish: measuring retracement from high to low  
            return self.swing_high.price - (self.price_range * ratio)


class FibRetracementTool:
    """
    Ultra-simple Fibonacci tool that ALWAYS uses current critical points.
    Only recalculates when critical points change - provides stable levels.
    """
    
    def __init__(self, pivot_archive: PivotArchive):
        self.pivot_archive = pivot_archive
        self.current_fib: Optional[FibRetracement] = None
        self.last_high_price = None
        self.last_low_price = None
        
        # Standard Fibonacci ratios
        self.fib_ratios = [-1.0, -0.62, -0.27, 0.0, 0.5, 0.618, 0.786, 1.0]
    
    def update(self, bar: Bar) -> Optional[FibRetracement]:
        """
        Update Fibonacci levels. Only recalculates if critical points changed.
        This provides STABLE horizontal levels until 5-step validation triggers.
        """
        high_point = self.pivot_archive.get_last_swing_high()
        low_point = self.pivot_archive.get_last_swing_low()
        
        if not (high_point and low_point):
            return None
        
        # Check if critical points changed
        high_changed = self.last_high_price != high_point.price
        low_changed = self.last_low_price != low_point.price
        
        if high_changed or low_changed or not self.current_fib:
            # Recalculate Fibonacci levels
            self.current_fib = self._calculate_fibonacci(high_point, low_point)
            self.last_high_price = high_point.price
            self.last_low_price = low_point.price
        
        return self.current_fib
    
    def _calculate_fibonacci(self, high_point: SwingPoint, low_point: SwingPoint) -> FibRetracement:
        """Calculate Fibonacci retracement levels"""
        direction, _ = self.pivot_archive.get_direction_with_confidence()
        
        price_range = abs(high_point.price - low_point.price)
        
        # Create Fibonacci levels
        levels = []
        for ratio in self.fib_ratios:
            if direction == "up":
                # Bullish: measuring from low to high
                price = low_point.price + (price_range * ratio)
                levels.append(FibLevel(ratio, price, f"Fib {ratio:.1%}"))
            else:
                # Bearish: measuring from high to low
                price = high_point.price - (price_range * ratio)
                levels.append(FibLevel(ratio, price, f"Fib {ratio:.1%}"))
        
        return FibRetracement(
            swing_high=high_point,
            swing_low=low_point,
            levels=levels,
            direction="bullish" if direction == "up" else "bearish",
            price_range=price_range
        )
    
    def get_current_fibonacci(self) -> Optional[FibRetracement]:
        """Get current Fibonacci retracement (always stable until critical points change)"""
        return self.current_fib
    
    def get_key_levels_for_strategy(self) -> dict:
        """Get key levels for strategy entry logic"""
        if not self.current_fib:
            return {}
        
        # Return the key retracement levels for entries
        levels = {}
        for level in self.current_fib.levels:
            if level.ratio in [0.5, 0.618, 0.786]:  # Key retracement levels
                levels[f"fib_{level.ratio}"] = level.price
        
        return levels
    
    def get_key_levels(self) -> dict:
        """Compatibility method for strategy - returns all Fibonacci levels"""
        if not self.current_fib:
            return {}
        
        levels = {}
        for level in self.current_fib.levels:
            # Convert ratio to string format expected by strategy
            ratio_str = f"{level.ratio:.3f}".replace("-", "neg_").replace(".", "_")
            levels[f"fib_{ratio_str}"] = level.price
        
        return levels
