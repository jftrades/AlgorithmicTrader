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
    buy = trades[trades['action'] == 'BUY']
    sell = trades[trades['action'] == 'SHORT']
    def add(points, name, sym, color):
        if points.empty:
            return
        normal = points.index.difference([selected_idx]) if selected_idx is not None else points.index
        if len(normal) > 0:
            nb = points.loc[normal]
            fig.add_trace(go.Scatter(
                x=nb['timestamp'],
                y=nb.get('open_price_actual', nb.get('price_actual', 0)),
                mode='markers',
                name=name,
                marker=dict(symbol=sym, size=14, color=color,
                            line=dict(color='#fff', width=1)),
                customdata=nb.index.tolist(),
                hovertemplate=f'<b>{name}</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>'
            ))
        if selected_idx in points.index:
            st = points.loc[[selected_idx]]
            fig.add_trace(go.Scatter(
                x=st['timestamp'],
                y=st.get('open_price_actual', st.get('price_actual', 0)),
                mode='markers',
                name=f'{name} (Selected)',
                marker=dict(symbol=sym, size=20, color=color,
                            line=dict(color='#000', width=3)),
                showlegend=False,
                customdata=st.index.tolist(),
                hovertemplate=f'<b>{name} (Selected)</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>'
            ))
    add(buy, 'BUY', 'triangle-up', '#28a745')
    add(sell, 'SHORT', 'triangle-down', '#dc3545')

def add_trade_visualization(fig, trades_df, bars_df, trade_idx):
    if trade_idx not in trades_df.index:
        return
    trade = trades_df.loc[trade_idx]
    entry_time = trade.get('timestamp')
    exit_time = trade.get('closed_timestamp')
    if pd.isna(entry_time) or pd.isna(exit_time):
        return
    entry_price = trade.get('open_price_actual', trade.get('price_actual', 0))
    exit_price = trade.get('close_price_actual', 0)
    if entry_price == 0 or exit_price == 0:
        return

    fig.add_trace(go.Scatter(
        x=[entry_time, exit_time],
        y=[entry_price, exit_price],
        mode='lines',
        line=dict(color='#ffc107', width=3, dash='dash'),
        name='Trade Path',
        showlegend=False
    ))

    sl, tp = trade.get('sl'), trade.get('tp')
    for level, name, color in [(sl, 'SL', '#dc3545'), (tp, 'TP', '#28a745')]:
        if pd.notna(level) and level > 0:
            fig.add_trace(go.Scatter(
                x=[entry_time, exit_time],
                y=[level, level],
                mode='lines',
                line=dict(color=color, width=2, dash='dot'),
                name=name,
                showlegend=False
            ))

def build_indicator_figure(indicators_list):
    fig = go.Figure()
    colors = ['#000000', 'rgba(0,0,0,0.7)', 'rgba(0,0,0,0.5)', 'rgba(64,64,64,0.8)', 'rgba(96,96,96,0.6)']
    for i, (name, df) in enumerate(indicators_list):
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['value'],
            mode='lines',
            name=name,
            line=dict(color=colors[i % len(colors)], width=2),
            hovertemplate='<b>%{fullData.name}</b><br>Zeit: %{x|%Y-%m-%d %H:%M:%S}<br>Wert: %{y:.4f}<extra></extra>',
            showlegend=True,
            hoverlabel=dict(bgcolor="rgba(255,255,255,0.95)", bordercolor="#666")
        ))

    indicator_names = [name for name, _ in indicators_list]
    plot_title = " & ".join(indicator_names) if len(indicator_names) <= 3 else f"{indicator_names[0]} & {len(indicator_names) - 1} others"

    fig.update_layout(
        title={
            'text': plot_title,
            'font': {'size': 14, 'family': 'Inter, system-ui, sans-serif', 'color': '#4a5568'},
            'x': 0.02,
            'xanchor': 'left',
            'y': 0.98,
            'yanchor': 'top'
        },
        template="plotly_white",
        hovermode='x unified',
        margin=dict(t=45, b=60, l=60, r=20)
    )
    return fig
