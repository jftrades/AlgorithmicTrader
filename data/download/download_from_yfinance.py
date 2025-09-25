import yfinance as yf
import pandas as pd
from pathlib import Path

VIX_CSV_PATH = Path(__file__).parent / "../../data/DATA_STORAGE/data_catalog_wrangled/data/bar/vix_data.csv"

def download_and_save_vix_data(
    start: str = "2000-01-01",
    end: str = "2025-07-01",
    path: Path = VIX_CSV_PATH
) -> None:
    vix = yf.download("^VIX", start=start, end=end)
    path.parent.mkdir(parents=True, exist_ok=True)
    vix.to_csv(path)

if __name__ == "__main__":
    download_and_save_vix_data()