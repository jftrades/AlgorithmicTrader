
from dataclasses import dataclass
from typing import Optional, List
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
    Fibonacci Archive with 0.3 retracement qualification:
    
    1. Use first swing high + low from Nautilus as initial critical points
    2. In uptrends: expand critical high, protect critical low
    3. Swing lows need 0.3+ retracement to qualify for waiting list
    4. Wait for close above last critical high OR close below last critical low
    5. Find most extreme swing in time window between bar and last critical point
    
    Rolling buffer system: max 3 critical highs/lows
    """
    
    def __init__(self, strength: int = 5):
        # Nautilus swings - our only swing source
        self.swings = Swings(period=strength)
        
        # State machine for clean logic flow
        self.state = "COLLECTING_INITIAL"  # COLLECTING_INITIAL -> UPTREND_MODE/DOWNTREND_MODE
        
        # Store last 3 critical highs and lows (rolling buffer)
        self.critical_highs: List[SwingPoint] = []  # Max 3 items
        self.critical_lows: List[SwingPoint] = []   # Max 3 items
        
        # Store all swing points for retrospective analysis
        self.all_swing_points: List[SwingPoint] = []
        
        # Waiting list for qualified retracements (0.3+ retracement depth)
        self.qualified_retracements: List[SwingPoint] = []
        
        # Swing tracking from Nautilus
        self.last_high_value = None
        self.last_low_value = None
        
        # 30% retracement threshold for qualification
        self.retracement_threshold = 0.3
        
        # For debugging and transparency
        self.state_changes = []
    
    def update(self, bar: Bar) -> bool:
        """
        Main update method - processes new bar through state machine.
        Returns True if critical points changed (Fibonacci needs recalculation).
        """
        # Update Nautilus swings first
        self.swings.handle_bar(bar)
        
        if not self.swings.initialized:
            return False
        
        # Check for new swings from Nautilus
        new_swing = self._detect_new_swing_from_nautilus(bar)
        
        if new_swing:
            # Process new swing through our state machine
            return self._process_swing_through_state_machine(new_swing, bar)
        
        # Even without new swings, check for trend decisions based on bar close
        self._check_trend_decision(bar)
        return False
    
    def _detect_new_swing_from_nautilus(self, bar: Bar) -> Optional[SwingPoint]:
        """Get new swing points directly from Nautilus indicator"""
        
        # Check for new swing high
        if (self.swings.changed and self.swings.direction == 1 and 
            self.last_high_value != self.swings.high_price):
            
            self.last_high_value = self.swings.high_price
            swing_point = SwingPoint(
                price=float(self.swings.high_price),
                timestamp=int(bar.ts_event),
                is_high=True
            )
            # Store all swing points for retrospective analysis
            self.all_swing_points.append(swing_point)
            return swing_point
            
        # Check for new swing low  
        elif (self.swings.changed and self.swings.direction == -1 and 
              self.last_low_value != self.swings.low_price):
            
            self.last_low_value = self.swings.low_price
            swing_point = SwingPoint(
                price=float(self.swings.low_price),
                timestamp=int(bar.ts_event),
                is_high=False
            )
            # Store all swing points for retrospective analysis
            self.all_swing_points.append(swing_point)
            return swing_point
        
        return None
    
    def _process_swing_through_state_machine(self, swing: SwingPoint, bar: Bar) -> bool:
        """Process new swing through our simplified state machine"""
        
        if self.state == "COLLECTING_INITIAL":
            return self._collect_initial_points(swing)
            
        elif self.state == "UPTREND_MODE":
            return self._handle_uptrend_logic(swing, bar)
            
        elif self.state == "DOWNTREND_MODE":
            return self._handle_downtrend_logic(swing, bar)
        
        return False
    
    def _collect_initial_points(self, swing: SwingPoint) -> bool:
        """Collect first swing high and low from Nautilus as initial critical points"""
        
        if swing.is_high and len(self.critical_highs) == 0:
            self.critical_highs.append(swing)
            self._log_state_change(f"Initial critical high: {swing.price:.5f}")
            
        elif not swing.is_high and len(self.critical_lows) == 0:
            self.critical_lows.append(swing)
            self._log_state_change(f"Initial critical low: {swing.price:.5f}")
        
        # Once we have both, determine initial trend direction
        if len(self.critical_highs) > 0 and len(self.critical_lows) > 0:
            # Determine trend based on which critical point is more recent
            last_high = self.critical_highs[-1]
            last_low = self.critical_lows[-1]
            
            if last_high.timestamp > last_low.timestamp:
                self.state = "UPTREND_MODE"
                self._log_state_change("Initial uptrend detected")
            else:
                self.state = "DOWNTREND_MODE" 
                self._log_state_change("Initial downtrend detected")
            
            return True  # Critical points changed
        
        return len(self.critical_highs) > 0 and len(self.critical_lows) > 0  # Return True if we have both for Fibonacci
    
    def _handle_break_detection(self, swing: SwingPoint, bar: Bar) -> bool:
        """State 2: Wait for price break above current high OR below current low"""
        
        current_price = float(bar.close)
        current_high = self.critical_highs[-1].price
        current_low = self.critical_lows[-1].price
        
        # Check for break above current high (start uptrend)
        if current_price > current_high:
            self.state = "UPTREND_MODE"
            
            # Create break point at the exact bar.close that broke the level
            break_point = SwingPoint(
                price=current_price,
                timestamp=int(bar.ts_event),
                is_high=True  # This break point represents the new trend high
            )
            
            # Add to critical highs buffer (rolling)
            self._add_critical_high(break_point)
            
            self._log_state_change(f"UPTREND started - price {current_price:.5f} > critical high {current_high:.5f} | New critical high added")
            return True  # Critical points changed
            
        # Check for break below current low (start downtrend)  
        elif current_price < current_low:
            self.state = "DOWNTREND_MODE"
            
            # Create break point at the exact bar.close that broke the level  
            break_point = SwingPoint(
                price=current_price,
                timestamp=int(bar.ts_event),
                is_high=False  # This break point represents the new trend low
            )
            
            # Add to critical lows buffer (rolling)
            self._add_critical_low(break_point)
            
            self._log_state_change(f"DOWNTREND started - price {current_price:.5f} < critical low {current_low:.5f} | New critical low added")
            return True  # Critical points changed
        
        return False  # No state change
    
    def _add_critical_high(self, swing_high: SwingPoint) -> None:
        """Add critical high to rolling buffer (max 3 items)"""
        self.critical_highs.append(swing_high)
        if len(self.critical_highs) > 3:
            self.critical_highs.pop(0)  # Remove oldest
    
    def _add_critical_low(self, swing_low: SwingPoint) -> None:
        """Add critical low to rolling buffer (max 3 items)"""
        self.critical_lows.append(swing_low)
        if len(self.critical_lows) > 3:
            self.critical_lows.pop(0)  # Remove oldest
    
    def _handle_uptrend_logic(self, swing: SwingPoint, bar: Bar) -> bool:
        """
        Uptrend mode with 0.3 retracement qualification:
        1. Higher highs -> expand critical high (expand fib)
        2. Swing lows need 0.3+ retracement to qualify for waiting list
        3. Wait for close above last critical high OR close below last critical low
        4. If close above critical high: find most extreme swing low between bar and last critical high
        """
        
        critical_points_changed = False
        
        if swing.is_high:
            # Higher high -> expand critical high and fib
            current_high = self.critical_highs[-1].price
            if swing.price > current_high:
                self._add_critical_high(swing)
                critical_points_changed = True
                self._log_state_change(f"Critical high expanded: {swing.price:.5f} (fib expanding)")
                    
        else:
            # Swing low - check if it qualifies for 0.3+ retracement
            if self._qualifies_for_retracement(swing, is_uptrend=True):
                self.qualified_retracements.append(swing)
                self._log_state_change(f"Qualified retracement (0.3+): {swing.price:.5f}")
        
        # Check for trend continuation or reversal based on bar close
        self._check_trend_decision(bar)
        
        return critical_points_changed
    
    def _handle_downtrend_logic(self, swing: SwingPoint, bar: Bar) -> bool:
        """
        Downtrend mode with 0.3 retracement qualification:
        1. Lower lows -> expand critical low (expand fib)
        2. Swing highs need 0.3+ retracement to qualify for waiting list
        3. Wait for close below last critical low OR close above last critical high
        4. If close below critical low: find most extreme swing high between bar and last critical low
        """
        
        critical_points_changed = False
        
        if not swing.is_high:
            # Lower low -> expand critical low and fib
            current_low = self.critical_lows[-1].price
            if swing.price < current_low:
                self._add_critical_low(swing)
                critical_points_changed = True
                self._log_state_change(f"Critical low expanded: {swing.price:.5f} (fib expanding)")
                    
        else:
            # Swing high - check if it qualifies for 0.3+ retracement  
            if self._qualifies_for_retracement(swing, is_uptrend=False):
                self.qualified_retracements.append(swing)
                self._log_state_change(f"Qualified retracement (0.3+): {swing.price:.5f}")
        
        # Check for trend continuation or reversal based on bar close
        self._check_trend_decision(bar)
        
        return critical_points_changed
    
    def _qualifies_for_retracement(self, swing: SwingPoint, is_uptrend: bool) -> bool:
        """Check if swing qualifies as 0.3+ retracement to be added to waiting list"""
        
        if len(self.critical_highs) == 0 or len(self.critical_lows) == 0:
            return False
        
        current_high = self.critical_highs[-1].price
        current_low = self.critical_lows[-1].price
        fib_range = current_high - current_low
        
        if is_uptrend:
            # In uptrend: swing low needs to retrace 0.3+ of fib range below current low
            threshold_price = current_low - (fib_range * 0.3)
            return not swing.is_high and swing.price < threshold_price
        else:
            # In downtrend: swing high needs to retrace 0.3+ of fib range above current high  
            threshold_price = current_high + (fib_range * 0.3)
            return swing.is_high and swing.price > threshold_price
    
    def _check_trend_decision(self, bar: Bar) -> None:
        """
        Check for trend continuation or reversal:
        - Close above last critical high: continue trend, update critical low from qualified retracements
        - Close below last critical low: reverse trend or reset
        """
        
        if len(self.critical_highs) == 0 or len(self.critical_lows) == 0:
            return
            
        current_price = float(bar.close)
        last_critical_high = self.critical_highs[-1].price
        last_critical_low = self.critical_lows[-1].price
        
        if self.state == "UPTREND_MODE":
            if current_price > last_critical_high:
                # Continue uptrend with deep retracement - find most extreme low in time window
                self._update_critical_low_from_qualified(bar, last_critical_high)
                self._log_state_change(f"Uptrend continued above {last_critical_high:.5f}")
                
            elif current_price < last_critical_low:
                # Trend reversal or reset
                self.state = "DOWNTREND_MODE"
                self.qualified_retracements.clear()
                self._log_state_change(f"Trend reversed to downtrend below {last_critical_low:.5f}")
                
        elif self.state == "DOWNTREND_MODE":
            if current_price < last_critical_low:
                # Continue downtrend with deep retracement - find most extreme high in time window
                self._update_critical_high_from_qualified(bar, last_critical_low)
                self._log_state_change(f"Downtrend continued below {last_critical_low:.5f}")
                
            elif current_price > last_critical_high:
                # Trend reversal or reset
                self.state = "UPTREND_MODE"
                self.qualified_retracements.clear()
                self._log_state_change(f"Trend reversed to uptrend above {last_critical_high:.5f}")
                
    def _update_critical_low_from_qualified(self, bar: Bar, last_critical_high_price: float) -> None:
        """Find most extreme swing low in qualified retracements between bar and last critical high"""
        
        if not self.qualified_retracements:
            return
            
        # Find last critical high timestamp
        last_critical_high_timestamp = self.critical_highs[-1].timestamp
        
        # Filter qualified lows between last critical high and current bar
        time_window_lows = [
            swing for swing in self.qualified_retracements 
            if not swing.is_high and swing.timestamp >= last_critical_high_timestamp and swing.timestamp <= bar.ts_event
        ]
        
        if time_window_lows:
            # Find most extreme (lowest) swing low in time window
            most_extreme_low = min(time_window_lows, key=lambda x: x.price)
            self._add_critical_low(most_extreme_low)
            self._log_state_change(f"Critical low updated to most extreme in window: {most_extreme_low.price:.5f}")
            
    def _update_critical_high_from_qualified(self, bar: Bar, last_critical_low_price: float) -> None:
        """Find most extreme swing high in qualified retracements between bar and last critical low"""
        
        if not self.qualified_retracements:
            return
            
        # Find last critical low timestamp
        last_critical_low_timestamp = self.critical_lows[-1].timestamp
        
        # Filter qualified highs between last critical low and current bar
        time_window_highs = [
            swing for swing in self.qualified_retracements 
            if swing.is_high and swing.timestamp >= last_critical_low_timestamp and swing.timestamp <= bar.ts_event
        ]
        
        if time_window_highs:
            # Find most extreme (highest) swing high in time window
            most_extreme_high = max(time_window_highs, key=lambda x: x.price)
            self._add_critical_high(most_extreme_high)
            self._log_state_change(f"Critical high updated to most extreme in window: {most_extreme_high.price:.5f}")
    
    def _log_state_change(self, message: str) -> None:
        """Log state changes for debugging and transparency"""
        self.state_changes.append(f"[{self.state}] {message}")
        # Keep only last 20 state changes to avoid memory bloat
        if len(self.state_changes) > 20:
            self.state_changes.pop(0)
    
    # Simple interface methods for Fibonacci tool and strategy
            current_price = float(bar.close)
            current_high = self.critical_highs[-1].price
            current_low = self.critical_lows[-1].price
            
            # UPTREND: Check for break below critical low
            if self.state == "UPTREND_MODE" and current_price < current_low:
                # Find most extreme swing HIGH in window: last critical_high timestamp → current bar
                most_extreme_high = self._find_most_extreme_swing_in_window(
                    start_timestamp=self.critical_highs[-1].timestamp,
                    end_timestamp=int(bar.ts_event),
                    find_high=True
                )
                
                if most_extreme_high:
                    self._add_critical_high(most_extreme_high)
                    self._log_state_change(f"Critical low broken in uptrend - updated critical high to most extreme: {most_extreme_high.price:.5f}")
                    return True
            
            # DOWNTREND: Check for break above critical high  
            elif self.state == "DOWNTREND_MODE" and current_price > current_high:
                # Find most extreme swing LOW in window: last critical_low timestamp → current bar
                most_extreme_low = self._find_most_extreme_swing_in_window(
                    start_timestamp=self.critical_lows[-1].timestamp,
                    end_timestamp=int(bar.ts_event),
                    find_high=False
                )
                
                if most_extreme_low:
                    self._add_critical_low(most_extreme_low)
                    self._log_state_change(f"Critical high broken in downtrend - updated critical low to most extreme: {most_extreme_low.price:.5f}")
                    return True
        
        return False
    
    def _find_most_extreme_swing_in_window(self, start_timestamp: int, end_timestamp: int, find_high: bool) -> Optional[SwingPoint]:
        """Find most extreme swing point (high or low) in specified time window"""
        
        # Filter swing points in the time window with correct type
        candidates = [
            swing for swing in self.all_swing_points
            if start_timestamp <= swing.timestamp <= end_timestamp and swing.is_high == find_high
        ]
        
        if not candidates:
            return None
        
        if find_high:
            # Return swing with highest price
            return max(candidates, key=lambda x: x.price)
        else:
            # Return swing with lowest price  
            return min(candidates, key=lambda x: x.price)
    
    def _log_state_change(self, message: str) -> None:
        """Log state changes for debugging and transparency"""
        self.state_changes.append(f"[{self.state}] {message}")
        # Keep only last 20 state changes to avoid memory bloat
        if len(self.state_changes) > 20:
            self.state_changes.pop(0)
    
    # Simple interface methods for Fibonacci tool and strategy
    def get_last_swing_high(self) -> Optional[SwingPoint]:
        """Get current critical high for Fibonacci calculation"""
        return self.critical_highs[-1] if len(self.critical_highs) > 0 else None
    
    def get_last_swing_low(self) -> Optional[SwingPoint]:
        """Get current critical low for Fibonacci calculation"""
        return self.critical_lows[-1] if len(self.critical_lows) > 0 else None
    
    def get_direction_with_confidence(self):
        """Get direction for Fibonacci calculation based on current state"""
        if self.state == "UPTREND_MODE":
            return "up", 1.0
        elif self.state == "DOWNTREND_MODE":
            return "down", 1.0
        elif len(self.critical_highs) > 0 and len(self.critical_lows) > 0:
            # In baseline/waiting state, use most recent critical point
            last_high = self.critical_highs[-1]
            last_low = self.critical_lows[-1]
            if last_high.timestamp > last_low.timestamp:
                return "up", 0.5  # Lower confidence
            else:
                return "down", 0.5  # Lower confidence
        return "unknown", 0.0
    
    def get_key_levels(self) -> dict:
        """Get key levels for strategy use"""
        current_high = self.critical_highs[-1] if len(self.critical_highs) > 0 else None
        current_low = self.critical_lows[-1] if len(self.critical_lows) > 0 else None
        
        return {
            "last_swing_high": current_high.price if current_high else None,
            "last_swing_low": current_low.price if current_low else None,
            "state": self.state,
            "qualified_retracements": len(self.qualified_retracements),
            "initialized": self.swings.initialized and current_high is not None and current_low is not None,
            "critical_highs_count": len(self.critical_highs),
            "critical_lows_count": len(self.critical_lows)
        }
    
    def get_state_history(self) -> List[str]:
        """Get recent state changes for debugging"""
        return self.state_changes.copy()
    
    def reset(self) -> None:
        """Reset the archive"""
        self.swings = Swings(period=5)
        self.state = "COLLECTING_INITIAL"
        self.critical_highs.clear()
        self.critical_lows.clear()
        self.qualified_retracements.clear()
        self.last_high_value = None
        self.last_low_value = None
        self.state_changes.clear()
