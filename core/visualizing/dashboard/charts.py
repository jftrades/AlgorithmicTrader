# core/visualizing/dashboard/charts.py
import plotly.graph_objects as go
import pandas as pd

def build_price_chart(bars_df, indicators_df, trades_df, selected_trade_index):
    fig = go.Figure()
    # Bars
    if bars_df is not None and not bars_df.empty:
        b = bars_df
        fig.add_trace(go.Candlestick(
            x=b['timestamp'], open=b['open'], high=b['high'], low=b['low'], close=b['close'],
            name='OHLC', increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
            increasing_fillcolor='#26a69a', decreasing_fillcolor='#ef5350', showlegend=True
        ))
    # Overlay indicators (plot_id == 0)
    for name, df in (indicators_df or {}).items():
        if df is None or df.empty: 
            continue
        try:
            pid = int(df['plot_id'].iloc[0])
            if pid == 0:
                fig.add_trace(go.Scatter(
                    x=df['timestamp'], y=df['value'], mode='lines',
                    name=name.upper(), line=dict(width=2.0)
                ))
        except Exception:
            pass
    # Trades
    if trades_df is not None and not trades_df.empty:
        _add_trade_markers(fig, trades_df, selected_trade_index)
        if selected_trade_index is not None:
            add_trade_visualization(fig, trades_df, bars_df, selected_trade_index)

    fig.update_layout(
        xaxis_title="Time", yaxis_title="Price (USDT)", template="plotly_white",
        hovermode='closest', margin=dict(t=30, b=50, l=60, r=20),
        xaxis=dict(rangeslider=dict(visible=False))
    )
    return fig

def _add_trade_markers(fig, trades, selected_idx):
    buy = trades[trades['action']=='BUY']; sell = trades[trades['action']=='SHORT']
    def add(points, name, sym, color):
        if points.empty: return
        normal = points.index.difference([selected_idx]) if selected_idx is not None else points.index
        if len(normal)>0:
            nb = points.loc[normal]
            fig.add_trace(go.Scatter(
                x=nb['timestamp'], y=nb.get('open_price_actual', nb.get('price_actual', 0)),
                mode='markers', name=name, marker=dict(symbol=sym, size=14, color=color, line=dict(color='#fff', width=1)),
                customdata=nb.index.tolist(),
                hovertemplate=f'<b>{name}</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>'
            ))
        if selected_idx in points.index:
            st = points.loc[[selected_idx]]
            fig.add_trace(go.Scatter(
                x=st['timestamp'], y=st.get('open_price_actual', st.get('price_actual', 0)),
                mode='markers', name=f"Selected {name}", marker=dict(symbol=sym, size=18, color=color, line=dict(color='#000', width=1)),
                customdata=[selected_idx], showlegend=False
            ))
    add(buy, "BUY", "triangle-up", "#28a745")
    add(sell, "SHORT", "triangle-down", "#dc3545")

def add_trade_visualization(fig, trades_df, bars_df, trade_index):
    if trades_df is None or trade_index not in trades_df.index:
        return
    trade = trades_df.loc[trade_index]
    entry_time = pd.to_datetime(trade['timestamp'])
    entry_price = trade.get('open_price_actual', trade.get('price_actual', None))
    exit_time = pd.to_datetime(trade['closed_timestamp']) if pd.notna(trade.get('closed_timestamp', None)) else None
    exit_price = trade['close_price_actual'] if pd.notna(trade.get('close_price_actual', None)) else None
    tp = trade.get('tp', None); sl = trade.get('sl', None)

    if entry_price is not None:
        _add_price_line_full_chart(fig, bars_df, entry_price, "Entry", "rgba(0,0,0,0.35)", "dash")
    if exit_time is not None and exit_price is not None:
        _add_price_line_full_chart(fig, bars_df, exit_price, "Exit", "rgba(0,0,0,0.35)", "dash")
        _add_exit_marker_small(fig, exit_time, exit_price)
    if exit_time is not None and entry_price is not None and (pd.notna(tp) or pd.notna(sl)):
        _add_tp_sl_boxes(fig, bars_df, entry_time, exit_time, entry_price, str(trade['action']).upper(), tp, sl)

