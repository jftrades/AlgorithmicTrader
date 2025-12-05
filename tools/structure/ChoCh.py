# change of character analysis using PivotArchive for market structure

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass

from nautilus_trader.model.data import Bar
from .PivotArchive import PivotArchive, Pivot


class TrendDirection(Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


class BreakType(Enum):
    BULLISH_CHOCH = "bullish_choch"  # Was in downtrend, now breaking up -> LONG
    BEARISH_CHOCH = "bearish_choch"  # Was in uptrend, now breaking down -> SHORT
    NO_BREAK = "no_break"


@dataclass
class ChochSignal:
    signal_type: BreakType
    direction: TrendDirection
    price: float
    timestamp: int
    confidence: float = 1.0
    broken_pivot: Optional[Pivot] = None


class ChoCh:
    def __init__(self, lookback_period: int = 100, min_swing_strength: int = 3):
        self.lookback_period = lookback_period
        self.min_swing_strength = min_swing_strength
        
        # Initialize PivotArchive for swing detection and storage
        self.pivot_archive = PivotArchive(
            max_pivots=lookback_period, 
            swing_strength=min_swing_strength
        )
        
        # Market structure tracking
        self.current_trend: TrendDirection = TrendDirection.UNKNOWN
        self.trend_confidence: float = 0.0
        
        # Signal tracking
        self.last_break_type: BreakType = BreakType.NO_BREAK
        self.last_signal: Optional[ChochSignal] = None
        self.bars_since_last_signal: int = 0
        
        # Bar tracking
        self.bar_count: int = 0
        
    @property
    def initialized(self) -> bool:
        levels = self.pivot_archive.get_key_levels()
        return (levels["initialized"] and 
                levels["last_swing_high"] is not None and 
                levels["last_swing_low"] is not None)
    
    def handle_bar(self, bar: Bar) -> Optional[ChochSignal]:
        self.bar_count += 1
        self.bars_since_last_signal += 1
        
        # Update pivot archive with new bar
        self.pivot_archive.update(bar)
        
        # Analyze current market structure from pivots
        self._analyze_market_structure()
        
        # Check for break signals
        signal = self._check_for_breaks(bar)
        
        if signal:
            self.last_signal = signal
            self.last_break_type = signal.signal_type
            self.bars_since_last_signal = 0
            
        return signal
    
    def _analyze_market_structure(self) -> None:
        trend_direction, confidence = self.pivot_archive.analyze_trend_from_pivots()
        
        # Map string to enum
        trend_map = {
            "uptrend": TrendDirection.UPTREND,
            "downtrend": TrendDirection.DOWNTREND,
            "sideways": TrendDirection.SIDEWAYS,
            "unknown": TrendDirection.UNKNOWN
        }
        
        self.current_trend = trend_map.get(trend_direction, TrendDirection.UNKNOWN)
        self.trend_confidence = confidence
    
    def _check_for_breaks(self, bar: Bar) -> Optional[ChochSignal]:
        if not self.initialized:
            return None
            
        close_price = float(bar.close)
        
        # Get key pivot levels
        last_high = self.pivot_archive.get_last_swing_high()
        last_low = self.pivot_archive.get_last_swing_low()
        
        if not last_high or not last_low:
            return None
        
        # Check for bullish ChoCh (was in downtrend, breaking above swing high -> LONG)
        if (self.current_trend == TrendDirection.DOWNTREND and 
            close_price > last_high.price):
            
            return ChochSignal(
                signal_type=BreakType.BULLISH_CHOCH,
                direction=TrendDirection.UPTREND,
                price=close_price,
                timestamp=int(bar.ts_event),
                confidence=self.trend_confidence,
                broken_pivot=last_high
            )
            
        # Check for bearish ChoCh (was in uptrend, breaking below swing low -> SHORT)
        if (self.current_trend == TrendDirection.UPTREND and 
            close_price < last_low.price):
            
            return ChochSignal(
                signal_type=BreakType.BEARISH_CHOCH,
                direction=TrendDirection.DOWNTREND,
                price=close_price,
                timestamp=int(bar.ts_event),
                confidence=self.trend_confidence,
                broken_pivot=last_low
            )
        
        return None
    
    def get_market_structure_info(self) -> Dict[str, Any]:
        levels = self.pivot_archive.get_key_levels()
        recent_pivots = self.pivot_archive.get_recent_pivots(6)
        
        return {
            "initialized": self.initialized,
            "current_trend": self.current_trend.value if self.current_trend else "unknown",
            "trend_confidence": self.trend_confidence,
            "total_pivots": levels["total_pivots"],
            "recent_pivot_sequence": [
                {
                    "type": p.pivot_type.value, 
                    "price": p.price, 
                    "bar_age": self.bar_count - p.bar_index
                }
                for p in recent_pivots
            ],
            "key_levels": {
                "last_swing_high": levels["last_swing_high"],
                "last_swing_low": levels["last_swing_low"],
                "previous_swing_high": levels["previous_swing_high"],
                "previous_swing_low": levels["previous_swing_low"],
            },
            "bars_since_last_signal": self.bars_since_last_signal,
            "last_break_type": self.last_break_type.value if self.last_break_type else "no_break"
        }
    
    def is_long_scenario(self, close_price: float) -> bool:
        if not self.initialized:
            return False
        last_high = self.pivot_archive.get_last_swing_high()
        return (self.current_trend == TrendDirection.DOWNTREND and
                last_high and close_price > last_high.price)
    
    def is_short_scenario(self, close_price: float) -> bool:
        if not self.initialized:
            return False
        last_low = self.pivot_archive.get_last_swing_low()
        return (self.current_trend == TrendDirection.UPTREND and
                last_low and close_price < last_low.price)
    
    def get_key_levels(self) -> Dict[str, Optional[float]]:
        return self.pivot_archive.get_key_levels()
    
    def reset(self) -> None:
        self.pivot_archive.reset()
        self.current_trend = TrendDirection.UNKNOWN
        self.trend_confidence = 0.0
        self.last_break_type = BreakType.NO_BREAK
        self.last_signal = None
        self.bars_since_last_signal = 0
        self.bar_count = 0