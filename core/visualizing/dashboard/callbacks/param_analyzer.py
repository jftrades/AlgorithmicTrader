from dash import Input, Output, State, callback_context, html
from dash.exceptions import PreventUpdate

from core.visualizing.dashboard.param_analysis.ui import build_analyzer_layout

def register_param_analyzer_callbacks(app, repo, analysis_service):
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
                layout = build_analyzer_layout(runs_df, analysis_service)
                return {**style, 'display': 'block'}, layout
            except Exception:
                return {**style, 'display': 'none'}, html.Div("Failed to load runs", style={'color': '#f87171'})
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
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        try:
            runs_df = repo.load_validated_runs()
        except Exception as e:
            return [html.Div(f"Load error: {e}", style={'color': '#f87171'})]

        if trigger == "param-analyzer-3d-btn":
            if not all([metric, xparam, yparam, zparam]):
                return [html.Div("Select metric + X,Y,Z", style={'color': '#f87171'})]
            try:
                return analysis_service.generate_3d_analysis(runs_df, metric, xparam, yparam, zparam, aggfunc)
            except Exception as e:
                return [html.Div(f"3D Analysis error: {e}", style={'color': '#f87171'})]

        if not all([metric, xparam, yparam]):
            raise PreventUpdate
        try:
            return analysis_service.generate_metric_views(runs_df, metric, xparam, yparam, aggfunc)
        except Exception as e:
            return [html.Div(f"Analysis error: {e}", style={'color': '#f87171'})]

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
            return [html.Div(f"Matrix error: {e}", style={'color': '#f87171'})]
