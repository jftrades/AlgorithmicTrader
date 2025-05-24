"""
Plot Backtest – Candles, EMAs & Buy/Sell-Marker
------------------------------------------------
• CSV-Struktur (siehe dein Export):
    timestamp,open,high,low,close,volume,ema_fast,ema_slow,signal
• Visuals:
    – Candlestick-Chart
    – EMA-Fast (blau) & EMA-Slow (orange)
    – Buy-Signal  ➜ grüner ↑-Pfeil
    – Sell-Signal ➜ roter  ↓-Pfeil
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ------------------------------------------------------------------
# 1) CSV laden  –  Pfad ggf. anpassen
# ------------------------------------------------------------------
df = pd.read_csv("backtest_plot_data.csv", parse_dates=["timestamp"])
df.sort_values("timestamp", inplace=True)  # sicherstellen, dass alles sortiert ist
df.reset_index(drop=True, inplace=True)

# ------------------------------------------------------------------
# 2) Buy / Sell Marker herausfiltern
# ------------------------------------------------------------------
buys  = df[df["signal"] == "BUY"]
sells = df[df["signal"] == "SELL"]

# ------------------------------------------------------------------
# 3) Figure-Layout vorbereiten
# ------------------------------------------------------------------
fig = make_subplots(rows=1, cols=1, shared_xaxes=True,
                    specs=[[{"secondary_y": False}]])

# --- Candlestick-Chart -------------------------------------------
fig.add_trace(
    go.Candlestick(
        x=df["timestamp"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Bars",
        increasing_line_color="green",
        decreasing_line_color="red",
        showlegend=False,
    )
)

# --- EMA-Fast & EMA-Slow -----------------------------------------
fig.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["ema_fast"],
        mode="lines",
        line=dict(width=1.5, color="#1f77b4"),  # blau
        name="EMA Fast",
    )
)
fig.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["ema_slow"],
        mode="lines",
        line=dict(width=1.5, color="#ff7f0e"),  # orange
        name="EMA Slow",
    )
)

# --- Buy-Marker ---------------------------------------------------
fig.add_trace(
    go.Scatter(
        x=buys["timestamp"],
        y=buys["close"],
        mode="markers",
        marker=dict(
            symbol="triangle-up",
            color="black",
            size=12,
            line=dict(width=1, color="black"),
        ),
        name="Buy",
    )
)

# --- Sell-Marker --------------------------------------------------
fig.add_trace(
    go.Scatter(
        x=sells["timestamp"],
        y=sells["close"],
        mode="markers",
        marker=dict(
            symbol="triangle-down",
            color="black",
            size=12,
            line=dict(width=1, color="black"),
        ),
        name="Sell",
    )
)

# ------------------------------------------------------------------
# 4) Layout-Feinschliff
# ------------------------------------------------------------------
fig.update_layout(
    title=dict(text="EMA Cross Backtest – Bars, EMAs, Trades", x=0.5),
    xaxis_title="Zeit",
    yaxis_title="Preis",
    xaxis_rangeslider_visible=False,
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=40, r=20, t=60, b=40),
)

# 5) Plot anzeigen / speichern
fig.show()               # interaktiv
# fig.write_html("backtest_plot.html")  # optional als HTML-Report speichern
