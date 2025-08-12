import yfinance as yf
import pandas as pd

class VIX:
    def __init__(
        self,
        start: str = "2020-01-01",
        end: str = "2025-01-01",
        fear_threshold: float = 25.0
    ):
        # Robust: Nur das Datum extrahieren, falls Zeitanteil vorhanden ist
        start_clean = start.split("T")[0]
        end_clean = end.split("T")[0]
        self.data = yf.download("^VIX", start=start_clean, end=end_clean)
        self.data.index = pd.to_datetime(self.data.index).date
        self.fear_threshold = fear_threshold

    def get_latest_value(self) -> float:
        return float(self.data["Close"].iloc[-1])

    def get_value_on_date(self, date: str) -> float:
        date_only = date.split("T")[0]
        try:
            date_obj = pd.to_datetime(date_only).date()
        except Exception:
            return None
        row = self.data.loc[self.data.index == date_obj]
        if not row.empty:
            return float(row["Close"].iloc[0])
        return None

    def is_market_in_fear(self, value: float = None) -> bool:
        if value is None:
            value = self.get_latest_value()
        return value >= self.fear_threshold