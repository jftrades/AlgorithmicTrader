from dash import dcc
import plotly.graph_objects as go
import pandas as pd

from core.visualizing.dashboard.charts import (
    build_price_chart,
    add_trade_visualization,
    build_indicator_figure
)
from core.visualizing.dashboard.components import (
    get_default_trade_details,
    get_default_trade_details_with_message,
    create_trade_details_content,
    create_metrics_table
)
from .helpers import extract_collector_data, iter_indicator_groups

def _handle_trade_click_single(state, trades_df, clickData):
    if not clickData or not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
        return get_default_trade_details()
    pt = next((p for p in clickData.get("points", []) if "customdata" in p), None)
    if not pt:
        return get_default_trade_details_with_message()
    idx = pt.get("customdata")
    if isinstance(idx, (list, tuple)) and len(idx) == 1:
        idx = idx[0]
    if isinstance(idx, (list, tuple)) and len(idx) == 1:
        idx = idx[0]
    if idx in trades_df.index:
        state["selected_trade_index"] = idx
        return create_trade_details_content(trades_df.loc[idx])
    return get_default_trade_details_with_message()

def _single_instrument(state, repo, instrument, chart_mode, x_range, clickData):
    coll = state["collectors"].get(instrument)
    bars, trades_df, indicators = extract_collector_data(coll)
    trade_details = _handle_trade_click_single(state, trades_df, clickData)

    try:
        price_fig = build_price_chart(
            bars,
            indicators,
            trades_df,
            state.get("selected_trade_index"),
            display_mode=(chart_mode or "OHLC")
        )
        price_fig.update_layout(uirevision="linked-range")
        if x_range:
            price_fig.update_xaxes(range=x_range, autorange=False)
        else:
            price_fig.update_xaxes(autorange=True)
    except Exception as e:
        price_fig = go.Figure().update_layout(title=f"Chart error: {e}")

    indicator_children = []
    for pid, lst in sorted(iter_indicator_groups(indicators).items()):
        fig_ind = build_indicator_figure(lst)
        if x_range:
            fig_ind.update_xaxes(range=x_range, autorange=False)
        fig_ind.update_layout(uirevision="linked-range")
        indicator_children.append(
            dcc.Graph(id=f"indicators-plot-{pid}", figure=fig_ind,
                      style={"height": "300px", "marginBottom": "10px"})
        )

    metrics, nautilus = {}, []
    if instrument and hasattr(repo, "load_metrics"):
        try:
            loaded = repo.load_metrics(instrument)
            if loaded:
                metrics, nautilus = loaded
        except Exception:
            pass
    metrics_div = create_metrics_table(metrics, nautilus)
    return price_fig, indicator_children, metrics_div, trade_details

