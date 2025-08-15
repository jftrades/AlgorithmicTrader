from pathlib import Path
from dash import html, dcc

class YamlViewer:
    """
    Kapselt Anzeige + Laden der run_config.yaml Dateien.
    Verwendung:
        viewer = YamlViewer()
        viewer.register_callbacks(app)
        # In layout:
        # app.layout.children.append(viewer.get_modal())
        # sidebar.children.extend(viewer.build_components(...)["controls"], ...)
    """

    def __init__(self):
        self._callbacks_registered = False
        self._cached_modal = None
        self._instance_id = id(self)  # NEU: Eindeutige Instanz-ID

    def get_modal(self):
        """Return (and lazily create) the single global modal component."""
        if self._cached_modal is None:
            self._cached_modal = self._build_modal()
        return self._cached_modal

    def build_components(self, runs_df, selected_run_indices, app=None):
        """Return sidebar pieces (controls + store). Modal is global (see get_modal)."""
        preload = self._preload_selected(runs_df, selected_run_indices)
        controls = self._build_controls(runs_df, selected_run_indices)
        
        # Store-Daten über separaten Callback aktualisieren
        if app is not None:
            self.register_callbacks(app)
        
        return {"controls": controls, "store": None}

    def _build_controls(self, runs_df, selected_indices):
        # Dropdown-Optionen vorbereiten
        opts = []
        if selected_indices:
            for idx in selected_indices:
                if 0 <= idx < len(runs_df):
                    row = runs_df.iloc[idx]
                    rid = self._resolve_run_id(row)
                    short = rid[:20] + ("…" if len(rid) > 20 else "")
                    opts.append({"label": short, "value": rid})
        
        # NEU: Wenn keine Runs ausgewählt sind, zeige GAR NICHTS an
        if not opts:
            return html.Div(style={'height': '0px', 'overflow': 'hidden'})
        
        # Dropdown und Button nur wenn Runs vorhanden
        dropdown = dcc.Dropdown(
            id="run-yaml-run-select",
            options=opts,
            value=opts[0]["value"],
            clearable=False,
            searchable=False,
            style={
                'minWidth': '140px',
                'fontSize': '10.5px',
                'height': '30px',
                'padding': '0 4px'
            }
        )
        
        button = html.Button(
            "Show YAML",
            id="show-run-yaml-btn", 
            n_clicks=0,
            style={
                'background': 'linear-gradient(90deg,#6366f1 0%,#8b5cf6 100%)',
                'color': '#fff',
                'border': 'none',
                'borderRadius': '8px',
                'padding': '0 14px',
                'cursor': 'pointer',
                'fontWeight': '600',
                'fontSize': '11px',
                'boxShadow': '0 2px 5px -1px rgba(99,102,241,0.35)',
                'transition': 'background .25s',
                'whiteSpace': 'nowrap',
                'height': '34px',          # was 30px
                'display': 'flex',
                'alignItems': 'center'
            }
        )
        
        return html.Div([dropdown, button], style={
            'display': 'flex',
            'alignItems': 'center',
            'gap': '6px'
        })

    def _build_modal(self):
        return html.Div(id="run-yaml-modal", style={
            'display': 'none',
            'position': 'fixed',
            'top': '0',
            'right': '0',
            'width': '480px',
            'maxWidth': '90vw',
            'height': '100vh',
            'background': 'linear-gradient(145deg,#ffffff 0%,#f1f5f9 100%)',
            'boxShadow': '-4px 0 18px -2px rgba(0,0,0,0.18)',
            'borderLeft': '3px solid #6366f1',
            'zIndex': '30000',  # war 5000, jetzt ganz oben!
            'padding': '18px 22px 28px 22px',
            'boxSizing': 'border-box',
            'overflowY': 'auto',
            'fontFamily': 'Inter,system-ui,sans-serif'
        }, children=[
            html.Div([
                html.H3("Run Configuration", style={
                    'margin': '0',
                    'fontSize': '20px',
                    'fontWeight': '600',
                    'color': '#1f2937',
                    'letterSpacing': '-0.5px'
                }),
                html.Button("✕", id="close-run-yaml-btn", style={
                    'background': '#475569',
                    'color': '#f1f5f9',
                    'border': 'none',
                    'borderRadius': '8px',
                    'cursor': 'pointer',
                    'fontWeight': '600',
                    'padding': '6px 12px',
                    'fontSize': '13px'
                })
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'space-between',
                'marginBottom': '12px'
            }),
            html.Div(id="run-yaml-title", style={
                'fontSize': '12px',
                'fontWeight': '600',
                'textTransform': 'uppercase',
                'letterSpacing': '.5px',
                'color': '#6366f1',
                'marginBottom': '6px'
            }),
            html.Pre(id="run-yaml-content", style={
                'whiteSpace': 'pre-wrap',
                'wordBreak': 'break-word',
                'background': '#0f172a',
                'color': '#e2e8f0',
                'padding': '14px 16px',
                'borderRadius': '10px',
                'fontSize': '12px',
                'lineHeight': '1.4',
                'border': '1px solid #1e293b',
                'boxShadow': 'inset 0 0 0 1px rgba(255,255,255,0.03)',
                'maxHeight': '70vh',
                'overflowY': 'auto'
            }),
            html.Pre(id="run-yaml-debug", style={
                'marginTop': '12px',
                'background': '#1e293b',
                'color': '#94a3b8',
                'padding': '8px 10px',
                'fontSize': '11px',
                'borderRadius': '8px',
                'whiteSpace': 'pre-wrap',
                'display': 'none'
            })
        ])

    # ---------- DATA LOADING ----------
    def _resolve_run_id(self, row):
        rid = str(row.get('run_id') or "").strip()
        if rid:
            return rid
        idx = row.get('run_index')
        return f"run{idx}" if idx is not None else "run_unknown"

    def _results_dir(self):
        current = Path(__file__).resolve()
        return current.parents[4] / "data" / "DATA_STORAGE" / "results"

    def _preload_selected(self, runs_df, indices):
        if not indices:
            return {}
        out = {}
        for i in indices:
            if 0 <= i < len(runs_df):
                rid = self._resolve_run_id(runs_df.iloc[i])
                text = self._load_yaml_file(rid)
                if text is not None:
                    out[rid] = text
        return out

    def _load_yaml_file(self, run_id):
        try:
            p = self._results_dir() / run_id / "run_config.yaml"
            if p.exists():
                return p.read_text(encoding='utf-8', errors='replace')
        except Exception:
            pass
        return None

    # ---------- CALLBACKS ----------
    def register_callbacks(self, app):
        if self._callbacks_registered:
            return
            
        self._callbacks_registered = True
        
        from dash import Input, Output, State
        try:
            from dash import ctx
        except ImportError:
            import dash
            ctx = dash.callback_context

        @app.callback(
            Output("run-yaml-modal", "style"),
            Output("run-yaml-content", "children"),
            Output("run-yaml-title", "children"),
            Input("show-run-yaml-btn", "n_clicks"),
            Input("close-run-yaml-btn", "n_clicks"),
            State("run-yaml-modal", "style"),
            State("run-yaml-store", "data"),
            State("run-yaml-run-select", "value"),
            State("run-yaml-run-select", "options"),
            prevent_initial_call=True
        )
        def _toggle_modal(show_clicks, close_clicks, modal_style, yaml_data, selected_run_id, run_options):
            modal_style = (modal_style or {}).copy()
            yaml_data = yaml_data or {}
            trig = getattr(ctx, "triggered_id", None)
            
            if trig == "close-run-yaml-btn":
                modal_style["display"] = "none"
                return modal_style, "", ""

            if trig == "show-run-yaml-btn":
                run_id = None
                if selected_run_id:
                    run_id = selected_run_id
                elif run_options and isinstance(run_options, list) and len(run_options) > 0:
                    run_id = run_options[0]["value"]
                
                if run_id:
                    if run_id not in yaml_data:
                        txt = self._load_yaml_file(run_id)
                        if txt is not None:
                            yaml_data[run_id] = txt
                    content = yaml_data.get(run_id, "No YAML found for selected run.")
                    title = f"{run_id} / run_config.yaml"
                else:
                    content = "No run selected."
                    title = "run_config.yaml"
                
                modal_style["display"] = "block"
                modal_style["boxShadow"] = "0 0 0 3px #6366f1, -4px 0 18px -2px rgba(0,0,0,0.18)"
                return modal_style, content, title

            return modal_style, "", ""
