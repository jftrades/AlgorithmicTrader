from typing import List, Tuple
from decimal import Decimal
from nautilus_trader.model.data import Bar


class FVG_Analyser:
    def __init__(self, min_size: float, lookback: int):
        self.min_size = min_size
        self.lookback = lookback
        self.bar_buffer: List[Bar] = []  # Buffer to store the last three bars

    def update_bars(self, bar: Bar) -> None:
        """
        Updates the bar buffer with the latest bar.
        Keeps only the last three bars in the buffer.
        """
        self.bar_buffer.append(bar)
        if len(self.bar_buffer) > 3:
            self.bar_buffer.pop(0)

    def is_bullish_fvg(self) -> Tuple[bool, Tuple[Decimal, Decimal]]:
        """
        Checks if the last three bars form a bullish FVG.
        Returns a tuple (bool, (high, low)) indicating if a bullish FVG exists and its range.
        """
        if len(self.bar_buffer) < 3:
            return False, (Decimal("0"), Decimal("0"))

        bar_2 = self.bar_buffer[-3]
        bar_0 = self.bar_buffer[-1]

        if bar_0.low > bar_2.high:
            return True, (bar_2.high, bar_0.low)
        return False, (Decimal("0"), Decimal("0"))

    def is_bearish_fvg(self) -> Tuple[bool, Tuple[Decimal, Decimal]]:
        """
        Checks if the last three bars form a bearish FVG.
        Returns a tuple (bool, (high, low)) indicating if a bearish FVG exists and its range.
        """
        if len(self.bar_buffer) < 3:
            return False, (Decimal("0"), Decimal("0"))

        bar_2 = self.bar_buffer[-3]
        bar_0 = self.bar_buffer[-1]

        if bar_0.high < bar_2.low:
            return True, (bar_2.low, bar_0.high)
        return False, (Decimal("0"), Decimal("0"))
