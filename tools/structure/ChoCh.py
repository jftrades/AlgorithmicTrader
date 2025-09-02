# in here there will be a ChoCh class coded like I learned a ChoCh (some call it BOS as well)
# 1. identify the last swing high and last swing low
# 2. with the value of these highs and lows, determine the current trend (market structure)
# 3. keep on tracking the swing high and lows with a n lookback (f.e. 50)
# 4. always compare the bar.close to the last swing high and swing low
# 5. if we are in a downtrend (lower lows, lower highs) -> wait for bar.close > last_swing_high -> long szenario
# 6. if we are in an uptrend (higher highs, higher lows) -> wait for bar.close < last_swing_low -> short szenario

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass

from nautilus_trader.model.data import Bar
from nautilus_trader.indicators.swings import Swings


class TrendDirection(Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


class BreakType(Enum):
    """Enumeration for break types."""
    BULLISH_CHOCH = "bullish_choch"  # Was in downtrend, now breaking up -> LONG
    BEARISH_CHOCH = "bearish_choch"  # Was in uptrend, now breaking down -> SHORT
    NO_BREAK = "no_break"


@dataclass
class SwingPoint:
    price: float
    timestamp: int
    is_high: bool
    bar_index: int


@dataclass
class ChochSignal:
    """Data class representing a ChoCh/BOS signal."""
    signal_type: BreakType
    direction: TrendDirection
    price: float
    timestamp: int
    confidence: float = 1.0


class ChoCh:
    def __init__(self, lookback_period: int = 50, min_swing_strength: int = 3):

        self.lookback_period = lookback_period
        self.min_swing_strength = min_swing_strength
        
        # Initialize the Swings indicator from NautilusTrader
        self.swings = Swings(period=min_swing_strength)
        
        # Market structure tracking
        self.last_swing_high: Optional[SwingPoint] = None
        self.last_swing_low: Optional[SwingPoint] = None
        self.previous_swing_high: Optional[SwingPoint] = None
        self.previous_swing_low: Optional[SwingPoint] = None
        
        # Trend analysis
        self.current_trend: TrendDirection = TrendDirection.UNKNOWN
        self.trend_confidence: float = 0.0
        
        # Break tracking
        self.last_break_type: BreakType = BreakType.NO_BREAK
        self.last_signal: Optional[ChochSignal] = None
        
        # Bar tracking
        self.bar_count: int = 0
        self.bars_since_last_signal: int = 0
        
        # State flags
        self.initialized: bool = False
        
    def handle_bar(self, bar: Bar) -> Optional[ChochSignal]:
        self.bar_count += 1
        self.bars_since_last_signal += 1
        
        # Update the swings indicator
        self.swings.handle_bar(bar)
        
        # Wait for swings indicator to initialize
        if not self.swings.initialized:
            return None
            
        # Update swing points if they changed
        self._update_swing_points(bar)
        
        # Analyze market structure
        self._analyze_market_structure()
        
        # Check for break signals
        signal = self._check_for_breaks(bar)
        
        if signal:
            self.last_signal = signal
            self.bars_since_last_signal = 0
            
        if not self.initialized and self.last_swing_high and self.last_swing_low:
            self.initialized = True
            
        return signal
    
    def _update_swing_points(self, bar: Bar) -> None:
        # Check if we have a new swing high
        if (self.swings.changed and self.swings.direction == 1 and 
            (not self.last_swing_high or self.swings.high_price != self.last_swing_high.price)):
            
            # Store previous swing high
            if self.last_swing_high:
                self.previous_swing_high = self.last_swing_high
                
            # Create new swing high
            self.last_swing_high = SwingPoint(
                price=float(self.swings.high_price),
                timestamp=int(bar.ts_event),
                is_high=True,
                bar_index=self.bar_count
            )
            
        # Check if we have a new swing low
        if (self.swings.changed and self.swings.direction == -1 and 
            (not self.last_swing_low or self.swings.low_price != self.last_swing_low.price)):
            
            # Store previous swing low
            if self.last_swing_low:
                self.previous_swing_low = self.last_swing_low
                
            # Create new swing low
            self.last_swing_low = SwingPoint(
                price=float(self.swings.low_price),
                timestamp=int(bar.ts_event),
                is_high=False,
                bar_index=self.bar_count
            )
    
    def _analyze_market_structure(self) -> None:
        if not (self.last_swing_high and self.last_swing_low and 
                self.previous_swing_high and self.previous_swing_low):
            self.current_trend = TrendDirection.UNKNOWN
            self.trend_confidence = 0.0
            return
            
        # Check for higher highs and higher lows (uptrend)
        higher_high = self.last_swing_high.price > self.previous_swing_high.price
        higher_low = self.last_swing_low.price > self.previous_swing_low.price
        
        # Check for lower highs and lower lows (downtrend)
        lower_high = self.last_swing_high.price < self.previous_swing_high.price
        lower_low = self.last_swing_low.price < self.previous_swing_low.price
        
        # Determine trend
        if higher_high and higher_low:
            self.current_trend = TrendDirection.UPTREND
            self.trend_confidence = 1.0
        elif lower_high and lower_low:
            self.current_trend = TrendDirection.DOWNTREND
            self.trend_confidence = 1.0
        elif higher_high and lower_low:
            self.current_trend = TrendDirection.SIDEWAYS
            self.trend_confidence = 0.5
        elif lower_high and higher_low:
            self.current_trend = TrendDirection.SIDEWAYS
            self.trend_confidence = 0.5
        else:
            self.current_trend = TrendDirection.UNKNOWN
            self.trend_confidence = 0.0
    
    def _check_for_breaks(self, bar: Bar) -> Optional[ChochSignal]:
        if not self.initialized:
            return None
            
        close_price = float(bar.close)
        
        # Check for bullish ChoCh (was in downtrend, breaking above swing high -> LONG)
        if (self.current_trend == TrendDirection.DOWNTREND and 
            self.last_swing_high and close_price > self.last_swing_high.price):
            
            return ChochSignal(
                signal_type=BreakType.BULLISH_CHOCH,
                direction=TrendDirection.UPTREND,
                price=close_price,
                timestamp=int(bar.ts_event),
                confidence=self.trend_confidence
            )
            
        # Check for bearish ChoCh (was in uptrend, breaking below swing low -> SHORT)
        if (self.current_trend == TrendDirection.UPTREND and 
            self.last_swing_low and close_price < self.last_swing_low.price):
            
            return ChochSignal(
                signal_type=BreakType.BEARISH_CHOCH,
                direction=TrendDirection.DOWNTREND,
                price=close_price,
                timestamp=int(bar.ts_event),
                confidence=self.trend_confidence
            )
        
        return None
    
    def get_market_structure_info(self) -> Dict[str, Any]:
        return {
            "initialized": self.initialized,
            "current_trend": self.current_trend.value if self.current_trend else "unknown",
            "trend_confidence": self.trend_confidence,
            "last_swing_high": {
                "price": self.last_swing_high.price if self.last_swing_high else None,
                "timestamp": self.last_swing_high.timestamp if self.last_swing_high else None,
                "bar_index": self.last_swing_high.bar_index if self.last_swing_high else None,
            },
            "last_swing_low": {
                "price": self.last_swing_low.price if self.last_swing_low else None,
                "timestamp": self.last_swing_low.timestamp if self.last_swing_low else None,
                "bar_index": self.last_swing_low.bar_index if self.last_swing_low else None,
            },
            "bars_since_last_signal": self.bars_since_last_signal,
            "last_break_type": self.last_break_type.value if self.last_break_type else "no_break"
        }
    
    def is_long_scenario(self, close_price: float) -> bool:
        return (self.initialized and 
                self.current_trend == TrendDirection.DOWNTREND and
                self.last_swing_high and 
                close_price > self.last_swing_high.price)
    
    def is_short_scenario(self, close_price: float) -> bool:
        return (self.initialized and 
                self.current_trend == TrendDirection.UPTREND and
                self.last_swing_low and 
                close_price < self.last_swing_low.price)
    
    def get_key_levels(self) -> Dict[str, Optional[float]]:
        return {
            "last_swing_high": self.last_swing_high.price if self.last_swing_high else None,
            "last_swing_low": self.last_swing_low.price if self.last_swing_low else None,
            "previous_swing_high": self.previous_swing_high.price if self.previous_swing_high else None,
            "previous_swing_low": self.previous_swing_low.price if self.previous_swing_low else None,
        }
    
    def reset(self) -> None:
        self.swings = Swings(period=self.min_swing_strength)
        self.last_swing_high = None
        self.last_swing_low = None
        self.previous_swing_high = None
        self.previous_swing_low = None
        self.current_trend = TrendDirection.UNKNOWN
        self.trend_confidence = 0.0
        self.last_break_type = BreakType.NO_BREAK
        self.last_signal = None
        self.bar_count = 0
        self.bars_since_last_signal = 0
        self.initialized = False