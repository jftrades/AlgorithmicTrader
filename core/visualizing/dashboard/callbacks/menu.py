from dash import Input, Output, State, ALL, callback_context, html, no_update
from dash.exceptions import PreventUpdate
import json  # Import json for robust trigger parsing

from core.visualizing.dashboard.slide_menu import SlideMenuComponent

# NEU: importiere Regime-Analyzer Callback-Registrierer
from .regime_analyzer import register_regime_analyzer_callbacks

# Erzeuge die SlideMenuComponent-Instanz EINMAL global!
slide_menu_component = SlideMenuComponent()

def register_menu_callbacks(app, repo, state):
    # NEU: Registriere YAML + QuantStats Callbacks sofort
    slide_menu_component.viewer.register_callbacks(app)
    slide_menu_component.quantstats_viewer.register_callbacks(app)

    # NEU: Registriere Regime Analyzer Callbacks ebenfalls
    register_regime_analyzer_callbacks(app, repo)
    
    @app.callback(
        [
            Output("slide-menu", "style"),
            Output("slide-menu", "children"),
            Output("menu-toggle-btn", "style"),
            Output("main-content", "style"),
            Output("menu-open-store", "data"),
            Output("menu-fullscreen-store", "data"),
            Output("fullscreen-close-btn", "style"),
            Output("selected-run-store", "data", allow_duplicate=True),
            Output("collector-dropdown", "options", allow_duplicate=True),
            Output("collector-dropdown", "value", allow_duplicate=True),
        ],
        [
            Input("menu-toggle-btn", "n_clicks"),
            Input("fullscreen-toggle-btn", "n_clicks"),
            Input("fullscreen-close-btn", "n_clicks"),
            Input({'type': 'run-checkbox', 'index': ALL}, 'value'),
            # REMOVED runs-table.selected_rows (zirkuläre Abhängigkeit)
        ],
        [
            State("menu-open-store", "data"),
            State("menu-fullscreen-store", "data"),
            State({'type': 'run-checkbox', 'index': ALL}, 'id'),
            State("selected-run-store", "data"),
            # REMOVED runs-table.data
        ],
        prevent_initial_call=True,
    )
    def handle_menu_and_fullscreen(menu_clicks, fullscreen_toggle_clicks, fullscreen_close_clicks,
                                   checkbox_values,
                                   is_open, is_fullscreen, checkbox_ids,
                                   stored_selected_run_ids):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        trigger_id_str = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # Load runs (needed early for mapping)
        try:
            runs_df = repo.load_validated_runs()
        except Exception as e:
            print(f"[ERROR] load runs: {e}")
            runs_df = None

        index_to_run_id = {}
        if runs_df is not None and 'run_index' in runs_df.columns and 'run_id' in runs_df.columns:
            index_to_run_id = dict(zip(runs_df['run_index'], runs_df['run_id']))

        # --- UNIFIED SELECTION LOGIC ---
        updated_run_ids = stored_selected_run_ids or []
        
        try:
            trigger_dict = json.loads(trigger_id_str)
        except (json.JSONDecodeError, TypeError):
            trigger_dict = {}

        if isinstance(trigger_dict, dict) and trigger_dict.get("type") == "run-checkbox":
            # TRIGGER: Fullscreen checkbox click
            run_ids_accum = []
            for cid, values in zip(checkbox_ids, checkbox_values):
                run_index = cid['index']
                checked = bool(values and run_index in values)
                if checked:
                    rid = index_to_run_id.get(run_index)
                    if rid:
                        run_ids_accum.append(str(rid))
            updated_run_ids = run_ids_accum
        # For other triggers (menu toggle, etc.), updated_run_ids remains stored_selected_run_ids

        selected_run_indices = []
        current_checkbox_states = {}
        # ALWAYS reconstruct visual states from the authoritative run_ids list
        if updated_run_ids and index_to_run_id:
            run_id_set = set(str(r) for r in updated_run_ids)
            # Clear and rebuild selections to guarantee sync
            current_checkbox_states = {}
            selected_run_indices = []
            for idx, rid in index_to_run_id.items():
                if str(rid) in run_id_set:
                    current_checkbox_states[idx] = True
                    selected_run_indices.append(idx)
                else:
                    current_checkbox_states[idx] = False

        # --- when checkbox or menu state changes, update shared state/cache/collectors ---
        # This now runs on every trigger to ensure state is always correct.
        # Load each selected run into cache if missing
        for rid in updated_run_ids:
            if rid not in state.get("runs_cache", {}):
                try:
                    state["runs_cache"][rid] = repo.load_specific_run(rid)
                except Exception:
                    pass
        # Update active runs
        state["active_runs"] = updated_run_ids
        state["selected_trade_index"] = None
        # Refresh collectors from FIRST selected run
        if updated_run_ids:
            first_rid = updated_run_ids[0]
            first_run_obj = state["runs_cache"].get(first_rid)
            if first_run_obj:
                state["collectors"] = first_run_obj.collectors or {}
                state["selected_collector"] = (
                    first_run_obj.selected
                    or state.get("selected_collector") # try to preserve
                    or next(iter(state["collectors"]), None)
                )
            print(f"[MENU-main] trigger={trigger_id_str} active_runs={updated_run_ids}")
        else: # No runs selected
            state["collectors"] = {}
            state["selected_collector"] = None
        # -------------------------------------------------------------------------------

        # Build collector dropdown data (always reflect current state["collectors"])
        collector_options = [{'label': k, 'value': k} for k in (state.get("collectors") or {})]

        # Preserve current selected_collector if still valid, else first available
        current_selected = state.get("selected_collector")
        if current_selected not in [o['value'] for o in collector_options]:
            current_selected = collector_options[0]['value'] if collector_options else None
            state["selected_collector"] = current_selected
        collector_value = [current_selected] if current_selected else []

        # Determine new open/fullscreen states
        new_is_open = is_open or False
        new_is_fullscreen = is_fullscreen or False

        if trigger_id_str == "menu-toggle-btn":
            new_is_open = not new_is_open
        elif trigger_id_str in ("fullscreen-toggle-btn", "fullscreen-close-btn"):
            new_is_fullscreen = not new_is_fullscreen
            if new_is_fullscreen:
                new_is_open = True  # ensure visible in fullscreen
        
        fullscreen_state_has_changed = new_is_fullscreen != (is_fullscreen or False)

        # --- Rebuild sidebar children ONLY when necessary ---
        if not fullscreen_state_has_changed and not isinstance(trigger_dict, dict):
            slide_children = no_update
        else:
            try:
                sidebar = slide_menu_component.create_sidebar(
                    runs_df=runs_df,
                    is_open=new_is_open,
                    is_fullscreen=new_is_fullscreen,
                    selected_run_indices=selected_run_indices,
                    checkbox_states=current_checkbox_states,
                    app=app
                )
                if hasattr(sidebar, 'children') and len(sidebar.children) > 1:
                    slide_children = sidebar.children[1].children
                else:
                    slide_children = [html.Div("Error loading menu")]
            except Exception as e:
                print(f"[ERROR] menu recreate: {e}")
                slide_children = [html.Div("Error loading menu")]

        menu_width = "100vw" if new_is_fullscreen else "380px"
        menu_style = {
            'position': 'fixed',
            'top': '0',
            'left': '0' if new_is_open else f'-{menu_width}',
            'width': menu_width,
            'height': '100vh',
            'background': 'linear-gradient(145deg, #ffffff 0%, #f8fafc 50%, #f1f5f9 100%)',
            'boxShadow': '4px 0 40px rgba(0,0,0,0.12)' if new_is_open else 'none',
            'zIndex': '1001',
            'transition': 'all 0.4s cubic-bezier(0.4,0,0.2,1)',
            'borderRight': '1px solid rgba(226,232,240,0.8)' if not new_is_fullscreen else 'none'
        }

        # This block is now only for calculating styles, not rebuilding children
        button_style = {
            'position': 'fixed',
            'top': '25px',
            'left': '25px' if not new_is_open else f'calc({menu_width} + 25px)',
            'zIndex': '1002',
            'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' if not new_is_open else 'linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%)',
            'color': 'white',
            'border': 'none',
            'borderRadius': '12px',
            'width': '48px',
            'height': '48px',
            'cursor': 'pointer',
            'boxShadow': '0 8px 25px rgba(102,126,234,0.4)' if not new_is_open else '0 8px 25px rgba(79,70,229,0.5)',
            'transition': 'all 0.4s cubic-bezier(0.4,0,0.2,1)',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'transform': 'scale(1.05)' if new_is_open else 'scale(1)'
        }

        main_style = {
            'minHeight': '100vh',
            'background': 'linear-gradient(135deg,#f5f7fa 0%,#c3cfe2 100%)',
            'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
            'marginLeft': menu_width if new_is_open and not new_is_fullscreen else '0px',
            'transition': 'margin-left 0.4s cubic-bezier(0.4,0,0.2,1)',
            'position': 'relative',
            'zIndex': '1',
            'display': 'none' if new_is_fullscreen and new_is_open else 'block'
        }

        close_button_style = {
            'position': 'fixed',
            'bottom': '55px',
            'right': '25px',
            'zIndex': '1003',
            'background': 'linear-gradient(135deg,#dc3545 0%,#fd7e14 100%)',
            'color': 'white',
            'border': 'none',
            'borderRadius': '50%',
            'width': '60px',
            'height': '60px',
            'cursor': 'pointer',
            'boxShadow': '0 8px 25px rgba(220,53,69,0.4)',
            'transition': 'all 0.3s cubic-bezier(0.4,0,0.2,1)',
            'display': 'flex' if (new_is_fullscreen and new_is_open) else 'none',
            'alignItems': 'center',
            'justifyContent': 'center',
            'fontFamily': 'monospace',
            'fontSize': '24px'
        }

        return (menu_style, slide_children, button_style, main_style,
                new_is_open, new_is_fullscreen, close_button_style, updated_run_ids,
                collector_options, collector_value)

    # NEU: Separater Callback für normale Tabellen-Selektion
    @app.callback(
        [
            Output("selected-run-store", "data", allow_duplicate=True),
            Output("collector-dropdown", "options", allow_duplicate=True),
            Output("collector-dropdown", "value", allow_duplicate=True),
        ],
        Input("runs-table", "selected_rows"),
        State("runs-table", "data"),
        State("selected-run-store", "data"),
        prevent_initial_call=True
    )
    def handle_runs_table_selection(selected_rows, table_data, stored_run_ids):
        if not selected_rows or not table_data:
            raise PreventUpdate
        # Map selected row indices -> run_ids
        run_ids = []
        for idx in selected_rows:
            if isinstance(idx, int) and 0 <= idx < len(table_data):
                rid = table_data[idx].get("run_id")
                if rid:
                    run_ids.append(str(rid))
        if not run_ids:
            raise PreventUpdate
        # Cache + collectors (erste Selektion maßgeblich)
        for rid in run_ids:
            if rid not in state["runs_cache"]:
                try:
                    state["runs_cache"][rid] = repo.load_specific_run(rid)
                except Exception as e:
                    print(f"[RUN-TABLE] load failed {rid}: {e}")
        state["active_runs"] = run_ids
        state["selected_trade_index"] = None
        if run_ids:
            first = run_ids[0]
            obj = state["runs_cache"].get(first)
            if obj:
                state["collectors"] = obj.collectors or {}
                state["selected_collector"] = (
                    obj.selected
                    or state.get("selected_collector")
                    or next(iter(state["collectors"]), None)
                )
        else:
            state["collectors"] = {}
            state["selected_collector"] = None
        options = [{'label': k, 'value': k} for k in (state.get("collectors") or {})]
        cur = state.get("selected_collector")
        if cur not in [o['value'] for o in options]:
            cur = options[0]['value'] if options else None
            state["selected_collector"] = cur
        value = [cur] if cur else []
        print(f"[RUN-TABLE] selected_rows={selected_rows} -> run_ids={run_ids}")
        return run_ids, options, value