def _multi_instrument(state, repo, instruments, chart_mode, x_range, color_map, clickData):
    selected_multi = state.get("selected_trade_index") if isinstance(state.get("selected_trade_index"), tuple) else None

    price_fig = go.Figure()
    candle_indices, line_indices, axis_ids = [], [], []
    trades_per_instrument = {}

    for i, inst in enumerate(instruments):
        coll = state["collectors"].get(inst)
        bars, trades_df, _ = extract_collector_data(coll)
        trades_per_instrument[inst] = (bars, trades_df)
        if not (isinstance(bars, pd.DataFrame) and not bars.empty):
            continue
        axis_id = 'y' if i == 0 else f'y{i+1}'
        axis_ids.append(axis_id)
        price_fig.add_trace(go.Candlestick(
            x=bars["timestamp"],
            open=bars["open"], high=bars["high"],
            low=bars["low"], close=bars["close"],
            name=f"{inst} OHLC",
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
            increasing_fillcolor='#26a69a',
            decreasing_fillcolor='#ef5350',
            opacity=1.0,
            showlegend=True,
            yaxis=axis_id,
            visible=(chart_mode == "OHLC")
        ))
        price_fig.data[-1].uid = f"candle_{inst}"
        candle_indices.append(len(price_fig.data) - 1)
        price_fig.add_trace(go.Scatter(
            x=bars["timestamp"],
            y=bars["close"],
            mode="lines",
            name=f"{inst} Close",
            line=dict(color=color_map.get(inst, "#000000"), width=2),
            hovertemplate=f"<b>{inst}</b><br>%{{x}}<br>Close: %{{y:.4f}}<extra></extra>",
            visible=(chart_mode == "GRAPH"),
            yaxis=axis_id
        ))
        price_fig.data[-1].uid = f"line_{inst}"
        line_indices.append(len(price_fig.data) - 1)

    # Trades (BUY / SHORT) pro Instrument
    for i, inst in enumerate(instruments):
        bars, trades_df = trades_per_instrument.get(inst, (None, None))
        if not (isinstance(trades_df, pd.DataFrame) and not trades_df.empty):
            continue
        axis_id = 'y' if i == 0 else f'y{i+1}'
        buy = trades_df[trades_df["action"] == "BUY"]
        short = trades_df[trades_df["action"] == "SHORT"]

        def add(points, action, symbol, color):
            if points.empty:
                return
            selected_idx = None
            if selected_multi and len(selected_multi) == 2 and selected_multi[0] == inst:
                selected_idx = selected_multi[1]
            normal = points.index.difference([selected_idx]) if selected_idx is not None else points.index
            if len(normal) > 0:
                sub = points.loc[normal]
                price_fig.add_trace(go.Scatter(
                    x=sub["timestamp"],
                    y=sub.get("open_price_actual", sub.get("price_actual", 0)),
                    mode="markers",
                    name=f"{inst} {action}",
                    marker=dict(symbol=symbol, size=12, color=color,
                                line=dict(color="#ffffff", width=1)),
                    customdata=[[inst, idx] for idx in sub.index],
                    hovertemplate=f"<b>{inst} {action}</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>",
                    yaxis=axis_id,
                    showlegend=True
                ))
            if selected_idx is not None and selected_idx in points.index:
                srow = points.loc[[selected_idx]]
                price_fig.add_trace(go.Scatter(
                    x=srow["timestamp"],
                    y=srow.get("open_price_actual", srow.get("price_actual", 0)),
                    mode="markers",
                    name=f"{inst} {action} (Selected)",
                    marker=dict(symbol=symbol, size=18, color=color,
                                line=dict(color="#222", width=2)),
                    customdata=[[inst, selected_idx]],
                    hovertemplate=f"<b>{inst} {action} (Selected)</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>",
                    yaxis=axis_id,
                    showlegend=False
                ))

        add(buy, "BUY", "triangle-up", "#28a745")
        add(short, "SHORT", "triangle-down", "#dc3545")

    # Trade Click
    trade_details = get_default_trade_details()
    if clickData:
        pt = next((p for p in clickData.get("points", []) if "customdata" in p), None)
        if pt:
            cd = pt.get("customdata")
            if isinstance(cd, (list, tuple)) and len(cd) == 2 and not isinstance(cd[0], (list, tuple)):
                inst_clicked, idx_clicked = cd
            elif isinstance(cd, (list, tuple)) and len(cd) == 1 and isinstance(cd[0], (list, tuple)) and len(cd[0]) == 2:
                inst_clicked, idx_clicked = cd[0]
            else:
                inst_clicked = idx_clicked = None
            if inst_clicked in trades_per_instrument:
                _bars, tdf = trades_per_instrument[inst_clicked]
                if isinstance(tdf, pd.DataFrame) and idx_clicked in tdf.index:
                    state["selected_trade_index"] = (inst_clicked, idx_clicked)
                    trade_details = create_trade_details_content(tdf.loc[idx_clicked])
                    try:
                        add_trade_visualization(price_fig, tdf, _bars, idx_clicked)
                    except Exception as e:
                        print(f"[WARN] add_trade_visualization multi-inst failed: {e}")
    else:
        if selected_multi and len(selected_multi) == 2:
            inst_sel, idx_sel = selected_multi
            _bars, tdf = trades_per_instrument.get(inst_sel, (None, None))
            if isinstance(tdf, pd.DataFrame) and idx_sel in tdf.index:
                try:
                    add_trade_visualization(price_fig, tdf, _bars, idx_sel)
                except Exception as e:
                    print(f"[WARN] persist add_trade_visualization multi-inst failed: {e}")

    # Achsenlayout
    axis_layout = {}
    for i, axis_id in enumerate(axis_ids):
        inst = instruments[i]
        axis_key = 'yaxis' if axis_id == 'y' else f'yaxis{i+1}'
        if i == 0:
            axis_layout[axis_key] = dict(
                title=dict(text=inst, font=dict(color=color_map.get(inst, "#000"))),
                tickfont=dict(color=color_map.get(inst, "#000")),
                showgrid=False, zeroline=False, showline=True,
                linecolor=color_map.get(inst, "#000")
            )
        else:
            pos = 1.0 - (i - 1) * 0.05
            axis_layout[axis_key] = dict(
                title=dict(text=inst, font=dict(color=color_map.get(inst, "#000"), size=11)),
                tickfont=dict(color=color_map.get(inst, "#000"), size=10),
                overlaying='y', side='right', position=max(0.0, pos),
                showgrid=False, zeroline=False, showline=True,
                linecolor=color_map.get(inst, "#000")
            )
    price_fig.update_layout(**axis_layout)

    # OHLC / Graph Buttons
    total = len(price_fig.data)
    candle_set = set(candle_indices)
    line_set = set(line_indices)
    current_vis = [(t.visible if t.visible is not None else True) for t in price_fig.data]
    vis_ohlc, vis_graph = [], []
    for i in range(total):
        if i in candle_set:
            vis_ohlc.append(True); vis_graph.append(False)
        elif i in line_set:
            vis_ohlc.append(False); vis_graph.append(True)
        else:
            vis_ohlc.append(current_vis[i]); vis_graph.append(current_vis[i])
    price_fig.update_layout(
        updatemenus=[dict(
            type='buttons',
            direction='right',
            x=1.0, xanchor='right',
            y=0.995, yanchor='top',
            pad=dict(r=2, t=2, b=2, l=2),
            bgcolor='rgba(255,255,255,0.40)',
            bordercolor='rgba(0,0,0,0.12)',
            borderwidth=1,
            font=dict(size=9),
            buttons=[
                dict(label='OHLC', method='update', args=[{'visible': vis_ohlc}]),
                dict(label='Graph', method='update', args=[{'visible': vis_graph}])
            ]
        )],
        template="plotly_white",
        hovermode="x unified",
        margin=dict(t=30, b=50, l=60, r=40),
        xaxis=dict(rangeslider=dict(visible=False)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0)
    )
    price_fig.update_layout(uirevision="linked-range")
    if x_range:
        price_fig.update_xaxes(range=x_range, autorange=False)

    # Indicator-Plots (kombiniert)
    indicator_children = []
    plot_groups = {}
    for inst in instruments:
        coll = state["collectors"].get(inst)
        _, _, indicators = extract_collector_data(coll)
        for name, df in (indicators or {}).items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                pid = int(df.get("plot_id", [0])[0]) if "plot_id" in df.columns else 0
                if pid >= 1:
                    plot_groups.setdefault(pid, []).append((inst, name, df))

    for pid, lst in sorted(plot_groups.items()):
        fig_ind = go.Figure()
        indicator_names = []
        for inst_, name, df in lst:
            fig_ind.add_trace(go.Scatter(
                x=df["timestamp"],
                y=df["value"],
                mode="lines",
                name=f"{inst_}:{name}",
                line=dict(color=color_map.get(inst_, "#000000"), width=2),
                hovertemplate=f"<b>{inst_}:{name}</b><br>%{{x}}<br>%{{y:.4f}}<extra></extra>"
            ))
            indicator_names.append(f"{inst_}:{name}")
        if not indicator_names:
            continue
        base_names = [n.split(":", 1)[-1] for n in indicator_names]
        unique_base = list(dict.fromkeys(base_names))
        if len(unique_base) == 1:
            title_text = unique_base[0]
        elif len(indicator_names) <= 3:
            title_text = " | ".join(indicator_names)
        else:
            title_text = f"{indicator_names[0]} + {len(indicator_names)-1} more"
        fig_ind.update_layout(
            template="plotly_white",
            margin=dict(t=55, b=40, l=50, r=15),
            title=dict(
                text=title_text,
                x=0.01, y=0.98, xanchor="left", yanchor="top",
                font=dict(size=14, color="#4a5568")
            ),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="top", y=1.0, x=0.0)
        )
        if x_range:
            fig_ind.update_xaxes(range=x_range, autorange=False)
        fig_ind.update_layout(uirevision="linked-range")
        indicator_children.append(
            dcc.Graph(id=f"indicators-plot-{pid}",
                      figure=fig_ind,
                      style={"height": "300px", "marginBottom": "10px"})
        )

    metrics, nautilus = {}, []
    primary = instruments[0] if instruments else None
    if primary and hasattr(repo, "load_metrics"):
        try:
            loaded = repo.load_metrics(primary)
            if loaded:
                metrics, nautilus = loaded
        except Exception:
            pass
    metrics_div = create_metrics_table(metrics, nautilus)
    return price_fig, indicator_children, metrics_div, trade_details

def build_single_run_view(state, repo, instruments, clickData, chart_mode, x_range, color_map):
    """Dispatcher: Single-Run mit 1 oder mehreren Instrumenten."""
    if not instruments:
        return (go.Figure().update_layout(title="No instrument selected"),
                [], create_metrics_table({}, []), get_default_trade_details())
    if len(instruments) == 1:
        return _single_instrument(
            state=state,
            repo=repo,
            instrument=instruments[0],
            chart_mode=chart_mode,
            x_range=x_range,
            clickData=clickData
        )
    return _multi_instrument(
        state=state,
        repo=repo,
        instruments=instruments,
        chart_mode=chart_mode,
        x_range=x_range,
        color_map=color_map,
        clickData=clickData
    )
