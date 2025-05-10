import pandas as pd
import matplotlib.pyplot as plt
import os

# Pfad zur CSV-Datei
file_path = os.path.join(
    ".","DATA_STORAGE", "spot",
    "monthly", "klines", "BTCUSDT", "15m",
    "BTCUSDT-15m-2022-08.csv")

# Spaltennamen entsprechend der Binance-Kline-Datenstruktur
columns = [
    "timestamp", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
]

# CSV-Datei einlesen
df = pd.read_csv(file_path, names=columns)

# Zeitstempel von Mikrosekunden in datetime konvertieren
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="us")

# 'timestamp' als Index setzen
df.set_index("timestamp", inplace=True)

# Plot der Schlusskurse
plt.figure(figsize=(12, 6))
plt.plot(df.index, df["close"].astype(float))
plt.title("BTC/USDT OHLCV – April 2022")
plt.xlabel("Datum")
plt.ylabel("Preis (USDT)")
plt.grid(True)
plt.tight_layout()
plt.show()


