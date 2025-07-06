import datetime as dt
from pathlib import Path
import pandas as pd
import requests
import zipfile
import sys

TICKER = "BTCUSDT"
START_DATE = dt.date(2024, 1, 1)
END_DATE = dt.date(2024, 1, 3)

BASE_DATA_DIR = Path(__file__).resolve().parent.parent / "DATA_STORAGE"
TEMP_DIR = BASE_DATA_DIR / "temp_tick_downloads"
start_str = START_DATE.strftime("%Y-%m-%d")
end_str = END_DATE.strftime("%Y-%m-%d")
PROCESSED_DIR = BASE_DATA_DIR / f"processed_tick_data_{start_str}_to_{end_str}" / "csv"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

FUTURES_URL = "https://data.binance.vision/data/futures/um/daily/trades"
output_file = PROCESSED_DIR / f"{TICKER}_TICKS_{start_str}_to_{end_str}.csv"
if output_file.exists():
    output_file.unlink()

columns = ['trade_id', 'price', 'quantity', 'base_quantity', 'timestamp', 'is_buyer_maker']
total_days = (END_DATE - START_DATE).days + 1

print(f"Download {TICKER} Ticks: {start_str} bis {end_str}")
for n in range(total_days):
    date = START_DATE + dt.timedelta(days=n)
    filename = f"{TICKER}-trades-{date.strftime('%Y-%m-%d')}.zip"
    url = f"{FUTURES_URL}/{TICKER}/{filename}"
    zip_path = TEMP_DIR / filename

    sys.stdout.write(f"\r[{n+1:>3}/{total_days}] {date.strftime('%Y-%m-%d')} ...")
    sys.stdout.flush()

    r = requests.get(url)
    if r.status_code != 200:
        continue
    with open(zip_path, "wb") as f:
        f.write(r.content)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(TEMP_DIR)
    for csv_file in TEMP_DIR.glob("*.csv"):
        df = pd.read_csv(csv_file, names=columns, low_memory=False)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['price', 'quantity', 'timestamp'])
        df = df[(df['price'] > 0) & (df['quantity'] > 0) & (df['timestamp'] > 0)]
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df['buyer_maker'] = df['is_buyer_maker'].astype(str).str.lower() == 'true'
        chunk = df[['timestamp', 'trade_id', 'price', 'quantity', 'buyer_maker']]
        mode = 'w' if n == 0 else 'a'
        header = n == 0
        chunk.to_csv(output_file, mode=mode, header=header, index=False)
        csv_file.unlink(missing_ok=True)
    zip_path.unlink(missing_ok=True)

print("\nDownload abgeschlossen.")

for f in TEMP_DIR.glob("*"):
    f.unlink(missing_ok=True)
TEMP_DIR.rmdir()