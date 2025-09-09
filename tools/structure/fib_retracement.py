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
    def __init__(self, pivot_archive: PivotArchive):
        self.pivot_archive = pivot_archive
        self.current_fib: Optional[FibRetracement] = None
        
        # Track last state to detect changes
        self.last_high_price = None
        self.last_low_price = None
        self.last_pivot_state = None
        
        # Standard Fibonacci ratios for trading
        self.fib_ratios = [-1.0, -0.62, -0.27, 0.0, 0.5, 0.618, 0.786, 1.0]
        
        # Track updates for debugging
        self.update_count = 0
        self.last_update_reason = None
    
    def update(self, bar: Bar) -> Optional[FibRetracement]:
        """
        Update Fibonacci levels based on PivotArchive state.
        
        Returns FibRetracement if levels are valid, None if not ready.
        Only recalculates when:
        1. Critical points change (price or timestamp)
        2. PivotArchive state changes
        3. First time initialization
        """
        # Get current critical points from PivotArchive
        key_levels = self.pivot_archive.get_key_levels()
        
        # Must be initialized to calculate Fibonacci
        if not key_levels["initialized"]:
            if self.current_fib:  # Had levels before but now invalid
                self.current_fib = None
                self.last_update_reason = "Waiting for Nautilus swing initialization"
            return None
            
        high_point = self.pivot_archive.get_last_swing_high()
        low_point = self.pivot_archive.get_last_swing_low()
        current_direction, confidence = self.pivot_archive.get_direction_with_confidence()
        
        # Must have both critical points to calculate Fibonacci
        if not (high_point and low_point):
            if self.current_fib:  # Had levels before but now invalid
                self.current_fib = None
                self.last_update_reason = "Critical points missing"
            return None
        
        # Check what changed to decide if recalculation needed
        # For immediate expansion, remove tolerance - every change should trigger update
        price_tolerance = 0.0  # No tolerance - immediate response to any change
        
        high_changed = (self.last_high_price is None or 
                       abs(self.last_high_price - high_point.price) > price_tolerance)
        low_changed = (self.last_low_price is None or 
                      abs(self.last_low_price - low_point.price) > price_tolerance)
        direction_changed = self.last_pivot_state != current_direction
        first_time = not self.current_fib
        
        # Only recalculate if there's a meaningful change
        if high_changed or low_changed or direction_changed or first_time:
            # Recalculate Fibonacci levels
            self.current_fib = self._calculate_fibonacci_levels(high_point, low_point, current_direction)
            
            # Update tracking variables
            self.last_high_price = high_point.price
            self.last_low_price = low_point.price
            self.last_pivot_state = current_direction
            self.update_count += 1
            
            # Log update reason for transparency
            reasons = []
            if high_changed:
                reasons.append("high changed")
            if low_changed:
                reasons.append("low changed") 
            if direction_changed:
                reasons.append(f"direction: {current_direction}")
            if first_time:
                reasons.append("initialization")
            self.last_update_reason = " + ".join(reasons)
        
        return self.current_fib
    
    def _calculate_fibonacci_levels(self, high_point: SwingPoint, low_point: SwingPoint, pivot_direction: str) -> FibRetracement:
        """Calculate Fibonacci retracement levels with state-aware direction"""
        
        # Get direction and confidence from PivotArchive
        direction, confidence = self.pivot_archive.get_direction_with_confidence()
        
        # Calculate price range for Fibonacci levels
        price_range = abs(high_point.price - low_point.price)
        
        # Generate all Fibonacci levels
        levels = []
        for ratio in self.fib_ratios:
            if direction == "up":
                # UPTREND: Fibonacci 0 at LOW (start of move), 100% at HIGH (end of move)
                # This means retracement measured from high back down toward low
                price = high_point.price - (price_range * ratio)
                levels.append(FibLevel(ratio, price, f"Fib {ratio:.1%}"))
            else:
                # DOWNTREND: Fibonacci 0 at HIGH (start of move), 100% at LOW (end of move)  
                # This means retracement measured from low back up toward high
                price = low_point.price + (price_range * ratio)
                levels.append(FibLevel(ratio, price, f"Fib {ratio:.1%}"))
        
        # Determine final direction string for FibRetracement
        fib_direction = "bullish" if direction == "up" else "bearish"
        
        return FibRetracement(
            swing_high=high_point,
            swing_low=low_point,
            levels=levels,
            direction=fib_direction,
            price_range=price_range
        )
    
    def get_current_fibonacci(self) -> Optional[FibRetracement]:
        """Get current Fibonacci retracement (stable until PivotArchive changes)"""
        return self.current_fib
    
    def get_key_levels_for_strategy(self) -> dict:
        """Get key retracement levels for strategy entry logic"""
        if not self.current_fib:
            return {}
        
        # Return only the most important retracement levels
        key_levels = {}
        for level in self.current_fib.levels:
            if level.ratio in [0.5, 0.618, 0.786]:  # Golden ratios for entries
                key_levels[f"fib_{level.ratio}"] = level.price
        
        return key_levels
    
    def get_key_levels(self) -> dict:
        """Compatibility method for strategy - returns all Fibonacci levels"""
        if not self.current_fib:
            return {}
        
        # Convert all levels to strategy-compatible format
        all_levels = {}
        for level in self.current_fib.levels:
            # Convert ratio to string format expected by strategy visualization
            ratio_str = f"{level.ratio:.3f}".replace("-", "neg_").replace(".", "_")
            all_levels[f"fib_{ratio_str}"] = level.price
        
        return all_levels
    
    def get_entry_levels_by_direction(self, current_price: float) -> dict:
        if not self.current_fib:
            return {"long_entries": {}, "short_entries": {}, "direction": "unknown"}
        
        direction, confidence = self.pivot_archive.get_direction_with_confidence()
        
        long_entries = {}
        short_entries = {}
        
        # Get key retracement levels for entries
        for level in self.current_fib.levels:
            if level.ratio in [0.5, 0.618, 0.786]:  # Key retracement ratios
                if level.price < current_price:
                    long_entries[f"fib_{level.ratio}"] = level.price
                elif level.price > current_price:
                    short_entries[f"fib_{level.ratio}"] = level.price
        
        return {
            "long_entries": long_entries,
            "short_entries": short_entries, 
            "direction": direction,
            "confidence": confidence
        }
    
    def is_price_near_fibonacci_level(self, current_price: float, target_ratio: float, tolerance_pct: float = 0.5) -> bool:
        """
        Check if current price is near a specific Fibonacci level.
        
        Args:
            current_price: Current market price
            target_ratio: Target Fibonacci ratio (e.g., 0.618)
            tolerance_pct: Tolerance percentage (default 0.5%)
            
        Returns:
            True if price is within tolerance of the Fibonacci level
        """
        if not self.current_fib:
            return False
        
        # Find the target Fibonacci level
        target_level = None
        for level in self.current_fib.levels:
            if abs(level.ratio - target_ratio) < 0.001:  # Small tolerance for float comparison
                target_level = level
                break
        
        if not target_level:
            return False
        
        # Check if current price is within tolerance
        tolerance_amount = abs(target_level.price * tolerance_pct / 100)
        return abs(current_price - target_level.price) <= tolerance_amount
    
    def get_debug_info(self) -> dict:
        key_levels = self.pivot_archive.get_key_levels()
        
        debug_info = {
            "pivot_archive_initialized": key_levels["initialized"],
            "nautilus_initialized": key_levels.get("nautilus_initialized", False),
            "critical_highs_count": key_levels["critical_highs_count"],
            "critical_lows_count": key_levels["critical_lows_count"],
            "highest_high": key_levels.get("highest_high"),
            "lowest_low": key_levels.get("lowest_low"),
            "last_swing_high": key_levels.get("last_swing_high"),
            "last_swing_low": key_levels.get("last_swing_low"),
            "total_highs_tracked": key_levels.get("total_highs_tracked", 0),
            "total_lows_tracked": key_levels.get("total_lows_tracked", 0),
            "fib_tool_ready": self.current_fib is not None,
            "update_count": self.update_count,
            "last_update_reason": self.last_update_reason
        }
        
        if self.current_fib:
            debug_info.update({
                "fib_direction": self.current_fib.direction,
                "fib_range": self.current_fib.price_range,
                "fib_levels_count": len(self.current_fib.levels)
            })
        
        return debug_info
    
    def get_fibonacci_status(self) -> dict:
        """
        Get comprehensive status of Fibonacci tool for debugging and strategy use.
        
        Returns dict with current state, update info, and level summary.
        """
        if not self.current_fib:
            return {
                "status": "not_ready",
                "reason": "No Fibonacci levels calculated",
                "pivot_direction": self.pivot_archive.get_direction_with_confidence()[0]
            }
        
        return {
            "status": "ready",
            "direction": self.current_fib.direction,
            "high_price": self.current_fib.swing_high.price,
            "low_price": self.current_fib.swing_low.price,
            "price_range": self.current_fib.price_range,
            "level_count": len(self.current_fib.levels),
            "update_count": self.update_count,
            "last_update_reason": self.last_update_reason,
            "pivot_direction": self.pivot_archive.get_direction_with_confidence()[0],
            "pivot_confidence": self.pivot_archive.get_direction_with_confidence()[1]
        }
