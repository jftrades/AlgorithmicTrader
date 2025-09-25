# core/visualizing/dashboard/charts.py
"""
Figure builder module.
Contains pure functions that construct Plotly figures (price + indicator plots).
Used by the callback modules (e.g. callbacks/charts.py). No Dash callbacks here.
"""
import plotly.graph_objects as go
import pandas as pd
import traceback

def build_price_chart(bars_df, indicators_df, trades_df, selected_trade_index, display_mode: str = "OHLC"):
    fig = go.Figure()
    # Bars
    index_ohlc = None
    index_close = None
    if bars_df is not None and not bars_df.empty:
        b = bars_df
        # Candlestick (standard sichtbar)
        fig.add_trace(go.Candlestick(
            x=b['timestamp'], open=b['open'], high=b['high'], low=b['low'], close=b['close'],
            name='OHLC', increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
            increasing_fillcolor='#26a69a', decreasing_fillcolor='#ef5350', showlegend=True
        ))
        index_ohlc = len(fig.data) - 1
        # stabile UID für Persistenz
        fig.data[index_ohlc].uid = "trace_ohlc"
        # Close-Line (initial unsichtbar)
        fig.add_trace(go.Scatter(
            x=b['timestamp'],
            y=b['close'],
            mode='lines',
            name='Close',                       # geändert von 'GRAPH'
            line=dict(color='#000000', width=1.6), # Farbe jetzt schwarz
            visible=False,
            hovertemplate='Time: %{x}<br>Close: %{y:.4f}<extra></extra>'
        ))
        index_close = len(fig.data) - 1
        fig.data[index_close].uid = "trace_graph"
    # Overlay indicators (plot_id == 0)
    # indicators_df expected as dict[name] -> DataFrame with columns ['timestamp','value','plot_id']
    try:
        for name, df in (indicators_df or {}).items():
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            try:
                pid = int(df['plot_id'].iloc[0]) if 'plot_id' in df.columns else 0
                if pid == 0:
                    # Check if this is a VWAP band indicator and make it black
                    line_color = '#000000' if 'vwap' in name.lower() and 'band' in name.lower() else None
                    line_config = dict(width=2.0, color=line_color) if line_color else dict(width=2.0)
                    
                    fig.add_trace(go.Scatter(
                        x=df['timestamp'], y=df['value'], mode='lines',
                        name=name.upper(), line=line_config
                    ))
            except Exception:
                # ignore indicator errors silently
                continue
    except Exception:
        pass
    # Trades
    if trades_df is not None and not trades_df.empty:
        # Linien zuerst, Marker danach!
        if selected_trade_index is not None:
            add_trade_visualization(fig, trades_df, bars_df, selected_trade_index)
        _add_trade_markers(fig, trades_df, selected_trade_index)

    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Price (USDT)",
        template="plotly_white",
        hovermode='x unified',
        hoverlabel=dict(bgcolor="rgba(255,255,255,0.9)", font=dict(size=11)),
        margin=dict(t=28, b=42, l=56, r=18),
        xaxis=dict(
            gridcolor="rgba(0,0,0,0.06)",
            zeroline=False,
            rangeslider=dict(visible=False)
        ),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)", zeroline=False),
        uirevision="linked-range"  # Ensure zoom/pan persistence
    )
    # Toggle Buttons (nur wenn Bars vorhanden)
    if index_ohlc is not None and index_close is not None:
        n = len(fig.data)
        vis_ohlc = [True] * n
        vis_close = [True] * n
        vis_ohlc[index_close] = False   # Close-Linie aus in OHLC-Modus
        vis_close[index_ohlc] = False   # Candlestick aus in Close-Modus
        # Falls persistenter Modus GRAPH: initial Graph aktiv
        if display_mode == "GRAPH":
            fig.data[index_ohlc].visible = False
            fig.data[index_close].visible = True
        else:
            fig.data[index_ohlc].visible = True
            fig.data[index_close].visible = False
        # Sichtbarkeiten aller Traces an initial state angleichen (nur zwei ersten unterscheiden sich)
        for i, tr in enumerate(fig.data):
            if i < len(vis_ohlc):
                if display_mode == "GRAPH":
                    tr.visible = vis_close[i]
                else:
                    tr.visible = vis_ohlc[i]
        fig.update_layout(
            updatemenus=[dict(
                type='buttons',
                direction='right',
                x=1.0,
                xanchor='right',
                y=0.995,          # höher platziert (knapp unter der Modebar-Zone)
                yanchor='top',
                pad=dict(r=2, t=2, b=2, l=2),
                bgcolor='rgba(255,255,255,0.55)',
                bordercolor='rgba(0,0,0,0.12)',
                borderwidth=1,
                font=dict(size=9),
                active=(0 if display_mode != "GRAPH" else 1),  # NEW: keep selected mode highlighted
                buttons=[
                    dict(label='OHLC',  method='update', args=[{'visible': vis_ohlc}]),
                    dict(label='Graph', method='update', args=[{'visible': vis_close}])  # Label bleibt 'Graph'
                ]
            )],
            legend=dict(
                bgcolor="rgba(255,255,255,0.55)",
                bordercolor="rgba(0,0,0,0.12)",
                borderwidth=1,
                font=dict(size=11)
            )
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
                marker=dict(
                    symbol=sym,
                    size=18,
                    color=color,
                    line=dict(color='#fff', width=1)
                ),
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

    # Chart-Grenzen bestimmen (volle Breite)
    if bars_df is not None and not bars_df.empty:
        x_min = bars_df['timestamp'].iloc[0]
        x_max = bars_df['timestamp'].iloc[-1]
    else:
        x_min = entry_time
        x_max = exit_time

    # Kräftige schwarze horizontale Linien für Entry/Exit (gestrichelt)
    fig.add_trace(go.Scatter(
        x=[x_min, x_max],
        y=[entry_price, entry_price],
        mode='lines',
        line=dict(color='rgba(0,0,0,0.50)', width=1, dash='dash'),
        name='Entry Price',
        showlegend=False,
        opacity=1,
        hoverinfo='skip'
    ))
    fig.add_trace(go.Scatter(
        x=[x_min, x_max],
        y=[exit_price, exit_price],
        mode='lines',
        line=dict(color='rgba(0,0,0,0.50)', width=1, dash='dash'),
        name='Exit Price',
        showlegend=False,
        opacity=1,
        hoverinfo='skip'
    ))

    sl, tp = trade.get('sl'), trade.get('tp')
    for level, name, color in [(sl, 'SL', '#dc3545'), (tp, 'TP', '#28a745')]:
        if pd.notna(level) and level > 0:
            fig.add_trace(go.Scatter(
                x=[x_min, x_max],
                y=[level, level],
                mode='lines',
                line=dict(color=color, width=2, dash='dot'),
                name=name,
                showlegend=False,
                opacity=0.5,
                hoverinfo='skip'
            ))

    # Add single black X at close (only for selected trade)
    fig.add_trace(go.Scatter(
        x=[exit_time],
        y=[exit_price],
        mode='markers',
        name='Close',
        marker=dict(
            symbol='x',
            size=14,
            color='#000000',
            line=dict(color='#ffffff', width=1)
        ),
        hovertemplate='<b>Close</b><br>%{x}<br>Price: %{y:.4f}<extra></extra>',
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
        hoverlabel=dict(bgcolor="rgba(255,255,255,0.9)", font=dict(size=11)),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", zeroline=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)", zeroline=False),
        margin=dict(t=45, b=60, l=60, r=20)
    )
    return fig
