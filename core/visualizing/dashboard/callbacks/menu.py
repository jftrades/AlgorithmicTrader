from dash import Input, Output, State, ALL, callback_context, html
from dash.exceptions import PreventUpdate

def register_menu_callbacks(app, repo, state):
    @app.callback(
        [
            Output("slide-menu", "style"),
            Output("slide-menu", "children"),
            Output("menu-toggle-btn", "style"),
            Output("main-content", "style"),
            Output("menu-open-store", "data"),
            Output("menu-fullscreen-store", "data"),
            Output("fullscreen-close-btn", "style"),
        ],
        [
            Input("menu-toggle-btn", "n_clicks"),
            Input("fullscreen-toggle-btn", "n_clicks"),
            Input("fullscreen-close-btn", "n_clicks"),
            Input({'type': 'run-checkbox', 'index': ALL}, 'value'),
        ],
        [
            State("menu-open-store", "data"),
            State("menu-fullscreen-store", "data"),
            State({'type': 'run-checkbox', 'index': ALL}, 'id'),
        ],
        prevent_initial_call=True,
    )
    def handle_menu_and_fullscreen(menu_clicks, fullscreen_toggle_clicks, fullscreen_close_clicks,
                                   checkbox_values, is_open, is_fullscreen, checkbox_ids):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        selected_run_indices = []
        current_checkbox_states = {}
        if checkbox_values and checkbox_ids:
            for cid, values in zip(checkbox_ids, checkbox_values):
                run_index = cid['index']
                checked = run_index in values if values else False
                current_checkbox_states[run_index] = checked
                if checked:
                    selected_run_indices.append(run_index)

        if trigger_id == "menu-toggle-btn":
            is_open = not (is_open or False)
        elif trigger_id in ("fullscreen-toggle-btn", "fullscreen-close-btn"):
            is_fullscreen = not (is_fullscreen or False)
            if is_fullscreen:
                is_open = True

        menu_width = "100vw" if is_fullscreen else "380px"
        menu_style = {
            'position': 'fixed',
            'top': '0',
            'left': '0' if is_open else f'-{menu_width}',
            'width': menu_width,
            'height': '100vh',
            'background': 'linear-gradient(145deg, #ffffff 0%, #f8fafc 50%, #f1f5f9 100%)',
            'boxShadow': '4px 0 40px rgba(0,0,0,0.12)' if is_open else 'none',
            'zIndex': '1001',
            'transition': 'all 0.4s cubic-bezier(0.4,0,0.2,1)',
            'borderRight': '1px solid rgba(226,232,240,0.8)' if not is_fullscreen else 'none'
        }

        from core.visualizing.dashboard.slide_menu import SlideMenuComponent
        try:
            runs_df = repo.load_validated_runs()
            component = SlideMenuComponent()
            selected_indices = selected_run_indices if (is_fullscreen and selected_run_indices) else None
            sidebar = component.create_sidebar(runs_df, is_open, is_fullscreen, selected_indices, current_checkbox_states)
            if hasattr(sidebar, 'children') and len(sidebar.children) > 1:
                slide_children = sidebar.children[1].children
            else:
                slide_children = [html.Div("Error loading menu")]
        except Exception as e:
            print(f"[ERROR] menu recreate: {e}")
            slide_children = [html.Div("Error loading menu")]

        button_style = {
            'position': 'fixed',
            'top': '25px',
            'left': '25px' if not is_open else f'calc({menu_width} + 25px)',
            'zIndex': '1002',
            'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' if not is_open else 'linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%)',
            'color': 'white',
            'border': 'none',
            'borderRadius': '12px',
            'width': '48px',
            'height': '48px',
            'cursor': 'pointer',
            'boxShadow': '0 8px 25px rgba(102,126,234,0.4)' if not is_open else '0 8px 25px rgba(79,70,229,0.5)',
            'transition': 'all 0.4s cubic-bezier(0.4,0,0.2,1)',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'transform': 'scale(1.05)' if is_open else 'scale(1)'
        }

        main_style = {
            'minHeight': '100vh',
            'background': 'linear-gradient(135deg,#f5f7fa 0%,#c3cfe2 100%)',
            'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
            'marginLeft': menu_width if is_open and not is_fullscreen else '0px',
            'transition': 'margin-left 0.4s cubic-bezier(0.4,0,0.2,1)',
            'position': 'relative',
            'zIndex': '1',
            'display': 'none' if is_fullscreen and is_open else 'block'
        }

        close_button_style = {
            'position': 'fixed',
            'bottom': '25px',
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
            'display': 'flex' if (is_fullscreen and is_open) else 'none',
            'alignItems': 'center',
            'justifyContent': 'center',
            'fontFamily': 'monospace',
            'fontSize': '24px'
        }

        return (menu_style, slide_children, button_style, main_style,
                is_open, is_fullscreen, close_button_style)
