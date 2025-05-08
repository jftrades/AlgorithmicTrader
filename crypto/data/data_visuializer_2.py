import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os

# Pfad zur CSV-Datei (lokal anpassen)
file_path = os.path.join(
    ".", "DATA_STORAGE", "spot",
    "monthly", "klines", "BTCUSDT", "15m",
    "BTCUSDT-15m-2025-04.csv"
)

# CSV-Datei laden
df = pd.read_csv(file_path, header=None)
df.columns = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
]

# Zeitstempel konvertieren (Mikrosekunden)
df["open_time"] = pd.to_datetime(df["open_time"], unit="us")
df.set_index("open_time", inplace=True)

# Beispiel-Trades (realistisch aus echten Datenpunkten)
trades = [
    {
        "type": "long",
        "time": pd.Timestamp("2025-04-10 12:00"),
        "entry": float(df.loc["2025-04-10 12:00"]["close"]),
        "sl": float(df.loc["2025-04-10 12:00"]["close"]) * 0.98,
        "tp": float(df.loc["2025-04-10 12:00"]["close"]) * 1.02
    },
    {
        "type": "short",
        "time": pd.Timestamp("2025-04-20 18:00"),
        "entry": float(df.loc["2025-04-20 18:00"]["close"]),
        "sl": float(df.loc["2025-04-20 18:00"]["close"]) * 1.02,
        "tp": float(df.loc["2025-04-20 18:00"]["close"]) * 0.98
    }
]

# Candlestick-Chart erzeugen
fig = go.Figure(data=[
    go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="BTCUSDT"
    )
])

# Volumen-Leiste hinzufügen
fig.add_trace(go.Bar(
    x=df.index,
    y=df["volume"],
    marker_color='rgba(150, 150, 250, 0.3)',
    yaxis='y2',
    name='Volume'
))

# Entry/SL/TP Punkte einzeichnen
for trade in trades:
    color = "green" if trade["type"] == "long" else "red"
    direction = "Buy" if trade["type"] == "long" else "Sell"

    # Entry
    fig.add_trace(go.Scatter(
        x=[trade["time"]],
        y=[trade["entry"]],
        mode="markers+text",
        marker=dict(size=12, color=color, symbol="arrow-up" if trade["type"] == "long" else "arrow-down"),
        name=f"{direction} Entry",
        text=[f"{direction} Entry"],
        textposition="top center"
    ))

    # Stop Loss
    fig.add_trace(go.Scatter(
        x=[trade["time"]],
        y=[trade["sl"]],
        mode="markers+text",
        marker=dict(size=10, color="orange", symbol="x"),
        name="Stop Loss",
        text=["SL"],
        textposition="bottom center"
    ))

    # Take Profit
    fig.add_trace(go.Scatter(
        x=[trade["time"]],
        y=[trade["tp"]],
        mode="markers+text",
        marker=dict(size=10, color="blue", symbol="circle"),
        name="Take Profit",
        text=["TP"],
        textposition="bottom center"
    ))

# Layout & Stil
fig.update_layout(
    title="BTCUSDT – 15m Candlestick Chart mit Entry / SL / TP",
    xaxis_title="Date",
    yaxis_title="Price (USDT)",
    yaxis=dict(domain=[0.2, 1]),
    yaxis2=dict(domain=[0, 0.15], showticklabels=False),
    xaxis_rangeslider_visible=False,
    height=700,
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

# Chart anzeigen
fig.show()
