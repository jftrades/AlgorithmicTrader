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
            Output("metrics-panel", "children"),
            Output("trade-details-panel", "children")
        ],
        [
            Input("collector-dropdown", "value"),
            Input("refresh-btn", "n_clicks"),
            Input("price-chart", "clickData"),
            Input("price-chart", "relayoutData"),
        ],
        # NEU: selected-run-store als State lesen (wird vom Layout initial gesetzt)
        State("price-chart-mode", "data"),
        State("selected-run-store", "data"),
        prevent_initial_call=False
    )
    def unified(sel_values, _n, clickData, relayoutData, chart_mode, selected_run_store):
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
        # --- NEU: multiple Run-IDs aus selected-run-store benutzen (falls Liste) ---
        run_ids = []
        if isinstance(selected_run_store, list):
            run_ids = [str(r) for r in selected_run_store if r is not None and str(r) != ""]
        elif isinstance(selected_run_store, (str, int)) and selected_run_store:
            run_ids = [str(selected_run_store)]
        if run_ids:
            # Cache fehlende run-data und setze active_runs als Liste (erhält Multi-Run Auswahl)
            for rid in run_ids:
                if rid not in state.get("runs_cache", {}):
                    try:
                        rd = repo.load_specific_run(rid)
                        state["runs_cache"][rid] = rd
                    except Exception as e:
                        print(f"[METRICS] Failed to load run data for {rid}: {e}")
            state["active_runs"] = run_ids
        # --- Ende NEU ---

        if not sel_values:
            from plotly.graph_objects import Figure
            empty_fig = Figure().update_layout(title="No instrument")
            return empty_fig, [], html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'}), get_default_trade_details()

        primary = sel_values[0]

        # Collector Wechsel
        if primary != state.get("selected_collector"):
            if primary in state.get("collectors", {}):
                state["selected_collector"] = primary
                state["selected_trade_index"] = None

        x_range = compute_x_range(relayoutData)
        active_runs = state.get("active_runs") or []
        run_id = active_runs[0] if active_runs else None
        multi_run_mode = len(active_runs) > 1
        color_map = get_color_map(sel_values)

        def get_metrics_panel(run_id, collector):
            if not run_id or not collector:
                return html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'})
            from pathlib import Path
            import pandas as pd
            results_root = Path(__file__).resolve().parents[3] / "data" / "DATA_STORAGE" / "results"
            run_dir = results_root / str(run_id)
            metrics_path = run_dir / str(collector) / "trade_metrics.csv"
            if metrics_path.exists() and metrics_path.is_file():
                try:
                    df = pd.read_csv(metrics_path)
                    if not df.empty:
                        metrics = df.iloc[0].to_dict()
                        from core.visualizing.dashboard.components import create_metrics_table
                        return create_metrics_table(metrics, [])
                except Exception:
                    # suppressed debug output
                    pass
            return html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'})

        if multi_run_mode:
            result = build_multi_run_view(
                state=state,
                repo=repo,
                instruments=sel_values,
                active_runs=active_runs,
                clickData=clickData,
                chart_mode=chart_mode,
                x_range=x_range,
                color_map=color_map
            )
            price_fig, indicator_children, metrics_children, trade_details = result
            return price_fig, indicator_children, metrics_children, trade_details

        # single-run mode
        result = build_single_run_view(
            state=state,
            repo=repo,
            instruments=sel_values,
            clickData=clickData,
            chart_mode=chart_mode,
            x_range=x_range,
            color_map=color_map,
            run_id=run_id  # NEU: run_id weiterreichen, damit single-run Builder trade_metrics.csv laden kann
        )
        price_fig, indicator_children, metrics_children, trade_details = result
        return price_fig, indicator_children, metrics_children, trade_details
