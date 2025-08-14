from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from core.visualizing.dashboard.colors import get_color_map
from core.visualizing.dashboard.components import get_default_trade_details  # hinzugefügt
from .chart.helpers import compute_x_range
from .chart.multi_run import build_multi_run_view
from .chart.single_run import build_single_run_view

def register_chart_callbacks(app, repo, state):

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
            Input("price-chart", "relayoutData"),
        ],
        State("price-chart-mode", "data"),
        prevent_initial_call=False
    )
    def unified(sel_values, _n, clickData, relayoutData, chart_mode):
        # Normalisieren
        if sel_values is None:
            sel_values = []
        elif isinstance(sel_values, str):
            sel_values = [sel_values]
        # Default auf ersten Collector falls leer
        if not sel_values and state.get("collectors"):
            first = next(iter(state["collectors"]), None)
            if first:
                sel_values = [first]

        if not sel_values:
            # Fallback leere Ausgabe
            from plotly.graph_objects import Figure
            return Figure().update_layout(title="No instrument"), [], [], get_default_trade_details()

        primary = sel_values[0]

        # Collector Wechsel
        if primary != state.get("selected_collector"):
            if primary in state.get("collectors", {}):
                state["selected_collector"] = primary
                state["selected_trade_index"] = None

        x_range = compute_x_range(relayoutData)
        active_runs = state.get("active_runs") or []
        multi_run_mode = len(active_runs) > 1
        color_map = get_color_map(sel_values)

        if multi_run_mode:
            return build_multi_run_view(
                state=state,
                repo=repo,
                instruments=sel_values,
                active_runs=active_runs,
                clickData=clickData,
                chart_mode=chart_mode,
                x_range=x_range,
                color_map=color_map
            )

        return build_single_run_view(
            state=state,
            repo=repo,
            instruments=sel_values,
            clickData=clickData,
            chart_mode=chart_mode,
            x_range=x_range,
            color_map=color_map
        )
