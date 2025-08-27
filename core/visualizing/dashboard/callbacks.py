from dash import Input, Output, dcc, State, callback_context, dash, ALL
from dash import html
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
import os
import traceback

from .callbacks.charts import register_chart_callbacks
from .callbacks.menu import register_menu_callbacks  # NEU: import menu callbacks

def register_callbacks(app, repo, dash_data=None):
    # State vorbereiten – KEIN zweites repo.load_dashboard() hier!
    state = {
        "selected_collector": None,
        "selected_trade_index": None,
        "collectors": {},
        "runs_cache": {},          # NEU
        "active_runs": []          # NEU
    }

    if dash_data is not None:
        state["collectors"] = dash_data.collectors or {}
        state["selected_collector"] = dash_data.selected or (next(iter(state["collectors"]), None))
        all_results_cache = getattr(dash_data, "all_results_df", None)
        if getattr(dash_data, "run_id", None):
            rid = str(dash_data.run_id)
            state["runs_cache"][rid] = dash_data
            state["active_runs"] = [rid]
    else:
        # Fallback (sollte eig. nicht passieren)
        state["collectors"] = {}
        state["selected_collector"] = None
        all_results_cache = None

    # NEU: Registrierung der ausgelagerten Chart-Callbacks (Multi-Run + Multi-Instrument)
    register_chart_callbacks(app, repo, state)
    
    # NEU: Registrierung der ausgelagerten und vereinheitlichten Menu-Callbacks
    register_menu_callbacks(app, repo, state)

    # --- Parameter Analyzer: open/close + render ---
    from core.visualizing.dashboard.param_analysis.ui import build_analyzer_layout
    from core.visualizing.dashboard.param_analysis.service import ParameterAnalysisService
    analysis_service = ParameterAnalysisService()  # nutzt jetzt run_param_columns für X/Y Parameter

    @app.callback(
        Output("param-analyzer-panel", "style"),
        Output("param-analyzer-content", "children"),
        Input("param-analyzer-open-btn", "n_clicks"),
        Input("param-analyzer-close-btn", "n_clicks"),
        State("param-analyzer-panel", "style"),
        prevent_initial_call=True
    )
    def toggle_param_analyzer(open_clicks, close_clicks, current_style):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        style = dict(current_style or {})
        if trigger == "param-analyzer-open-btn":
            try:
                runs_df = repo.load_validated_runs()
            except Exception:
                return {**style, 'display': 'none'}, html.Div("Failed to load runs", style={'color': '#f87171'})
            layout = build_analyzer_layout(runs_df, analysis_service)
            return {**style, 'display': 'block'}, layout
        else:
            return {**style, 'display': 'none'}, None

    @app.callback(
        Output("param-analyzer-results-container", "children"),
        Input("param-analyzer-run-metric", "value"),
        Input("param-analyzer-xparam", "value"),
        Input("param-analyzer-yparam", "value"),
        Input("param-analyzer-zparam", "value"),
        Input("param-analyzer-aggfunc", "value"),
        Input("param-analyzer-refresh-btn", "n_clicks"),
        Input("param-analyzer-3d-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def refresh_param_analysis(metric, xparam, yparam, zparam, aggfunc, _2d_clicks, _3d_clicks):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        # Bestimme welcher Button gedrückt wurde
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        
        if trigger == "param-analyzer-3d-btn":
            # 3D-Analyse
            if not all([metric, xparam, yparam, zparam]):
                return [html.Div("Please select metric and all three parameters (X, Y, Z) for 3D analysis", 
                                style={'color': '#f87171'})]
            try:
                runs_df = repo.load_validated_runs()
                return analysis_service.generate_3d_analysis(runs_df, metric, xparam, yparam, zparam, aggfunc)
            except Exception as e:
                return [html.Div(f"3D Analysis error: {e}", style={'color': '#f87171'})]
        else:
            # 2D-Analyse (bestehend)
            if not all([metric, xparam, yparam]):
                raise PreventUpdate
            try:
                runs_df = repo.load_validated_runs()
                figs = analysis_service.generate_metric_views(runs_df, metric, xparam, yparam, aggfunc)
                return figs
            except Exception as e:
                return [html.Div(f"Analysis error: {e}", style={'color': '#f87171'})]

    # --- Auto-matrix (all parameter pairs) ---
    @app.callback(
        Output("param-analyzer-matrix-container", "children"),
        Input("param-analyzer-build-matrix-btn", "n_clicks"),
        State("param-analyzer-run-metric", "value"),
        prevent_initial_call=True
    )
    def build_full_matrix(n, metric):
        if not n or not metric:
            raise PreventUpdate
        try:
            runs_df = repo.load_validated_runs()
            return analysis_service.generate_full_pair_matrix(runs_df, metric)
        except Exception as e:
            try:
                return [html.Div(f"Matrix error: {e}", style={'color': '#f87171'})]
            except NameError:
                # ultra fallback
                return []
