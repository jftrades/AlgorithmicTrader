from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from tools.structure.PivotArchive import PivotArchive, Pivot, PivotType
from nautilus_trader.model.data import Bar


@dataclass
class FibLevel:
    ratio: float
    price: float
    label: str


@dataclass
class FibRetracement:
    swing_high: Pivot
    swing_low: Pivot
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
        
        # Your specific Fibonacci ratios for visualization
        self.fib_ratios = [
            (-1.0, "-1.0"),      # Fib extension TP 3
            (-0.62, "-0.62"),    # Fib extension TP 2  
            (-0.27, "-0.27"),    # Fib extension TP 1
            (0.0, "0.0"),        # 0% level (end point)
            (0.5, "0.5"),        # 50% retracement
            (0.618, "0.618"),    # 61.8% retracement
            (0.786, "0.786"),    # 78.6% retracement
            (1.0, "1.0")         # 100% level (start point)
        ]
        
        self.current_retracement: Optional[FibRetracement] = None
        self.last_calculated_swing_high: Optional[Pivot] = None
        self.last_calculated_swing_low: Optional[Pivot] = None
        
    def update(self, bar: Bar) -> Optional[FibRetracement]:
        if not self.pivot_archive.swings.initialized:
            return None
            
        # Get the most recent swing high and low
        last_high = self.pivot_archive.get_last_swing_high()
        last_low = self.pivot_archive.get_last_swing_low()
        
        if not last_high or not last_low:
            return None
            
        # Check if we have new swing points to calculate from
        if (self.last_calculated_swing_high != last_high or 
            self.last_calculated_swing_low != last_low):
            
            self.current_retracement = self._calculate_retracement(last_high, last_low)
            self.last_calculated_swing_high = last_high
            self.last_calculated_swing_low = last_low
            
        return self.current_retracement
    
    def _calculate_retracement(self, swing_high: Pivot, swing_low: Pivot) -> FibRetracement:
        price_range = swing_high.price - swing_low.price
        
        # Determine direction based on which swing came most recently
        direction = "bullish" if swing_low.bar_index > swing_high.bar_index else "bearish"
        
        # Calculate all Fibonacci levels
        levels = []
        for ratio, label in self.fib_ratios:
            if direction == "bullish":
                # Bullish retracement: from low to high
                price = swing_low.price + (price_range * ratio)
            else:
                # Bearish retracement: from high to low
                price = swing_high.price - (price_range * ratio)
                
            levels.append(FibLevel(ratio=ratio, price=price, label=label))
        
        return FibRetracement(
            swing_high=swing_high,
            swing_low=swing_low,
            levels=levels,
            direction=direction,
            price_range=price_range
        )
    
    def get_retracement_for_visualization(self) -> Optional[Dict[str, Any]]:
        if not self.current_retracement:
            return None
            
        fib = self.current_retracement
        
        # Prepare data for collector visualization
        viz_data = {
            "swing_high_price": fib.swing_high.price,
            "swing_low_price": fib.swing_low.price,
            "direction": fib.direction,
            "price_range": fib.price_range
        }
        
        # Add each Fibonacci level for visualization
        for level in fib.levels:
            viz_data[f"fib_{level.label.replace('.', '_')}"] = level.price
            
        return viz_data
    
    def get_key_levels(self) -> Dict[str, Optional[float]]:
        if not self.current_retracement:
            return {
                "fib_1_0": None,        # 100% - start point
                "fib_0_786": None,      # 78.6% retracement
                "fib_0_618": None,      # 61.8% retracement  
                "fib_0_5": None,        # 50% retracement
                "fib_0_0": None,        # 0% - end point
                "fib_ext_0_27": None,   # -27% extension (TP1)
                "fib_ext_0_62": None,   # -62% extension (TP2)
                "fib_ext_1_0": None     # -100% extension (TP3)
            }
            
        levels_dict = {}
        for level in self.current_retracement.levels:
            if level.ratio == 1.0:
                levels_dict["fib_1_0"] = level.price
            elif level.ratio == 0.786:
                levels_dict["fib_0_786"] = level.price
            elif level.ratio == 0.618:
                levels_dict["fib_0_618"] = level.price
            elif level.ratio == 0.5:
                levels_dict["fib_0_5"] = level.price
            elif level.ratio == 0.0:
                levels_dict["fib_0_0"] = level.price
            elif level.ratio == -0.27:
                levels_dict["fib_ext_0_27"] = level.price
            elif level.ratio == -0.62:
                levels_dict["fib_ext_0_62"] = level.price
            elif level.ratio == -1.0:
                levels_dict["fib_ext_1_0"] = level.price
                
        return levels_dict
    
    def is_price_near_fib_level(self, price: float, tolerance: float = 0.001) -> Optional[FibLevel]:
        if not self.current_retracement:
            return None
            
        for level in self.current_retracement.levels:
            price_diff = abs(price - level.price)
            if price_diff <= tolerance * level.price:  # Percentage tolerance
                return level
                
        return None
    
    def get_level_by_ratio(self, ratio: float) -> Optional[FibLevel]:
        if not self.current_retracement:
            return None
            
        for level in self.current_retracement.levels:
            if abs(level.ratio - ratio) < 0.001:  # Small tolerance for float comparison
                return level
                
        return None