def _add_price_line_full_chart(fig, bars_df, price, name, color, dash="dash"):
    import pandas as pd
    if bars_df is not None and not bars_df.empty:
        min_ts = bars_df['timestamp'].min(); max_ts = bars_df['timestamp'].max()
    else:
        min_ts, max_ts = pd.Timestamp.now() - pd.Timedelta(days=1), pd.Timestamp.now()
    fig.add_trace(go.Scatter(
        x=[min_ts, max_ts], y=[price, price], mode='lines',
        name=f"{name} Line", line=dict(color=color, width=1, dash=dash),
        showlegend=False, hovertemplate=f'<b>{name} Price</b><br>Price: {price:.4f} USDT<extra></extra>'
    ))

def _add_exit_marker_small(fig, exit_time, exit_price):
    fig.add_trace(go.Scatter(
        x=[exit_time], y=[exit_price], mode='markers', name='Trade Exit',
        marker=dict(symbol='x', size=11, color='#000', line=dict(color='#fff', width=1)),
        showlegend=False, hovertemplate='<b>Trade Exit</b><br>%{x}<br>Price: %{y:.4f} USDT<extra></extra>'
    ))

def _add_tp_sl_boxes(fig, bars_df, entry_time, exit_time, entry_price, action, tp, sl):
    is_long = action == 'BUY'
    if pd.notna(tp) and tp > 0:
        box_color = "rgba(76, 175, 80, 0.2)"; line_color = "#4CAF50"
        yb, yt = (min(tp, entry_price), max(tp, entry_price))
        _add_box(fig, bars_df, entry_time, exit_time, yb, yt, box_color, line_color, "TP")
    if pd.notna(sl) and sl > 0:
        box_color = "rgba(244, 67, 54, 0.2)"; line_color = "#F44336"
        yb, yt = (min(sl, entry_price), max(sl, entry_price))
        _add_box(fig, bars_df, entry_time, exit_time, yb, yt, box_color, line_color, "SL")

def _add_box(fig, bars_df, start_time, end_time, y_bottom, y_top, fill_color, line_color, label):
    mid_time = start_time + (end_time - start_time) / 2
    mid_price = (y_bottom + y_top) / 2
    fig.add_trace(go.Scatter(
        x=[start_time, end_time, end_time, start_time, start_time],
        y=[y_bottom, y_bottom, y_top, y_top, y_bottom],
        fill="toself", fillcolor=fill_color, line=dict(color=line_color, width=1),
        mode='lines', name=f"{label} Zone", showlegend=False,
        hovertemplate=f'<b>{label} Zone</b><br>Range: {y_bottom:.2f} - {y_top:.2f} USDT<extra></extra>'
    ))
    fig.add_annotation(x=mid_time, y=mid_price, text=label, showarrow=False,
                       font=dict(color=line_color, size=12, family="Inter, system-ui, sans-serif"),
                       bgcolor="rgba(255,255,255,0.8)", bordercolor=line_color, borderwidth=1)

def build_indicator_figure(indicators_list):
    fig = go.Figure()
    colors = ['#000000','rgba(0,0,0,0.7)','rgba(0,0,0,0.5)','rgba(64,64,64,0.8)','rgba(96,96,96,0.6)']
    for i, (name, df) in enumerate(indicators_list):
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['value'], mode='lines', name=name,
            line=dict(color=colors[i % len(colors)], width=2),
            hovertemplate='<b>%{fullData.name}</b><br>Zeit: %{x|%Y-%m-%d %H:%M:%S}<br>Wert: %{y:.4f}<extra></extra>',
            showlegend=True, hoverlabel=dict(bgcolor="rgba(255,255,255,0.95)", bordercolor="#666")
        ))
    fig.update_layout(template="plotly_white", hovermode='x unified', margin=dict(t=30, b=60, l=60, r=20))
    return fig
