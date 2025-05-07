import pandas as pd
import mplfinance as mpf
import os

# Pfad zur Datei
file_path = os.path.join(
    ".","DATA_STORAGE", "spot",
    "monthly", "klines", "BTCUSDT", "15m",
    "BTCUSDT-15m-2025-04.csv"
)

# Daten einlesen
df = pd.read_csv(file_path, header=None)
df.columns = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
]

# Zeitstempel konvertieren (Mikrosekunden)
df["open_time"] = pd.to_datetime(df["open_time"], unit="us")
df.set_index("open_time", inplace=True)

# Umbenennen auf Standard für mplfinance
df_ohlc = df[["open", "high", "low", "close", "volume"]].astype(float)
df_ohlc.index.name = "Date"

# Plot als Candlestick
mpf.plot(
    df_ohlc,
    type="candle",
    style="yahoo",
    title="BTCUSDT – 15m Candlestick Chart (April 2025)",
    volume=True,
    ylabel="Price (USDT)",
    ylabel_lower="Volume",
    figratio=(16, 8),
    tight_layout=True
)
