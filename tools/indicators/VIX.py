import yfinance as yf
import pandas as pd

class VIX:
    def __init__(
        self,
        start: str = "2020-01-01",
        end: str = "2025-01-01",
        fear_threshold: float = 25.0,
        chill_threshold: float = 15.0
    ):
        self.data = yf.download("^VIX", start=start, end=end)
        self.fear_threshold = fear_threshold
        self.chill_threshold = chill_threshold

    def get_latest_value(self) -> float:
        return float(self.data["Close"].iloc[-1])

    def get_value_on_date(self, date: str) -> float:
        row = self.data.loc[self.data.index == date]
        if not row.empty:
            return float(row["Close"].iloc[0])
        return None

    def is_market_in_fear(self, value: float = None) -> bool:
        if value is None:
            value = self.get_latest_value()
        return value >= self.fear_threshold

    def is_market_chilling(self, value: float = None) -> bool:
        if value is None:
            value = self.get_latest_value()
        return value <= self.chill_threshold