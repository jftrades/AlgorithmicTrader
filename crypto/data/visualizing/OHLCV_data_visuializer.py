import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

# Pfad zur Datei (manuell anpassen, falls nötig)
file_path = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_data_2023-07-01_to_2024-08-15" / "csv" / "BTCUSDT_15MINUTE_2023-07-01_to_2024-08-15.csv"

# CSV ohne Header laden und manuell Spaltennamen zuweisen
df = pd.read_csv(file_path, header=None, names=[
    "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
])

# Zeitstempel konvertieren
df["open_time"] = pd.to_datetime(df["open_time_ms"], unit="ms")
df.set_index("open_time", inplace=True)

# Candlestick-Chart
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

# Volumen hinzufügen
fig.add_trace(go.Bar(
    x=df.index,
    y=df["volume"],
    marker_color='rgba(150, 150, 250, 0.3)',
    yaxis='y2',
    name='Volume'
))

# Layout
fig.update_layout(
    title="BTCUSDT – 15m Candlestick Chart mit Volumen",
    xaxis_title="Zeit",
    yaxis_title="Preis (USDT)",
    yaxis=dict(domain=[0.2, 1]),
    yaxis2=dict(domain=[0, 0.15], showticklabels=False),
    xaxis_rangeslider_visible=False,
    height=700,
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

fig.show()
