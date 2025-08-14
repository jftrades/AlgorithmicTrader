from dash import Input, Output, State, dcc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import pandas as pd

from core.visualizing.dashboard.charts import build_price_chart, build_indicator_figure, add_trade_visualization
from core.visualizing.dashboard.components import (
    get_default_trade_details,
    get_default_trade_details_with_message,
    create_trade_details_content,
    create_metrics_table
)
from core.visualizing.dashboard.colors import get_color_map
from core.visualizing.dashboard.multi_run_manager import (
    gather_multi_run_data,
    short_run_label,
    run_color_for_index
)

# NEU: deutlicherer Offset-Faktor für Multi-Run Marker (vorher effektiv 0.0008)
MULTI_RUN_MARKER_OFFSET_FACTOR = 0.004  # bei Bedarf weiter anheben

"""
Dash callback registration for price / indicator / metrics / trade details.
Imports figure builder helpers from core.visualizing.dashboard.charts.
Not to be confused with that module – this one only wires callbacks.
"""

def register_chart_callbacks(app, repo, state):
    # Generic extractor (Collector kann dict oder Objekt sein)
    def _extract(coll):
        if coll is None:
            return None, None, {}
        if isinstance(coll, dict):
            return (
                coll.get("bars_df"),
                coll.get("trades_df"),
                coll.get("indicators_df", {}) or coll.get("indicators", {})
            )
        return (
            getattr(coll, "bars_df", None),
            getattr(coll, "trades_df", None),
            getattr(coll, "indicators_df", {}) or getattr(coll, "indicators", {})
        )

    @app.callback(
        Output("price-chart-mode", "data"),
        Input("price-chart", "restyleData"),
        State("price-chart-mode", "data"),
        State("price-chart", "figure"),
        prevent_initial_call=True
    )
    def update_chart_mode(restyle_data, current_mode, fig_state):
        if not restyle_data or 'visible' not in restyle_data[0]:
            raise PreventUpdate
        change = restyle_data[0]
        indices = restyle_data[1] if len(restyle_data) > 1 else []
        data = fig_state.get("data", []) if isinstance(fig_state, dict) else []

        # Indizes für Candle / Line (multi + single) anhand Type / UID / Name
        candle_idxs = []
        line_idxs = []
        for i, tr in enumerate(data):
            ttype = tr.get("type")
            uid = tr.get("uid") or ""
            name = str(tr.get("name", ""))
            if ttype == "candlestick" or uid.startswith("candle_") or uid == "trace_ohlc":
                candle_idxs.append(i)
            elif (ttype == "scatter" and name.endswith("Close")) or uid.startswith("line_") or uid == "trace_graph":
                line_idxs.append(i)

        if not candle_idxs or not line_idxs:
            # Wenn einer der Sets nicht existiert -> kein Moduswechsel möglich
            raise PreventUpdate

        # Wurde überhaupt einer der relevanten Traces geändert?
        changed_relevant = any(i in candle_idxs or i in line_idxs for i in indices)
        if not changed_relevant:
            raise PreventUpdate  # ignorieren (z.B. Trade-Layer / Legend anderer Traces)

        # Sichtbarkeiten nach Änderung rekonstruieren
        def vis_after(i):
            if i in indices:
                v = change['visible'][indices.index(i)]
            else:
                v = data[i].get('visible', True)
            # Plotly: 'legendonly' gilt als nicht sichtbar
            return False if v in (False, 'legendonly') else True

        any_candle = any(vis_after(i) for i in candle_idxs)
        any_line = any(vis_after(i) for i in line_idxs)

        if any_candle and not any_line:
            new_mode = "OHLC"
        elif any_line and not any_candle:
            new_mode = "GRAPH"
        else:
            # Gemischte oder keine eindeutige Umschaltung -> ignorieren
            raise PreventUpdate

        if new_mode == current_mode:
            raise PreventUpdate
        return new_mode

    @app.callback(
        [
            Output("price-chart", "figure"),
            Output("indicators-container", "children"),
            Output("metrics-display", "children"),
            Output("trade-details-panel", "children")
        ],
        [
            Input("collector-dropdown", "value"),
            Input("refresh-btn", "n_clicks"),
            Input("price-chart", "clickData"),
            Input("price-chart", "relayoutData"),          # NEU: Zoom/Pan Events
        ],
        State("price-chart-mode", "data"),
        prevent_initial_call=False
    )
    def unified(sel_values, _n, clickData, relayoutData, chart_mode):
        # --- X-Range übernehmen (falls gezoomt) ---
        x_range = None
        if isinstance(relayoutData, dict):
            if 'xaxis.range[0]' in relayoutData and 'xaxis.range[1]' in relayoutData:
                x_range = [relayoutData['xaxis.range[0]'], relayoutData['xaxis.range[1]']]
            elif relayoutData.get('xaxis.autorange'):
                x_range = None
        # Auswahl normalisieren
        if isinstance(sel_values, str):
            sel_values = [sel_values]
        sel_values = sel_values or []
        if not sel_values and state["collectors"]:
            sel_values = [next(iter(state["collectors"]))]
        primary = sel_values[0] if sel_values else None

        # State aktualisieren
        if primary and primary in state["collectors"] and primary != state.get("selected_collector"):
            state["selected_collector"] = primary
            state["selected_trade_index"] = None
        elif state.get("selected_collector") is None and primary:
            state["selected_collector"] = primary

        multi_mode = len(sel_values) > 1
        color_map = get_color_map(sel_values)

        # NEU: Multi-Run Modus Erkennung
        active_runs = state.get("active_runs", []) or []
        multi_run_mode = len(active_runs) > 1
        # Für Multi-Run nur den ersten Collector nutzen (Bars identisch Vorgabe)
        if multi_run_mode and sel_values:
            sel_values = sel_values[:1]

        # Trade-Klick verarbeiten
        trade_details = get_default_trade_details()
        if clickData:
            def _scalarize(val):
                if isinstance(val, (list, tuple)):
                    # Flache Suche nach erstem hashbarem Element
                    for v in val:
                        if isinstance(v, (list, tuple)):
                            sv = _scalarize(v)
                            if sv is not None:
                                return sv
                        else:
                            return v
                    return None
                return val
            pt = next((p for p in clickData.get("points", []) if "customdata" in p), None)
            if pt:
                cd = pt.get("customdata")
                if multi_mode:
                    # Erwartet [instrument, index] – robust normalisieren
                    inst_clicked, tr_idx = None, None
                    if isinstance(cd, (list, tuple)):
                        if len(cd) == 2:
                            inst_clicked = cd[0]
                            tr_idx = _scalarize(cd[1])
                        elif len(cd) >= 1:
                            # Falls Struktur verschoben ist
                            inst_clicked = primary
                            tr_idx = _scalarize(cd[-1])
                    else:
                        inst_clicked = primary
                        tr_idx = _scalarize(cd)
                else:
                    inst_clicked = primary
                    tr_idx = _scalarize(cd)
                if inst_clicked in state["collectors"] and tr_idx is not None:
                    _, trades_df_clicked, _ = _extract(state["collectors"][inst_clicked])
                    try:
                        if isinstance(trades_df_clicked, pd.DataFrame) and tr_idx in trades_df_clicked.index:
                            state["selected_trade_index"] = (inst_clicked, tr_idx) if multi_mode else tr_idx
                            trade_details = create_trade_details_content(trades_df_clicked.loc[tr_idx])
                        else:
                            trade_details = get_default_trade_details_with_message()
                    except TypeError:
                        # Index unverträglich (z.B. immer noch Liste) -> ignorieren
                        trade_details = get_default_trade_details_with_message()
            # else kein customdata -> Hinweis

        # --- Multi-Run Overlays (ein Instrument, mehrere Runs) ---
        if multi_run_mode and sel_values:
            collector = sel_values[0]
            bars_df, indicators_per_run, trades_per_run = gather_multi_run_data(
                state["runs_cache"], active_runs, collector
            )

            # NEU (angepasst): Preis-Range für vertikale Offsets (stärkerer Faktor)
            price_span = 0.0
            if isinstance(bars_df, pd.DataFrame) and not bars_df.empty:
                try:
                    price_span = (bars_df["high"].max() - bars_df["low"].min()) or 0.0
                except Exception:
                    price_span = 0.0
            # vorher: price_span * 0.0008 -> jetzt deutlich größer + Fallback auf Mittelpreis
            if price_span > 0:
                base_offset_unit = price_span * MULTI_RUN_MARKER_OFFSET_FACTOR
            else:
                try:
                    avg_price = float(bars_df["close"].mean())
                except Exception:
                    avg_price = 1.0
                base_offset_unit = avg_price * (MULTI_RUN_MARKER_OFFSET_FACTOR * 0.5)

            # Optional: Mindestoffset erzwingen (verhindert Null bei sehr engem Markt)
            if base_offset_unit == 0:
                base_offset_unit = 1e-6

            # Basis-Preisfigur aus erster Run
            try:
                price_fig = build_price_chart(
                    bars_df,
                    {},
                    None,
                    None,
                    display_mode=(chart_mode or "OHLC")
                )
                price_fig.update_layout(uirevision="linked-range")
                if x_range:
                    price_fig.update_xaxes(range=x_range, autorange=False)
            except Exception as e:
                price_fig = go.Figure().update_layout(title=f"Chart error: {e}")

            # Vorhandene Auswahl (kann Tuple sein)
            selected_tuple = state.get("selected_trade_index") if isinstance(state.get("selected_trade_index"), tuple) else None

            # Trades pro Run overlayn (mit Offset + customdata [run_id, index])
            run_count = len(active_runs)
            for ridx, rid in enumerate(active_runs):
                trades_df = trades_per_run.get(rid)
                if not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
                    continue
                buy_color, short_color, _base_ind = run_color_for_index(ridx)
                offset = base_offset_unit * (ridx - (run_count - 1) / 2.0)

                def add_group(action, symbol, color):
                    sub = trades_df[trades_df["action"] == action]
                    if sub.empty:
                        return
                    first_index = sub.index[0]  # NEU: Referenz für Legend
                    for idx in sub.index:
                        # Optional NEU: zusätzlichen kleinen intra-run Offset um BUY/SHORT bei *gleichem* Timestamp minimal zu staffeln
                        # (keine Änderung wenn nicht nötig, lässt sich leicht entfernen)
                        row = sub.loc[idx]
                        timestamp_local_offset = 0.0
                        # z.B. BUY leicht höher, SHORT leicht tiefer (symmetrisch um Offset-Layer)
                        if action == "BUY":
                            timestamp_local_offset = base_offset_unit * 0.15
                        elif action == "SHORT":
                            timestamp_local_offset = -base_offset_unit * 0.15
                        y_val = (row.get("open_price_actual", row.get("price_actual", 0)) + offset + timestamp_local_offset)
                        is_sel = selected_tuple == (rid, idx)
                        price_fig.add_trace(go.Scatter(
                            x=[row["timestamp"]],
                            y=[y_val],
                            mode="markers",
                            name=f"{short_run_label(rid)} {action}" if idx == first_index else None,
                            marker=dict(
                                symbol=symbol,
                                size=18 if is_sel else 12,
                                color=color,
                                line=dict(color="#ffffff", width=2 if is_sel else 1)
                            ),
                            customdata=[[rid, idx]],
                            hovertemplate=(
                                f"<b>{short_run_label(rid)} {action}"
                                f"{' (Selected)' if is_sel else ''}</b><br>%{{x}}"
                                f"<br>Price: %{{y:.4f}}<extra></extra>"
                            ),
                            showlegend=bool(idx == first_index)  # NEU: explizit Python bool
                        ))

                add_group("BUY", "triangle-up", buy_color)
                add_group("SHORT", "triangle-down", short_color)

            # Trade-Selektion inkl. Linien
            trade_details = get_default_trade_details()
            if clickData:
                pt = next((p for p in clickData.get("points", []) if "customdata" in p), None)
                if pt:
                    cd = pt.get("customdata")
                    run_id_clicked, trade_idx_clicked = None, None
                    # customdata Varianten robust parsen
                    if isinstance(cd, (list, tuple)):
                        if len(cd) == 2 and not isinstance(cd[0], (list, tuple)):
                            run_id_clicked, trade_idx_clicked = cd[0], cd[1]
                        elif len(cd) == 1 and isinstance(cd[0], (list, tuple)) and len(cd[0]) == 2:
                            run_id_clicked, trade_idx_clicked = cd[0][0], cd[0][1]
                    if run_id_clicked is not None and trade_idx_clicked is not None:
                        tdf = trades_per_run.get(run_id_clicked)
                        if isinstance(tdf, pd.DataFrame) and trade_idx_clicked in tdf.index:
                            state["selected_trade_index"] = (run_id_clicked, trade_idx_clicked)
                            trade_details = create_trade_details_content(tdf.loc[trade_idx_clicked])
                            # Linien hinzufügen (bars_df aus erstem Run)
                            try:
                                add_trade_visualization(price_fig, tdf, bars_df, trade_idx_clicked)
                            except Exception as e:
                                print(f"[WARN] add_trade_visualization multi-run failed: {e}")

            # Falls bereits Auswahl existiert (ohne neuen Klick) -> Linien zeichnen
            if selected_tuple and not clickData:
                sel_run, sel_idx = selected_tuple
                tdf_sel = trades_per_run.get(sel_run)
                if isinstance(tdf_sel, pd.DataFrame) and sel_idx in tdf_sel.index:
                    try:
                        add_trade_visualization(price_fig, tdf_sel, bars_df, sel_idx)
                    except Exception as e:
                        print(f"[WARN] add_trade_visualization multi-run (persist) failed: {e}")

            # Indicators zusammenführen (alle Runs)
            indicator_children = []
            plot_groups = {}
            for ridx, rid in enumerate(active_runs):
                ind_map = indicators_per_run.get(rid, {}) or {}
                for name, df in ind_map.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        pid = int(df.get("plot_id", [0])[0]) if "plot_id" in df.columns else 0
                        if pid > 0:
                            plot_groups.setdefault(pid, []).append((ridx, rid, name, df))

            for pid, lst in sorted(plot_groups.items()):
                fig_ind = go.Figure()
                for ridx, rid, name, df in lst:
                    _, _, base_col = run_color_for_index(ridx)
                    fig_ind.add_trace(go.Scatter(
                        x=df["timestamp"],
                        y=df["value"],
                        mode="lines",
                        name=f"{short_run_label(rid)}:{name}",
                        line=dict(color=base_col, width=2),
                        hovertemplate=f"<b>{short_run_label(rid)}:{name}</b><br>%{{x}}<br>%{{y:.4f}}<extra></extra>"
                    ))
                fig_ind.update_layout(
                    template="plotly_white",
                    margin=dict(t=45, b=40, l=50, r=15),
                    title=dict(
                        text=f"Run Overlay: Plot {pid}",
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
                    dcc.Graph(id=f"multi-run-indicators-plot-{pid}", figure=fig_ind,
                              style={"height": "300px", "marginBottom": "10px"})
                )

            metrics_div = create_metrics_table({}, [])
            return price_fig, indicator_children, metrics_div, trade_details

        # Figure Aufbau
        if not multi_mode:
            coll = state["collectors"].get(primary)
            bars, trades_df, indicators = _extract(coll)
            try:
                price_fig = build_price_chart(
                    bars,
                    indicators,
                    trades_df,
                    (state["selected_trade_index"][1] if isinstance(state.get("selected_trade_index"), tuple) else state.get("selected_trade_index")),
                    display_mode=(chart_mode or "OHLC")
                )
                price_fig.update_layout(uirevision="linked-range")
                if x_range:
                    price_fig.update_xaxes(range=x_range, autorange=False)
                else:
                    price_fig.update_xaxes(autorange=True)
            except Exception as e:
                price_fig = go.Figure().update_layout(title=f"Chart error: {e}")
        else:
            price_fig = go.Figure()
            candle_indices = []
            line_indices = []
            axis_ids = []
            # Preis-Traces (Candlestick + Line für jedes Instrument)
            for i, inst in enumerate(sel_values):
                coll = state["collectors"].get(inst)
                bars, _, _ = _extract(coll)
                if not isinstance(bars, pd.DataFrame) or bars.empty:
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
                price_fig.data[-1].uid = f"candle_{inst}"  # NEU: stabile UID
                candle_indices.append(len(price_fig.data) - 1)

                price_fig.add_trace(go.Scatter(
                    x=bars["timestamp"],
                    y=bars["close"],
                    mode="lines",
                    name=f"{inst} Close",
                    line=dict(color=color_map[inst], width=2),
                    hovertemplate=f"<b>{inst}</b><br>Time: %{{x}}<br>Close: %{{y:.4f}}<extra></extra>",
                    visible=(chart_mode == "GRAPH"),
                    yaxis=axis_id
                ))
                price_fig.data[-1].uid = f"line_{inst}"  # NEU: stabile UID
                line_indices.append(len(price_fig.data) - 1)

            # Trades
            selected_multi = state.get("selected_trade_index") if isinstance(state.get("selected_trade_index"), tuple) else (None, None)
            for inst_index, inst in enumerate(sel_values):
                coll = state["collectors"].get(inst)
                _, trades_df, _ = _extract(coll)
                if not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
                    continue
                axis_id = 'y' if inst_index == 0 else f'y{inst_index+1}'
                for action, symbol, base_color in (("BUY", "triangle-up", "#28a745"), ("SHORT", "triangle-down", "#dc3545")):
                    sub = trades_df[trades_df["action"] == action]
                    if sub.empty:
                        continue
                    first = True
                    for idx, row in sub.iterrows():
                        is_sel = (inst, idx) == selected_multi
                        price_fig.add_trace(go.Scatter(
                            x=[row["timestamp"]],
                            y=[row.get("open_price_actual", row.get("price_actual", 0))],
                            mode="markers",
                            name=f"{inst} {action}" if first else None,
                            marker=dict(
                                symbol=symbol,
                                size=20 if is_sel else 12,
                                color=base_color,
                                line=dict(color="#ffffff", width=2 if is_sel else 1)
                            ),
                            customdata=[[inst, idx]],
                            hovertemplate=f"<b>{inst} {action}{' (Selected)' if is_sel else ''}</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>",
                            showlegend=first,
                            yaxis=axis_id
                        ))
                        first = False

            # Linien für selektierten Trade
            if isinstance(selected_multi, tuple):
                inst_sel, idx_sel = selected_multi
                if inst_sel in state["collectors"]:
                    coll_sel = state["collectors"][inst_sel]
                    bars_sel, trades_sel, _ = _extract(coll_sel)
                    if isinstance(trades_sel, pd.DataFrame) and idx_sel in trades_sel.index:
                        try:
                            before = len(price_fig.data)
                            add_trade_visualization(price_fig, trades_sel, bars_sel, idx_sel)
                            inst_idx = sel_values.index(inst_sel)
                            axis_id = 'y' if inst_idx == 0 else f'y{inst_idx+1}'
                            for tr in price_fig.data[before:]:
                                tr.update(yaxis=axis_id)
                        except Exception as e:
                            print(f"[WARN] add_trade_visualization failed: {e}")

            # Y-Achsen Layout
            axis_layout = {}
            for i, axis_id in enumerate(axis_ids):
                inst = sel_values[i]
                axis_key = 'yaxis' if axis_id == 'y' else f'yaxis{i+1}'
                if i == 0:
                    axis_layout[axis_key] = dict(
                        title=dict(text=inst, font=dict(color=color_map[inst])),
                        tickfont=dict(color=color_map[inst]),
                        showgrid=False, zeroline=False, showline=True,
                        linecolor=color_map[inst]
                    )
                else:
                    pos = 1.0 - (i - 1) * 0.05
                    axis_layout[axis_key] = dict(
                        title=dict(text=inst, font=dict(color=color_map[inst], size=11)),
                        tickfont=dict(color=color_map[inst], size=10),
                        overlaying='y', side='right', position=max(0.0, pos),
                        showgrid=False, zeroline=False, showline=True,
                        linecolor=color_map[inst]
                    )
            price_fig.update_layout(**axis_layout)

            # Sichtbarkeitsprofile für Buttons
            total = len(price_fig.data)
            candle_set = set(candle_indices)
            line_set = set(line_indices)
            current_vis = [ (t.visible if t.visible is not None else True) for t in price_fig.data ]
            vis_ohlc = []
            vis_graph = []
            for i in range(total):
                if i in candle_set:
                    vis_ohlc.append(True);  vis_graph.append(False)
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
                        dict(label='OHLC',  method='update', args=[{'visible': vis_ohlc}]),
                        dict(label='Graph', method='update', args=[{'visible': vis_graph}])
                    ]
                )],
                xaxis_title="Time",
                yaxis_title="Price",
                template="plotly_white",
                hovermode="x unified",
                margin=dict(t=30, b=50, l=60, r=40),
                xaxis=dict(rangeslider=dict(visible=False)),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0)
            )
            price_fig.update_layout(uirevision="linked-range")
            if x_range:
                price_fig.update_xaxes(range=x_range, autorange=False)

        # Indicators
        indicator_children = []
        if multi_mode:
            plot_groups = {}
            for inst in sel_values:
                coll = state["collectors"].get(inst)
                _, _, indicators = _extract(coll)
                for name, df in (indicators or {}).items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        pid = int(df.get("plot_id", [0])[0]) if "plot_id" in df.columns else 0
                        if pid >= 1:
                            plot_groups.setdefault(pid, []).append((inst, name, df))
            for pid, lst in sorted(plot_groups.items()):
                fig_ind = go.Figure()
                indicator_names = []
                for inst, name, df in lst:
                    try:
                        fig_ind.add_trace(go.Scatter(
                            x=df["timestamp"],
                            y=df["value"],
                            mode="lines",
                            name=f"{inst}:{name}",
                            line=dict(color=color_map[inst], width=2),
                            hovertemplate=f"<b>{inst}:{name}</b><br>%{{x}}<br>%{{y:.4f}}<extra></extra>"
                         ))
                        indicator_names.append(f"{inst}:{name}")
                    except Exception:
                        continue
                if not indicator_names:
                    continue
                # NEU: Basisnamen extrahieren (Teil nach letztem ':')
                base_names = [n.split(":", 1)[-1] for n in indicator_names]
                unique_base = list(dict.fromkeys(base_names))
                if len(unique_base) == 1:
                    title_text = unique_base[0]  # nur gemeinsamer Name, z.B. 'equity'
                elif len(indicator_names) <= 3:
                    title_text = " | ".join(indicator_names)
                else:
                    title_text = f"{indicator_names[0]} + {len(indicator_names)-1} more"
                fig_ind.update_layout(
                    template="plotly_white",
                    margin=dict(t=55, b=40, l=50, r=15),
                    title=dict(
                        text=title_text,
                        x=0.01,
                        y=0.98,
                        xanchor="left",
                        yanchor="top",
                        font=dict(size=14, color="#4a5568")
                    ),
                    hovermode="x unified",
                    legend=dict(
                        orientation="h",
                        yanchor="top",
                        y=1.00,
                        x=0.0
                    )
                )
                fig_ind.update_xaxes(range=x_range, autorange=False) if x_range else fig_ind.update_xaxes(autorange=True)
                fig_ind.update_layout(uirevision="linked-range")
                indicator_children.append(
                    dcc.Graph(id=f"indicators-plot-{pid}", figure=fig_ind, style={"height": "300px", "marginBottom": "10px"})
                )
        else:
            coll = state["collectors"].get(primary)
            _, _, indicators = _extract(coll)
            groups = {}
            for name, df in (indicators or {}).items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    pid = int(df["plot_id"].iloc[0]) if "plot_id" in df.columns else 0
                    if pid > 0:
                        groups.setdefault(pid, []).append((name, df))

            # NEU: Figures erst bauen, Range anwenden, dann Graph erzeugen
            indicator_children = []
            for pid, lst in sorted(groups.items()):
                fig_obj = build_indicator_figure(lst)
                if x_range:
                    fig_obj.update_xaxes(range=x_range, autorange=False)
                else:
                    fig_obj.update_xaxes(autorange=True)
                fig_obj.update_layout(uirevision="linked-range")
                indicator_children.append(
                    dcc.Graph(
                        id=f"indicators-plot-{pid}",
                        figure=fig_obj,
                        style={"height": "300px", "marginBottom": "10px"}  # <-- fehlende } ergänzt
                    )
                )
            # Entfernt: alte Kompakt-Liste + nachträgliche for-Schleife auf dcc.Graph Objekten

        # Metrics nur primäres Instrument
        metrics = {}
        nautilus_result = []
        if primary and hasattr(repo, "load_metrics"):
            try:
                loaded = repo.load_metrics(primary)
                if loaded:
                    metrics, nautilus_result = loaded
            except Exception:
                pass
        metrics_div = create_metrics_table(metrics, nautilus_result)

        return price_fig, indicator_children, metrics_div, trade_details
