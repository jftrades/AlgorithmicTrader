from dash import Input, Output, dcc, State, callback_context, dash, ALL
from dash import html
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
import os
import traceback

from .components import (
    create_metrics_table
)

from .callbacks.charts import register_chart_callbacks  # NEU: orchestrierter Chart-Callback

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

    # KOMBINIERTER Callback für Menu Toggle UND Fullscreen - alle Styles zusammen
    @app.callback(
        [
            Output("slide-menu", "style"),
            Output("slide-menu", "children"),
            Output("menu-toggle-btn", "style"),
            Output("main-content", "style"),
            Output("menu-open-store", "data"),
            Output("menu-fullscreen-store", "data"),
            Output("fullscreen-close-btn", "style"),
            Output("selected-run-store", "data")  # NEU: selected runs aus Sidebar weiterreichen
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
            # suppressed debug output
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

        # --- NEU: aktualisiere shared state mit ausgewählten Runs und lade deren Daten in Cache ---
        selected_runs_data = selected_run_indices or []
        if selected_runs_data:
            # Lade ggf. run-data in state["runs_cache"]
            for rid in selected_runs_data:
                if rid not in state.get("runs_cache", {}):
                    try:
                        rd = repo.load_specific_run(rid)
                        state["runs_cache"][rid] = rd
                    except Exception as e:
                        # suppressed debug output
                        pass
        # set active runs (leer ok)
        state["active_runs"] = selected_runs_data

        return (
            menu_style, 
            new_slide_menu_content, 
            button_style, 
            main_style, 
            is_open, 
            is_fullscreen, 
            close_button_style,
            selected_runs_data
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

    @app.callback(
        Output("collector-dropdown", "options"),
        Output("collector-dropdown", "value"),
        Output("selected-run-store", "data"),
        Input("metrics-table", "derived_virtual_selected_rows"),
        State("metrics-table", "data"),
        prevent_initial_call=True
    )
    def select_run_from_table(selected_rows, table_data):
        if not selected_rows or not table_data:
            raise PreventUpdate
        selected_row = table_data[selected_rows[0]]
        run_id = selected_row.get('run_id')

        if not run_id:
            # missing run_id -> abort
            raise PreventUpdate

        try:
            run_data = repo.load_specific_run(run_id)
        except Exception as e:
            # suppressed debug output
            raise PreventUpdate

        state["collectors"] = run_data.collectors or {}
        state["selected_collector"] = run_data.selected or (next(iter(state["collectors"]), None))
        state["selected_trade_index"] = None

        state["runs_cache"][run_id] = run_data
        state["active_runs"] = [run_id]

        new_options = [{'label': k, 'value': k} for k in state["collectors"].keys()]
        new_value = state["selected_collector"]
        return new_options, new_value, run_id
