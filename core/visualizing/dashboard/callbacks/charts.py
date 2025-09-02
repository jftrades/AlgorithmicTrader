from dash import Input, Output, State, html
from dash.exceptions import PreventUpdate
from dash import callback_context
from dash import ALL  # für Pattern-Matching Outputs

from core.visualizing.dashboard.colors import get_color_map
from core.visualizing.dashboard.components import get_default_trade_details  # hinzugefügt
# removed: create_metrics_table (unused)
# removed: Path, os, traceback (unused)
from .chart.helpers import compute_x_range
from .chart.multi_run import build_multi_run_view
from .chart.single_run import build_single_run_view
import pandas as pd

def register_chart_callbacks(app, repo, state):

    # --- Timeframe options helper callback (populates timeframe-dropdown) ---
    @app.callback(
        [Output("timeframe-dropdown", "options"),
         Output("timeframe-dropdown", "value")],
        Input("collector-dropdown", "value"),
        State("timeframe-dropdown", "value"),
        prevent_initial_call=False
    )
    def update_timeframe_dropdown(sel_values, current_value):
        vals = sel_values or []
        if isinstance(vals, str):
            vals = [vals]
        if not vals:
            return [], None
        primary = vals[0]
        coll = (state.get("collectors") or {}).get(primary)
        variants = None
        if isinstance(coll, dict):
            variants = coll.get("bars_variants")
        if not variants:
            return [{'label': 'DEFAULT', 'value': '__default__'}], '__default__'
        # rank by seconds
        import re
        def tf_seconds(tf: str):
            m = re.match(r"(\d+)\s*([smhdSMHD])", str(tf))
            if not m:
                return -1
            v = int(m.group(1))
            mult = {'s':1,'m':60,'h':3600,'d':86400}.get(m.group(2).lower(), 1)
            return v * mult
        ordered = sorted(variants.keys(), key=tf_seconds)
        default_tf = ordered[-1]  # highest timeframe
        if current_value in ordered:
            default_tf = current_value
        return [{'label': tf, 'value': tf} for tf in ordered], default_tf

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

        candle_idxs, line_idxs = [], []
        for i, tr in enumerate(data):
            ttype = tr.get("type")
            uid = tr.get("uid") or ""
            name = str(tr.get("name", ""))
            if ttype == "candlestick" or uid.startswith("candle_") or uid == "trace_ohlc":
                candle_idxs.append(i)
            elif (ttype == "scatter" and name.endswith("Close")) or uid.startswith("line_") or uid == "trace_graph":
                line_idxs.append(i)

        if not candle_idxs or not line_idxs:
            raise PreventUpdate
        if not any(i in candle_idxs or i in line_idxs for i in indices):
            raise PreventUpdate

        def vis_after(i):
            if i in indices:
                v = change['visible'][indices.index(i)]
            else:
                v = data[i].get('visible', True)
            return False if v in (False, 'legendonly') else True

        any_candle = any(vis_after(i) for i in candle_idxs)
        any_line = any(vis_after(i) for i in line_idxs)

        if any_candle and not any_line:
            new_mode = "OHLC"
        elif any_line and not any_candle:
            new_mode = "GRAPH"
        else:
            raise PreventUpdate
        if new_mode == current_mode:
            raise PreventUpdate
        return new_mode

    # REPLACED: merged slider init + display update (remove old two callbacks)
    @app.callback(
        [
            Output("time-range-slider", "min"),
            Output("time-range-slider", "max"),
            Output("time-range-slider", "value"),
            Output("time-range-slider", "marks"),
            Output("time-range-display", "children"),
            Output("time-slider-store", "data"),          # NEW
        ],
        [
            Input("collector-dropdown", "value"),
            Input("timeframe-dropdown", "value"),
            Input("time-range-slider", "value"),
        ],
        State("time-slider-store", "data"),               # NEW (previous selection)
        prevent_initial_call=False
    )
    def update_time_slider(sel_values, timeframe_value, slider_value, stored_value):
        # Determine trigger
        trig = None
        if callback_context.triggered:
            trig = callback_context.triggered[0]["prop_id"].split(".")[0]

        vals = sel_values or []
        if isinstance(vals, str):
            vals = [vals]
        if not vals:
            state["time_slider_ts"] = []
            return 0, 1, [0, 1], {}, "", None
        primary = vals[0]
        coll = (state.get("collectors") or {}).get(primary) or {}

        # Pick bars per timeframe
        bars = None
        if timeframe_value and timeframe_value != "__default__":
            bars = (coll.get("bars_variants") or {}).get(timeframe_value)
        if bars is None:
            bars = coll.get("bars_df")

        if not isinstance(bars, pd.DataFrame) or bars.empty or "timestamp" not in bars.columns:
            state["time_slider_ts"] = []
            return 0, 1, [0, 1], {}, "", None

        ts = pd.to_datetime(bars["timestamp"], errors="coerce").dropna()
        if ts.empty:
            state["time_slider_ts"] = []
            return 0, 1, [0, 1], {}, "", None

        ts_list = ts.reset_index(drop=True)
        state["time_slider_ts"] = ts_list

        min_idx = 0
        max_idx = len(ts_list) - 1

        def nearest_index(ts_val):
            try:
                pos = int(ts_list.searchsorted(ts_val, side="left"))
                if pos >= len(ts_list):
                    pos = len(ts_list) - 1
                if pos < 0:
                    pos = 0
                if pos > 0:
                    prev_diff = abs(ts_val - ts_list.iloc[pos - 1])
                    cur_diff = abs(ts_list.iloc[pos] - ts_val)
                    if prev_diff <= cur_diff:
                        return pos - 1
                return pos
            except Exception:
                return None

        # Default full range
        current_value = [min_idx, max_idx]

        restored_from_store = False
        original_store = stored_value  # keep to avoid overwriting on failed restore

        if trig == "time-range-slider" and isinstance(slider_value, (list, tuple)) and len(slider_value) == 2:
            a, b = int(slider_value[0]), int(slider_value[1])
            if 0 <= a < b <= max_idx:
                current_value = [a, b]
        else:
            # Any non-slider trigger (collector / timeframe) -> try restore from stored_value
            start_ts = end_ts = None
            if isinstance(stored_value, dict):
                ts_pair = stored_value.get("ts")
                if isinstance(ts_pair, (list, tuple)) and len(ts_pair) == 2:
                    try:
                        start_ts = pd.to_datetime(ts_pair[0])
                        end_ts = pd.to_datetime(ts_pair[1])
                    except Exception:
                        start_ts = end_ts = None
                # Fallback to indices only if timestamps missing
                if (start_ts is None or end_ts is None) and isinstance(stored_value.get("idx"), (list, tuple)) and len(stored_value["idx"]) == 2:
                    ia, ib = stored_value["idx"]
                    if 0 <= int(ia) < int(ib) <= max_idx:
                        current_value = [int(ia), int(ib)]
                        restored_from_store = True
            elif isinstance(stored_value, (list, tuple)) and len(stored_value) == 2:
                ia, ib = stored_value
                if 0 <= int(ia) < int(ib) <= max_idx:
                    current_value = [int(ia), int(ib)]
                    restored_from_store = True

            if start_ts is not None and end_ts is not None and start_ts < end_ts:
                ia = nearest_index(start_ts)
                ib = nearest_index(end_ts)
                if ia is not None and ib is not None and ia < ib:
                    current_value = [ia, ib]
                    restored_from_store = True

        # Clamp
        a, b = current_value
        if not (0 <= a < b <= max_idx):
            current_value = [min_idx, max_idx]
            a, b = current_value
            if trig == "timeframe-dropdown":
                # If timeframe change caused invalid window -> keep previous store (do NOT overwrite)
                s_dt = ts_list.iloc[min_idx]
                e_dt = ts_list.iloc[max_idx]
                disp = f"{s_dt.strftime('%d %b %H:%M')} – {e_dt.strftime('%d %b %H:%M')}"
                # keep original store (may still hold meaningful timestamps for another timeframe)
                return min_idx, max_idx, current_value, {min_idx: s_dt.strftime('%Y-%m-%d %H:%M'), max_idx: e_dt.strftime('%Y-%m-%d %H:%M')}, disp, original_store

        # Marks (start & end)
        def fmt_label(dt):
            return dt.strftime("%Y-%m-%d %H:%M")
        start_dt = ts_list.iloc[min_idx]
        end_dt = ts_list.iloc[max_idx]
        marks = {min_idx: fmt_label(start_dt), max_idx: fmt_label(end_dt)}

        s_dt = ts_list.iloc[a]
        e_dt = ts_list.iloc[b]

        def compact_span(xa, xb):
            if xa.date() == xb.date():
                return f"{xa.strftime('%d %b %H:%M')} – {xb.strftime('%H:%M')}"
            if xa.year == xb.year and xa.month == xb.month:
                return f"{xa.strftime('%d')}–{xb.strftime('%d %b')} {xb.strftime('%H:%M')}"
            if xa.year == xb.year:
                return f"{xa.strftime('%d %b')} – {xb.strftime('%d %b')} {xb.strftime('%H:%M')}"
            return f"{xa.strftime('%Y-%m-%d')} → {xb.strftime('%Y-%m-%d')}"
        disp = compact_span(s_dt, e_dt)

        # Build new store payload ONLY if:
        #  - user moved slider, or
        #  - restore succeeded, or
        #  - there was no previous store
        if trig == "time-range-slider" or restored_from_store or not stored_value:
            store_payload = {
                "idx": current_value,
                "ts": [s_dt.isoformat(), e_dt.isoformat()]
            }
        else:
            # Keep previous store on timeframe change if restore failed
            store_payload = stored_value

        return min_idx, max_idx, current_value, marks, disp, store_payload

    # NEW: toggle trades visibility
    @app.callback(
        [Output("show-trades-store", "data"),
         Output("toggle-trades-btn", "children"),
         Output("toggle-trades-btn", "style")],
        Input("toggle-trades-btn", "n_clicks"),
        State("show-trades-store", "data"),
        prevent_initial_call=False
    )
    def toggle_trades(n, current):
        show = True if current is None else bool(current)
        if n:
            show = not (n % 2)
        label = "Trades" if show else "Trades Off"
        style = {
            'backgroundColor': '#2563eb' if show else '#9ca3af',
            'color': '#ffffff'
        }
        return show, label, style

    @app.callback(
        [
            Output("price-chart", "figure"),
            Output("indicators-container", "children"),
            Output("metrics-panel", "children"),
            Output("trade-details-panel", "children")
        ],
        [
            Input("collector-dropdown", "value"),
            Input("timeframe-dropdown", "value"),      # NEW timeframe input
            Input("refresh-btn", "n_clicks"),
            Input("price-chart", "clickData"),
            Input("price-chart", "relayoutData"),
            Input("show-trades-store", "data"),          # NEW
            Input("time-range-slider", "value"),          # NEW slider
            Input("selected-run-store", "data"),          # CHANGED: was State
        ],
        State("price-chart-mode", "data"),
        prevent_initial_call=False
    )
    def unified(sel_values, timeframe_value, _n, clickData, relayoutData, show_trades, slider_value, selected_run_store, chart_mode):
        # Persist timeframe in state
        state["selected_timeframe"] = timeframe_value
        # Normalize instruments
        if sel_values is None:
            sel_values = []
        elif isinstance(sel_values, str):
            sel_values = [sel_values]
        if not sel_values and state.get("collectors"):
            first = next(iter(state["collectors"]), None)
            if first:
                sel_values = [first]

        # Ensure runs_cache dict exists
        if "runs_cache" not in state or not isinstance(state["runs_cache"], dict):
            state["runs_cache"] = {}

        # --- SIMPLIFIED AND CORRECTED RUN SELECTION LOGIC ---
        # The selected_run_store is the single source of truth.
        if isinstance(selected_run_store, list):
            active_runs = [str(r) for r in selected_run_store if r]
        elif isinstance(selected_run_store, (str, int)):
            active_runs = [str(selected_run_store)]
        else:
            active_runs = []
        
        state["active_runs"] = active_runs
        # --- END OF SIMPLIFIED LOGIC ---

        # Reload any missing run objects (e.g., if app was restarted)
        for rid in state["active_runs"]:
            if rid not in state["runs_cache"]:
                try:
                    rd = repo.load_specific_run(rid)
                    state["runs_cache"][rid] = rd
                except Exception:
                    pass

        # This block is now redundant as menu.py handles collector sync, but keep as a fallback.
        if active_runs:
            first_rid = active_runs[0]
            if state.get("current_collectors_run_id") != first_rid:
                # load run object if missing
                if first_rid not in state["runs_cache"]:
                    try:
                        state["runs_cache"][first_rid] = repo.load_specific_run(first_rid)
                    except Exception:
                        pass
                run_obj = state["runs_cache"].get(first_rid)
                if run_obj:
                    new_collectors = run_obj.collectors or {}
                    if new_collectors:
                        state["collectors"] = new_collectors
                        # pick previously selected collector if still present else run's selected else first key
                        prev = state.get("selected_collector")
                        if not prev or prev not in new_collectors:
                            state["selected_collector"] = (
                                run_obj.selected
                                or (prev if prev in new_collectors else next(iter(new_collectors), None))
                            )
                        # reset trade selection when switching run
                        state["selected_trade_index"] = None
                        state["current_collectors_run_id"] = first_rid
                # else: keep old collectors (run failed to load)
        else:
            # no active runs -> clear collectors
            if state.get("collectors"):
                state["collectors"] = {}
                state["selected_collector"] = None
                state["current_collectors_run_id"] = None
                state["selected_trade_index"] = None

        if not sel_values:
            from plotly.graph_objects import Figure
            empty_fig = Figure().update_layout(title="No instrument")
            return empty_fig, [], html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'}), get_default_trade_details()

        primary = sel_values[0]
        if primary != state.get("selected_collector") and primary in state.get("collectors", {}):
            state["selected_collector"] = primary
            state["selected_trade_index"] = None

        # Interpret index-based slider into timestamp window
        x_window = None
        ts_list = state.get("time_slider_ts")  # pandas Series of timestamps
        if (
            isinstance(slider_value, (list, tuple))
            and len(slider_value) == 2
            and hasattr(ts_list, "iloc")
            and len(ts_list) > 0
        ):
            try:
                a, b = int(slider_value[0]), int(slider_value[1])
                if 0 <= a < b < len(ts_list):
                    start_ts = ts_list.iloc[a]
                    end_ts = ts_list.iloc[b]
                    if pd.notna(start_ts) and pd.notna(end_ts) and start_ts < end_ts:
                        x_window = (start_ts, end_ts)
            except Exception:
                x_window = None
        state["selected_time_window"] = x_window

        # Compute x_range (zoom) but override if slider window present
        from dash import callback_context as _ctx
        trigger_id = (_ctx.triggered[0]["prop_id"].split(".")[0] if _ctx.triggered else None)

        # EARLY-ZOOM-HANDLING (NEU):
        # Wenn nur der Price-Chart (relayoutData) getriggert hat (Pan/Zoom) -> kein kompletter Rebuild.
        # Erkennung: trigger_id == "price-chart" UND relayoutData enthält mindestens ein "xaxis." Key.
        # FIX: Previously this blocked processing of clickData when both relayoutData and clickData fired
        # (common after zooming then clicking a marker). We now skip rebuild ONLY if relayoutData is
        # the sole trigger (pure pan/zoom). If a click occurred, we continue so trade selection works.
        if isinstance(relayoutData, dict) and any(k.startswith("xaxis.") for k in relayoutData.keys()):
            triggered_props = [_t.get("prop_id") for _t in _ctx.triggered] if _ctx.triggered else []
            only_relayout = (
                len(triggered_props) > 0
                and all(p.startswith("price-chart.relayoutData") for p in triggered_props)
            )
            if only_relayout:
                xr = compute_x_range(relayoutData)
                if xr:
                    state["last_x_range"] = xr
                raise PreventUpdate

        x_range = None  # wird weiter unten gesetzt (nicht mehr vorher aus relayoutData bei reinem Zoom)

        # Hilfsfunktion: nachträgliche X-Range-Synchronisierung aller Indicator Charts
        def _apply_range_sync(indicator_children, xr):
            # Wenn dieser Code noch ausgeführt wird, handelt es sich NICHT um reines Zoom/Pan
            if not xr:
                return indicator_children
            for comp in indicator_children:
                try:
                    fig = getattr(comp, "figure", None)
                    if fig and hasattr(fig, "update_xaxes"):
                        fig.update_xaxes(range=xr, autorange=False, constrain="domain", rangebreaks=[])
                        fig.update_layout(uirevision="linked-range")
                except Exception:
                    continue
            return indicator_children

        # Bestimme x_range nun ausschließlich aus:
        # 1) Slider Fenster
        # 2) Gespeicherter state["last_x_range"] (falls vorhanden)
        if x_window:
            x_range = [x_window[0], x_window[1]]
            state["last_x_range"] = x_range
        elif "last_x_range" in state:
            x_range = state["last_x_range"]

        # Force multi-run mode if we still have >1 preserved
        multi_run_mode = len(active_runs) > 1
        run_id = active_runs[0] if active_runs else None
        color_map = get_color_map(sel_values)

        # Multi-run
        if multi_run_mode:
            price_fig, indicator_children, metrics_children, trade_details = build_multi_run_view(
                state=state,
                repo=repo,
                instruments=sel_values,
                active_runs=active_runs,
                clickData=clickData,
                chart_mode=chart_mode,
                x_range=x_range,
                color_map=color_map,
                timeframe=(None if timeframe_value in (None, '__default__') else timeframe_value),
                show_trades=bool(show_trades),
                x_window=x_window  # NEW
            )
            # unify chart wrapper classes (added)
            for c in indicator_children:
                if hasattr(c, "props") and "className" not in getattr(c, "props", {}):
                    c.className = "indicator-chart"
            return price_fig, indicator_children, metrics_children, trade_details

        # Single run
        price_fig, indicator_children, metrics_children, trade_details = build_single_run_view(
            state=state,
            repo=repo,
            instruments=sel_values,
            clickData=clickData,
            chart_mode=chart_mode,
            x_range=x_range,
            color_map=color_map,
            run_id=run_id,
            timeframe=(None if timeframe_value in (None, '__default__') else timeframe_value),
            show_trades=bool(show_trades),
            x_window=x_window  # NEW
        )
        for c in indicator_children:
            if hasattr(c, "props") and "className" not in getattr(c, "props", {}):
                c.className = "indicator-chart"
        return price_fig, indicator_children, metrics_children, trade_details

    # --- NEU: Reine X-Achsen-Synchronisierung (leichtgewichtig) ---
    @app.callback(
        Output({'type': 'indicator-graph', 'index': ALL}, 'figure'),
        [
            Input("price-chart", "relayoutData"),
            Input("collector-dropdown", "value"),          # bei Instrument-Wechsel erneut anwenden
            Input("timeframe-dropdown", "value"),          # bei TF-Wechsel erneut anwenden
        ],
        State({'type': 'indicator-graph', 'index': ALL}, 'figure'),
        prevent_initial_call=True
    )
    def sync_indicator_xaxis(relayoutData, _sel_instruments, _tf, figures):
        # Keine Indicator-Figuren -> nichts tun
        if not figures:
            raise PreventUpdate

        # Versuche Range aus relayoutData
        xr = compute_x_range(relayoutData) if isinstance(relayoutData, dict) else None

        # Fallback: vorhandene gespeicherte Range aus server-side state (falls vorhanden)
        if xr is None:
            xr = state.get("last_x_range")

        if xr is None or len(xr) != 2:
            raise PreventUpdate  # keine explizite Range -> nichts ändern

        start, end = xr
        out = []
        for fig in figures:
            try:
                # Sicherstellen, dass Layout-Strukturen existieren
                lay = fig.get("layout", {})
                xaxis = lay.get("xaxis", {})
                xaxis["range"] = [str(start), str(end)]
                xaxis["autorange"] = False
                lay["xaxis"] = xaxis
                # Persistenter Zoom
                lay["uirevision"] = "linked-range"
                fig["layout"] = lay
                out.append(fig)
            except Exception:
                out.append(fig)
        return out

