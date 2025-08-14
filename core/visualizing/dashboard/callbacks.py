from dash import Input, Output, dcc, State, callback_context, dash, ALL
from dash import html  # <-- hinzugefügt (NameError fix)
from dash.exceptions import PreventUpdate  # re-added
import plotly.graph_objects as go
import pandas as pd

from .charts import build_price_chart, build_indicator_figure
from .components import (
    get_default_trade_details,
    get_default_trade_details_with_message,
    create_trade_details_content,
    create_metrics_table
)

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

    # KOMBINIERTER Callback für Menu Toggle UND Fullscreen - alle Styles zusammen
    @app.callback(
        [
            Output("slide-menu", "style"),
            Output("slide-menu", "children"),
            Output("menu-toggle-btn", "style"),
            Output("main-content", "style"),
            Output("menu-open-store", "data"),
            Output("menu-fullscreen-store", "data"),
            Output("fullscreen-close-btn", "style")
        ],
        [
            Input("menu-toggle-btn", "n_clicks"),
            Input("fullscreen-toggle-btn", "n_clicks"),  # FEHLTE: Fullscreen-Button Input
            Input("fullscreen-close-btn", "n_clicks"),
            Input({'type': 'run-checkbox', 'index': ALL}, 'value')  # Korrekte Syntax
        ],
        [
            State("menu-open-store", "data"),
            State("menu-fullscreen-store", "data"),
            State({'type': 'run-checkbox', 'index': ALL}, 'id')  # IDs der Checkboxen sammeln
        ],
        prevent_initial_call=True
    )
    def handle_menu_and_fullscreen(menu_clicks, fullscreen_toggle_clicks, fullscreen_close_clicks, checkbox_values, is_open, is_fullscreen, checkbox_ids):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
            
        # Bestimme welcher Button/Input gedrückt wurde
        trigger_id = ctx.triggered[0]['prop_id']
        button_id = trigger_id.split('.')[0]
        
        # Sammle aktuelle Checkbox-Zustände
        selected_run_indices = []
        current_checkbox_states = {}
        
        if checkbox_values and checkbox_ids:
            for checkbox_id, values in zip(checkbox_ids, checkbox_values):
                run_index = checkbox_id['index']
                is_checked = run_index in values if values else False
                current_checkbox_states[run_index] = is_checked
                if is_checked:
                    selected_run_indices.append(run_index)
        
        # Aktualisiere States basierend auf Button
        if button_id == "menu-toggle-btn":
            is_open = not (is_open or False)
        elif button_id in ["fullscreen-toggle-btn", "fullscreen-close-btn"]:
            is_fullscreen = not (is_fullscreen or False)
            if is_fullscreen:
                is_open = True
        # Bei Checkbox-Änderung: States beibehalten, nur Inhalt neu laden
        
        # Breiten definieren
        menu_width_normal = "380px"
        menu_width_fullscreen = "100vw"
        current_width = menu_width_fullscreen if is_fullscreen else menu_width_normal
        
        # Menu Style - mit Animation
        menu_style = {
            'position': 'fixed',
            'top': '0',
            'left': '0' if is_open else f'-{current_width}',
            'width': current_width,
            'height': '100vh',
            'background': 'linear-gradient(145deg, #ffffff 0%, #f8fafc 50%, #f1f5f9 100%)',
            'boxShadow': '4px 0 40px rgba(0,0,0,0.12), 0 0 0 1px rgba(255,255,255,0.05)' if is_open else 'none',
            'zIndex': '1001',
            'transition': 'all 0.4s cubic-bezier(0.4, 0.0, 0.2, 1)',
            'borderRight': '1px solid rgba(226, 232, 240, 0.8)' if not is_fullscreen else 'none'
        }
        
        # Menu-Inhalt neu erstellen mit aktuellem Fullscreen-Status und ausgewählten Runs
        from core.visualizing.dashboard.slide_menu import SlideMenuComponent
        from dash import html
        
        try:
            runs_df = repo.load_validated_runs()
            menu_component = SlideMenuComponent()
            
            # Übergebe sowohl ausgewählte Indizes als auch Checkbox-Zustände
            selected_indices = selected_run_indices if (is_fullscreen and selected_run_indices) else None
            
            # Erstelle neuen Sidebar-Inhalt mit aktuellen Checkbox-Zuständen
            new_sidebar = menu_component.create_sidebar(runs_df, is_open, is_fullscreen, selected_indices, current_checkbox_states)
            
            # Extrahiere nur die Sidebar-Inhalte
            if hasattr(new_sidebar, 'children') and len(new_sidebar.children) > 1:
                new_slide_menu_content = new_sidebar.children[1].children
            else:
                new_slide_menu_content = [html.Div("Error loading menu")]
                
        except Exception as e:
            print(f"[ERROR] Failed to recreate slide menu: {e}")
            new_slide_menu_content = [html.Div("Error loading menu")]
        
        # Toggle Button Style - IMMER LINKS (25px) - korrigiert
        button_style = {
            'position': 'fixed',
            'top': '25px',
            'left': '25px' if not is_open else f'calc({current_width} + 25px)',
            'zIndex': '1002',
            'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' if not is_open else 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
            'color': 'white',
            'border': 'none',
            'borderRadius': '12px',
            'width': '48px',
            'height': '48px',
            'cursor': 'pointer',
            'boxShadow': '0 8px 25px rgba(102, 126, 234, 0.4)' if not is_open else '0 8px 25px rgba(79, 70, 229, 0.5)',
            'transition': 'all 0.4s cubic-bezier(0.4, 0.0, 0.2, 1)',
            'backdropFilter': 'blur(10px)',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'transform': 'scale(1.05)' if is_open else 'scale(1)'
        }
        
        # Main Content Style
        main_style = {
            'minHeight':'100vh',
            'background':'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
            'fontFamily':'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
            'marginLeft': current_width if is_open and not is_fullscreen else '0px',
            'transition': 'margin-left 0.4s cubic-bezier(0.4, 0.0, 0.2, 1)',
            'position': 'relative',
            'zIndex': '1',
            'display': 'none' if is_fullscreen and is_open else 'block'
        }
        
        # Fullscreen-Close-Button Style - nur sichtbar wenn Fullscreen UND geöffnet
        close_button_style = {
            'position': 'fixed',
            'bottom': '25px',
            'right': '25px',
            'zIndex': '1003',
            'background': 'linear-gradient(135deg, #dc3545 0%, #fd7e14 100%)',
            'color': 'white',
            'border': 'none',
            'borderRadius': '50%',
            'width': '60px',
            'height': '60px',
            'cursor': 'pointer',
            'boxShadow': '0 8px 25px rgba(220, 53, 69, 0.4)',
            'transition': 'all 0.3s cubic-bezier(0.4, 0.0, 0.2, 1)',
            'display': 'flex' if (is_fullscreen and is_open) else 'none',  # Nur wenn Fullscreen UND offen
            'alignItems': 'center',
            'justifyContent': 'center',
            'fontFamily': 'monospace',
            'fontSize': '24px',
            'transform': 'scale(1)'
        }
        
        return (
            menu_style, 
            new_slide_menu_content, 
            button_style, 
            main_style, 
            is_open, 
            is_fullscreen, 
            close_button_style
        )

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

    # Callback für normale Run-Auswahl (nur wenn DataTable existiert)
    @app.callback(
        [
            Output("collector-dropdown", "options"),
            Output("collector-dropdown", "value"),
            Output("selected-run-store", "data")
        ],
        [Input("runs-table", "selected_rows")],
        [State("runs-table", "data")],
        prevent_initial_call=True
    )
    def select_run_from_table(selected_rows, table_data):
        if not selected_rows or not table_data:
            raise PreventUpdate
        selected_row = table_data[selected_rows[0]]
        run_id = selected_row.get('run_id')

        # Kein Fallback mehr: wenn run_id fehlt -> kein Update (sichtbarer Fehler im Log)
        if not run_id:
            print("[ERROR] run_id missing in selected row; aborting update.")
            raise PreventUpdate

        try:
            run_data = repo.load_specific_run(run_id)
        except Exception as e:
            print(f"[ERROR] Failed to load run_id {run_id}: {e}")
            raise PreventUpdate

        state["collectors"] = run_data.collectors or {}
        state["selected_collector"] = run_data.selected or (next(iter(state["collectors"]), None))
        state["selected_trade_index"] = None

        # --- NEU: Cache & active_runs pflegen ---
        state["runs_cache"][run_id] = run_data
        state["active_runs"] = [run_id]

        new_options = [{'label': k, 'value': k} for k in state["collectors"].keys()]
        new_value = state["selected_collector"]
        return new_options, new_value, run_id

    @app.callback(
        Output("price-chart-mode", "data"),
        Input("price-chart", "restyleData"),
        State("price-chart-mode", "data"),
        prevent_initial_call=True
    )
    def update_chart_mode(restyle_data, current_mode):
        """
        This callback ONLY updates the chart mode store when the OHLC/GRAPH buttons are clicked.
        It works by checking if the visibility of the first two traces (0=OHLC, 1=GRAPH) has changed.
        """
        if not restyle_data or 'visible' not in restyle_data[0]:
            raise PreventUpdate

        change = restyle_data[0]
        indices = restyle_data[1] if len(restyle_data) > 1 else []
        
        # Create a map of which trace index had its visibility changed
        vis_map = {idx: change['visible'][i] for i, idx in enumerate(indices)}

        # We only care about changes to trace 0 (OHLC) or trace 1 (GRAPH)
        if 0 not in vis_map and 1 not in vis_map:
            raise PreventUpdate

        # Determine the new state of both traces. If one wasn't in the restyle_data,
        # its visibility is the opposite of the one that was.
        ohlc_visible = vis_map.get(0, not vis_map.get(1, True))
        graph_visible = vis_map.get(1, not vis_map.get(0, True))

        if graph_visible and not ohlc_visible:
            new_mode = "GRAPH"
        else: # Default to OHLC if graph isn't exclusively visible
            new_mode = "OHLC"

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
            Input("price-chart", "clickData")
        ],
        State("price-chart-mode", "data"),
        prevent_initial_call=False,
    )
    def unified(sel_value, _n_clicks, clickData, chart_mode):
        # NEU: Falls Dropdown multi=True liefert Liste -> ersten Eintrag nehmen
        if isinstance(sel_value, list):
            sel_value = sel_value[0] if sel_value else None

        # Collector nur dann neu setzen (und Trade-Auswahl resetten), wenn er sich wirklich geändert hat
        if sel_value and sel_value in state["collectors"] and sel_value != state["selected_collector"]:
            state["selected_collector"] = sel_value
            state["selected_trade_index"] = None
        elif state["selected_collector"] is None and state["collectors"]:
            state["selected_collector"] = next(iter(state["collectors"]))

        c = state["collectors"].get(state["selected_collector"])
        bars = c.get("bars_df") if isinstance(c, dict) else None
        trades = c.get("trades_df") if isinstance(c, dict) else None
        indicators = c.get("indicators_df", {}) if isinstance(c, dict) else {}

        # Trade-Klick
        trade_details = get_default_trade_details()
        if clickData and isinstance(trades, pd.DataFrame) and not trades.empty:
            pt = next((p for p in clickData.get("points", []) if "customdata" in p), None)
            if pt is not None:
                idx = pt["customdata"]
                if idx in trades.index:
                    state["selected_trade_index"] = idx
                    trade_details = create_trade_details_content(trades.loc[idx])
            else:
                trade_details = get_default_trade_details_with_message()

        # Chart - persistenter Modus beibehalten
        try:
            price_fig = build_price_chart(
                bars, indicators, trades, state["selected_trade_index"], 
                display_mode=(chart_mode or "OHLC")
            )
            # Konsistente uirevision ohne Modus-Reset
            price_fig.update_layout(uirevision="persistent-chart")
        except Exception as e:
            price_fig = go.Figure().update_layout(title=f"Chart error: {e}")

        # Indicator-Subplots
        groups = {}
        for name, df in (indicators or {}).items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                pid = int(df["plot_id"].iloc[0]) if "plot_id" in df.columns else 0
                if pid > 0:
                    groups.setdefault(pid, []).append((name, df))
        ind_children = [
            dcc.Graph(
                id=f"indicators-plot-{pid}",
                figure=build_indicator_figure(lst),
                style={"height": "300px", "marginBottom": "10px"},
            )
            for pid, lst in sorted(groups.items())
        ]

        # Metrics (optional Repo-Hook)
        metrics, nautilus_result = {}, []
        if hasattr(repo, "load_metrics"):
            try:
                loaded = repo.load_metrics(state["selected_collector"])
                if loaded:
                    metrics, nautilus_result = loaded
            except Exception:
                pass
        metrics_div = create_metrics_table(metrics, nautilus_result)

        return price_fig, ind_children, metrics_div, trade_details
