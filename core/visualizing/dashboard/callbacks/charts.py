from dash import Input, Output, State, html
from dash.exceptions import PreventUpdate
from dash import callback_context

from core.visualizing.dashboard.colors import get_color_map
from core.visualizing.dashboard.components import get_default_trade_details  # hinzugefügt
from core.visualizing.dashboard.components import create_metrics_table
from pathlib import Path
import os
import traceback
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
        ],
        [
            Input("collector-dropdown", "value"),
            Input("timeframe-dropdown", "value"),
            Input("time-range-slider", "value"),          # user drag
        ],
        prevent_initial_call=False
    )
    def update_time_slider(sel_values, timeframe_value, slider_value):
        # Determine trigger
        trig = None
        if callback_context.triggered:
            trig = callback_context.triggered[0]["prop_id"].split(".")[0]

        vals = sel_values or []
        if isinstance(vals, str):
            vals = [vals]
        if not vals:
            state["time_slider_ts"] = []
            return 0, 1, [0, 1], {}, ""
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
            return 0, 1, [0, 1], {}, ""

        ts = pd.to_datetime(bars["timestamp"], errors="coerce").dropna()
        if ts.empty:
            state["time_slider_ts"] = []
            return 0, 1, [0, 1], {}, ""

        # Store full ordered timestamp list in state for unified callback
        ts_list = ts.reset_index(drop=True)
        state["time_slider_ts"] = ts_list

        min_idx = 0
        max_idx = len(ts_list) - 1

        # Decide current visible window
        if (
            trig == "time-range-slider"
            and isinstance(slider_value, (list, tuple))
            and len(slider_value) == 2
            and isinstance(slider_value[0], (int, float))
            and isinstance(slider_value[1], (int, float))
            and 0 <= int(slider_value[0]) < int(slider_value[1]) <= max_idx
        ):
            current_value = [int(slider_value[0]), int(slider_value[1])]
        else:
            # Reset on instrument/timeframe change
            current_value = [min_idx, max_idx]

        # Marks: only start & end to avoid clutter
        def fmt_label(dt):
            return dt.strftime("%Y-%m-%d %H:%M")
        start_dt = ts_list.iloc[min_idx]
        end_dt = ts_list.iloc[max_idx]
        marks = {
            min_idx: fmt_label(start_dt),
            max_idx: fmt_label(end_dt)
        }

        s_idx, e_idx = current_value
        s_dt = ts_list.iloc[s_idx]
        e_dt = ts_list.iloc[e_idx]

        def compact_span(a, b):
            if a.date() == b.date():
                # same day
                return f"{a.strftime('%d %b %H:%M')} – {b.strftime('%H:%M')}"
            if a.year == b.year and a.month == b.month:
                # same month
                return f"{a.strftime('%d')}–{b.strftime('%d %b')} {b.strftime('%H:%M')}"
            if a.year == b.year:
                return f"{a.strftime('%d %b')} – {b.strftime('%d %b')} {b.strftime('%H:%M')}"
            return f"{a.strftime('%Y-%m-%d')} → {b.strftime('%Y-%m-%d')}"
        disp = compact_span(s_dt, e_dt)
        return min_idx, max_idx, current_value, marks, disp

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
        # NEW: ensure multi_run_lock exists
        if "multi_run_lock" not in state or not isinstance(state["multi_run_lock"], list):
            state["multi_run_lock"] = []

        trig_id = (callback_context.triggered[0]["prop_id"].split(".")[0]
                   if callback_context.triggered else None)
        existing_active = state.get("active_runs", [])
        parse_new = trig_id == "selected-run-store"
        if parse_new:
            new_list = []
            if isinstance(selected_run_store, list):
                new_list = [str(r) for r in selected_run_store if r not in (None, "", [])]
            elif isinstance(selected_run_store, (str, int)) and selected_run_store not in (None, "", []):
                new_list = [str(selected_run_store)]

            def should_overwrite(old, new):
                if not new:
                    return False
                if len(new) > 1:
                    return True      # explicit multi-run
                if len(old) > 1 and len(new) == 1:
                    return False     # protect existing multi-run
                if not old:
                    return True
                if len(old) == 1 and len(new) == 1 and old[0] != new[0]:
                    return True      # switch single run
                return False

            if should_overwrite(existing_active, new_list):
                for rid in new_list:
                    if rid not in state["runs_cache"]:
                        try:
                            rd = repo.load_specific_run(rid)
                            state["runs_cache"][rid] = rd
                        except Exception:
                            pass
                state["active_runs"] = new_list
            else:
                state["active_runs"] = existing_active
        else:
            # Non-run trigger: keep existing_active
            state["active_runs"] = existing_active

        # NEW: restore multi-run if store collapsed but we have a lock
        if len(state.get("active_runs", [])) <= 1 and len(state.get("multi_run_lock", [])) > 1:
            # Only restore if current trigger is NOT an intentional run selection change
            if trig_id != "selected-run-store":
                state["active_runs"] = list(state["multi_run_lock"])

        # NEW: refresh lock when we truly have a multi-run active list
        if len(state.get("active_runs", [])) > 1:
            state["multi_run_lock"] = list(state["active_runs"])

        # Reload any missing run objects (menu might have been hidden after initial selection)
        for rid in state["active_runs"]:
            if rid not in state["runs_cache"]:
                try:
                    rd = repo.load_specific_run(rid)
                    state["runs_cache"][rid] = rd
                except Exception:
                    pass

        active_runs = state.get("active_runs") or []

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
        x_range = compute_x_range(relayoutData)
        if x_window:
            x_range = [x_window[0], x_window[1]]

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
        return price_fig, indicator_children, metrics_children, trade_details  # fixed (was 'trade')
