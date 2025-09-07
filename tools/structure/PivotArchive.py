
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
    Clean Fibonacci Archive using 30% retracement logic:
    
    1. Wait for first swing high + low from Nautilus (baseline)
    2. Wait for price break to determine trend direction  
    3. In uptrend: expand high, protect low (only 30%+ retracements qualify)
    4. In downtrend: expand low, protect high (only 30%+ retracements qualify)
    5. Reset when price breaks critical levels
    
    This provides stable but adaptive Fibonacci levels.
    """
    
    def __init__(self, strength: int = 5):
        # Nautilus swings - our only swing source
        self.swings = Swings(period=strength)
        
        # State machine for clean logic flow
        self.state = "WAITING_FOR_BASELINE"  # WAITING_FOR_BASELINE -> WAITING_FOR_BREAK -> UPTREND_MODE/DOWNTREND_MODE
        
        # Baseline anchors (first swing high + low from Nautilus)
        self.baseline_high: Optional[SwingPoint] = None
        self.baseline_low: Optional[SwingPoint] = None
        
        # Current critical points for Fibonacci calculation
        self.critical_high: Optional[SwingPoint] = None  # Always available for Fibonacci
        self.critical_low: Optional[SwingPoint] = None   # Always available for Fibonacci
        
        # Store all swing points for retrospective analysis
        self.all_swing_points: List[SwingPoint] = []
        
        # Waiting list for significant retracements (30%+ deeper/shallower)
        self.retracement_candidates: List[SwingPoint] = []
        
        # Swing tracking from Nautilus
        self.last_high_value = None
        self.last_low_value = None
        
        # 30% retracement threshold for qualification
        self.retracement_threshold = 0.3
        
        # Range expansion limits to prevent infinite expansion
        self.max_range_multiplier = 3.0  # Max 3x baseline range
        self.baseline_range = None  # Store original range for comparison0
        
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
        
        # Even without new swings, check for price breaks that trigger state changes
        return self._check_price_breaks(bar)
    
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
        """Process new swing through our clean state machine"""
        
        if self.state == "WAITING_FOR_BASELINE":
            return self._handle_baseline_collection(swing)
            
        elif self.state == "WAITING_FOR_BREAK":
            return self._handle_break_detection(swing, bar)
            
        elif self.state == "UPTREND_MODE":
            return self._handle_uptrend_swing(swing)
            
        elif self.state == "DOWNTREND_MODE":
            return self._handle_downtrend_swing(swing)
        
        return False
    
    def _handle_baseline_collection(self, swing: SwingPoint) -> bool:
        """State 1: Collect first swing high and low as baseline anchors"""
        
        if swing.is_high and not self.baseline_high:
            self.baseline_high = swing
            self.critical_high = swing  # Also set as critical for immediate Fibonacci use
            self._log_state_change(f"Baseline high set: {swing.price:.5f}")
            
        elif not swing.is_high and not self.baseline_low:
            self.baseline_low = swing
            self.critical_low = swing  # Also set as critical for immediate Fibonacci use
            self._log_state_change(f"Baseline low set: {swing.price:.5f}")
        
        # Once we have both baseline points, move to next state
        if self.baseline_high and self.baseline_low:
            # Store baseline range for expansion limit calculations
            self.baseline_range = abs(self.baseline_high.price - self.baseline_low.price)
            self.state = "WAITING_FOR_BREAK"
            self._log_state_change("Baseline complete - waiting for trend break")
            return True  # Critical points changed
        
        return bool(self.critical_high and self.critical_low)  # Return True if we have both for Fibonacci
    
    def _handle_break_detection(self, swing: SwingPoint, bar: Bar) -> bool:
        """State 2: Wait for price break above baseline high OR below baseline low"""
        
        current_price = float(bar.close)
        
        # Check for break above baseline high (start uptrend)
        if current_price > self.baseline_high.price:
            self.state = "UPTREND_MODE"
            
            # CRITICAL FIX: Update critical points to reflect the actual trend start
            # Create break point at the exact bar.close that broke the baseline
            break_point = SwingPoint(
                price=current_price,
                timestamp=int(bar.ts_event),
                is_high=True  # This break point represents the new trend high
            )
            
            # Update critical points: new high at break, keep baseline low protected
            self.critical_high = break_point  # Fibonacci 0 will anchor here in uptrend
            # critical_low stays at baseline_low for protection
            
            self._log_state_change(f"UPTREND started - price {current_price:.5f} > baseline high {self.baseline_high.price:.5f} | Critical high updated to break point")
            return True  # Critical points changed
            
        # Check for break below baseline low (start downtrend)  
        elif current_price < self.baseline_low.price:
            self.state = "DOWNTREND_MODE"
            
            # CRITICAL FIX: Update critical points to reflect the actual trend start
            # Create break point at the exact bar.close that broke the baseline  
            break_point = SwingPoint(
                price=current_price,
                timestamp=int(bar.ts_event),
                is_high=False  # This break point represents the new trend low
            )
            
            # Update critical points: new low at break, keep baseline high protected
            self.critical_low = break_point  # Fibonacci 0 will anchor here in downtrend  
            # critical_high stays at baseline_high for protection
            
            self._log_state_change(f"DOWNTREND started - price {current_price:.5f} < baseline low {self.baseline_low.price:.5f} | Critical low updated to break point")
            return True  # Critical points changed
        
        return False  # No state change
    
    def _handle_uptrend_swing(self, swing: SwingPoint) -> bool:
        """State 3: Uptrend mode - expand high, handle retracements with 30% threshold"""
        
        critical_points_changed = False
        
        if swing.is_high:
            # Scenario 1: New swing high - expand critical high (lengthen Fibonacci range)
            if swing.price > self.critical_high.price:
                # Check if this expansion would exceed our range limit
                potential_range = abs(swing.price - self.critical_low.price)
                max_allowed_range = self.baseline_range * self.max_range_multiplier
                
                if potential_range <= max_allowed_range:
                    self.critical_high = swing
                    critical_points_changed = True
                    self._log_state_change(f"Critical high expanded: {swing.price:.5f}")
                else:
                    # Range too large - reset to more recent baseline
                    self._reset_to_recent_range(swing, is_uptrend=True)
                    critical_points_changed = True
                    self._log_state_change(f"Range limit exceeded - reset to recent range with new high: {swing.price:.5f}")
                    
        else:
            # New swing low - check if it qualifies for 30% retracement to become new critical_low
            if self._qualifies_for_retracement_uptrend(swing):
                self.retracement_candidates.append(swing)
                self._log_state_change(f"Retracement candidate added: {swing.price:.5f}")
                
                # Update critical low to deepest qualifying retracement (most extreme swing low > 30%)
                deepest_candidate = min(self.retracement_candidates, key=lambda x: x.price)
                if deepest_candidate.price < self.critical_low.price:
                    self.critical_low = deepest_candidate
                    critical_points_changed = True
                    self._log_state_change(f"Critical low updated to deepest retracement: {deepest_candidate.price:.5f}")
        
        return critical_points_changed
    
    def _handle_downtrend_swing(self, swing: SwingPoint) -> bool:
        """State 4: Downtrend mode - expand low, handle retracements with 30% threshold"""
        
        critical_points_changed = False
        
        if not swing.is_high:
            # Scenario 3: New swing low - expand critical low (lengthen Fibonacci range)
            if swing.price < self.critical_low.price:
                # Check if this expansion would exceed our range limit
                potential_range = abs(self.critical_high.price - swing.price)
                max_allowed_range = self.baseline_range * self.max_range_multiplier
                
                if potential_range <= max_allowed_range:
                    self.critical_low = swing
                    critical_points_changed = True
                    self._log_state_change(f"Critical low expanded: {swing.price:.5f}")
                else:
                    # Range too large - reset to more recent baseline
                    self._reset_to_recent_range(swing, is_uptrend=False)
                    critical_points_changed = True
                    self._log_state_change(f"Range limit exceeded - reset to recent range with new low: {swing.price:.5f}")
                    
        else:
            # New swing high - check if it qualifies for 30% retracement to become new critical_high
            if self._qualifies_for_retracement_downtrend(swing):
                self.retracement_candidates.append(swing)
                self._log_state_change(f"Retracement candidate added: {swing.price:.5f}")
                
                # Update critical high to shallowest qualifying retracement (most extreme swing high > 30%)
                shallowest_candidate = max(self.retracement_candidates, key=lambda x: x.price)
                if shallowest_candidate.price > self.critical_high.price:
                    self.critical_high = shallowest_candidate
                    critical_points_changed = True
                    self._log_state_change(f"Critical high updated to shallowest retracement: {shallowest_candidate.price:.5f}")
        
        return critical_points_changed
    
    def _qualifies_for_retracement_uptrend(self, swing_low: SwingPoint) -> bool:
        """Check if swing low qualifies as significant retracement (30%+ deeper) in uptrend"""
        
        if not self.critical_high or not self.critical_low:
            return False
        
        # Calculate 30% retracement from current Fibonacci range
        fib_range = self.critical_high.price - self.critical_low.price
        retracement_threshold_price = self.critical_low.price - (fib_range * self.retracement_threshold)
        
        # Qualify if swing low is 30%+ deeper than current critical low
        return swing_low.price < retracement_threshold_price
    
    def _qualifies_for_retracement_downtrend(self, swing_high: SwingPoint) -> bool:
        """Check if swing high qualifies as significant retracement (30%+ shallower) in downtrend"""
        
        if not self.critical_high or not self.critical_low:
            return False
        
        # Calculate 30% retracement from current Fibonacci range  
        fib_range = self.critical_high.price - self.critical_low.price
        retracement_threshold_price = self.critical_high.price + (fib_range * self.retracement_threshold)
        
        # Qualify if swing high is 30%+ shallower than current critical high
        return swing_high.price > retracement_threshold_price
    
    def _reset_to_recent_range(self, new_extreme_swing: SwingPoint, is_uptrend: bool) -> None:
        """Reset to a more recent, manageable range when expansion gets too large"""
        
        if is_uptrend:
            # For uptrend: keep new high, take last swing low before current critical high
            self.critical_high = new_extreme_swing
            
            # Find last swing low that occurred before the current critical high
            if self.retracement_candidates:
                # Filter candidates that occurred before current critical high
                valid_candidates = [
                    candidate for candidate in self.retracement_candidates 
                    if candidate.timestamp < self.critical_high.timestamp and not candidate.is_high
                ]
                if valid_candidates:
                    # Take the most recent valid swing low
                    self.critical_low = max(valid_candidates, key=lambda x: x.timestamp)
                else:
                    # If no valid candidates, keep current critical_low (don't create artificial)
                    pass
            
        else:
            # For downtrend: keep new low, take last swing high before current critical low  
            self.critical_low = new_extreme_swing
            
            # Find last swing high that occurred before the current critical low
            if self.retracement_candidates:
                # Filter candidates that occurred before current critical low
                valid_candidates = [
                    candidate for candidate in self.retracement_candidates 
                    if candidate.timestamp < self.critical_low.timestamp and candidate.is_high
                ]
                if valid_candidates:
                    # Take the most recent valid swing high
                    self.critical_high = max(valid_candidates, key=lambda x: x.timestamp)
                else:
                    # If no valid candidates, keep current critical_high (don't create artificial)
                    pass
        
        # Clear retracement candidates for fresh start
        self.retracement_candidates.clear()
        
        # Update baseline range to new, smaller range
        self.baseline_range = abs(self.critical_high.price - self.critical_low.price)
    
    def _check_price_breaks(self, bar: Bar) -> bool:
        """Check for critical level breaks and implement 4-scenario logic"""
        
        if self.state in ["UPTREND_MODE", "DOWNTREND_MODE"]:
            current_price = float(bar.close)
            
            # UPTREND: Check for break below critical low
            if self.state == "UPTREND_MODE" and current_price < self.critical_low.price:
                # Find most extreme swing HIGH in window: last critical_high timestamp → current bar
                most_extreme_high = self._find_most_extreme_swing_in_window(
                    start_timestamp=self.critical_high.timestamp,
                    end_timestamp=int(bar.ts_event),
                    find_high=True
                )
                
                if most_extreme_high:
                    self.critical_high = most_extreme_high
                    self._log_state_change(f"Critical low broken in uptrend - updated critical high to most extreme: {most_extreme_high.price:.5f}")
                    return True
            
            # DOWNTREND: Check for break above critical high  
            elif self.state == "DOWNTREND_MODE" and current_price > self.critical_high.price:
                # Find most extreme swing LOW in window: last critical_low timestamp → current bar
                most_extreme_low = self._find_most_extreme_swing_in_window(
                    start_timestamp=self.critical_low.timestamp,
                    end_timestamp=int(bar.ts_event),
                    find_high=False
                )
                
                if most_extreme_low:
                    self.critical_low = most_extreme_low
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
    
    def _reset_to_baseline(self) -> None:
        """Reset to baseline anchors and wait for new trend break"""
        
        # Reset critical points to baseline
        self.critical_high = self.baseline_high
        self.critical_low = self.baseline_low
        
        # Clear retracement candidates
        self.retracement_candidates.clear()
        
        # Return to waiting for break state
        self.state = "WAITING_FOR_BREAK"
    
    def _log_state_change(self, message: str) -> None:
        """Log state changes for debugging and transparency"""
        self.state_changes.append(f"[{self.state}] {message}")
        # Keep only last 20 state changes to avoid memory bloat
        if len(self.state_changes) > 20:
            self.state_changes.pop(0)
    
    # Simple interface methods for Fibonacci tool and strategy
    def get_last_swing_high(self) -> Optional[SwingPoint]:
        """Get critical high for Fibonacci calculation (always available after baseline)"""
        return self.critical_high
    
    def get_last_swing_low(self) -> Optional[SwingPoint]:
        """Get critical low for Fibonacci calculation (always available after baseline)"""
        return self.critical_low
    
    def get_direction_with_confidence(self):
        """Get direction for Fibonacci calculation based on current state"""
        if self.state == "UPTREND_MODE":
            return "up", 1.0
        elif self.state == "DOWNTREND_MODE":
            return "down", 1.0
        elif self.critical_high and self.critical_low:
            # In baseline/waiting state, use most recent critical point
            if self.critical_high.timestamp > self.critical_low.timestamp:
                return "up", 0.5  # Lower confidence
            else:
                return "down", 0.5  # Lower confidence
        return "unknown", 0.0
    
    def get_key_levels(self) -> dict:
        """Get key levels for strategy use"""
        return {
            "last_swing_high": self.critical_high.price if self.critical_high else None,
            "last_swing_low": self.critical_low.price if self.critical_low else None,
            "state": self.state,
            "retracement_candidates": len(self.retracement_candidates),
            "initialized": self.swings.initialized and self.critical_high is not None and self.critical_low is not None
        }
    
    def get_state_history(self) -> List[str]:
        """Get recent state changes for debugging"""
        return self.state_changes.copy()
    
    def reset(self) -> None:
        """Reset the archive"""
        self.swings = Swings(period=5)
        self.state = "WAITING_FOR_BASELINE"
        self.baseline_high = None
        self.baseline_low = None
        self.critical_high = None
        self.critical_low = None
        self.retracement_candidates.clear()
        self.last_high_value = None
        self.last_low_value = None
        self.state_changes.clear()
