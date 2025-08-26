from dash import Input, Output, State, html
from dash.exceptions import PreventUpdate

from core.visualizing.dashboard.colors import get_color_map
from core.visualizing.dashboard.components import get_default_trade_details  # hinzugefügt
from core.visualizing.dashboard.components import create_metrics_table
from pathlib import Path
import os
import traceback
from .chart.helpers import compute_x_range
from .chart.multi_run import build_multi_run_view
from .chart.single_run import build_single_run_view

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
            # invert on each click
            show = (n % 2 == 1) == False if current is True else (n % 2 == 0)
            # Simpler: compute by parity of clicks vs default True
            show = not (n % 2)  # even clicks => True, odd => False
        label = "Hide Trades" if show else "Show Trades"
        base_style = {
            'height':'42px','alignSelf':'flex-end','marginLeft':'14px',
            'background':'linear-gradient(135deg,#4ade80 0%,#16a34a 100%)' if show else 'linear-gradient(135deg,#64748b 0%,#334155 100%)',
            'color':'#fff','border':'none','borderRadius':'10px',
            'padding':'8px 16px','cursor':'pointer','fontSize':'13px',
            'fontFamily':'Inter, system-ui, sans-serif','fontWeight':'600',
            'boxShadow':'0 2px 6px rgba(16,185,129,0.35)' if show else '0 2px 6px rgba(51,65,85,0.35)'
        }
        return show, label, base_style

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
        ],
        State("price-chart-mode", "data"),
        State("selected-run-store", "data"),
        prevent_initial_call=False
    )
    def unified(sel_values, timeframe_value, _n, clickData, relayoutData, show_trades, chart_mode, selected_run_store):
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

        # Active runs management
        run_ids = []
        if isinstance(selected_run_store, list):
            run_ids = [str(r) for r in selected_run_store if r not in (None, "", [])]
        elif isinstance(selected_run_store, (str, int)) and selected_run_store:
            run_ids = [str(selected_run_store)]
        if run_ids:
            for rid in run_ids:
                if rid not in state.get("runs_cache", {}):
                    try:
                        rd = repo.load_specific_run(rid)
                        state["runs_cache"][rid] = rd
                    except Exception:
                        pass
            state["active_runs"] = run_ids

        if not sel_values:
            from plotly.graph_objects import Figure
            empty_fig = Figure().update_layout(title="No instrument")
            return empty_fig, [], html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'}), get_default_trade_details()

        primary = sel_values[0]
        if primary != state.get("selected_collector") and primary in state.get("collectors", {}):
            state["selected_collector"] = primary
            state["selected_trade_index"] = None

        x_range = compute_x_range(relayoutData)
        active_runs = state.get("active_runs") or []
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
                show_trades=bool(show_trades)
            )
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
            show_trades=bool(show_trades)
        )
        return price_fig, indicator_children, metrics_children, trade_details
