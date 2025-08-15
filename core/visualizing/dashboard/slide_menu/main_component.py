"""
Hauptkomponente für das Slide-Menu
Orchestriert die verschiedenen Subkomponenten
"""
import pandas as pd
from dash import html, dcc  # NEU: dcc Import hinzugefügt
from .table_components import RunTableBuilder
from .chart_components import EquityChartsBuilder
from .yaml_viewer import YamlViewer  # NEU
from .quantstats_viewer import QuantStatsViewer  # NEU

class SlideMenuComponent:
    """UI-Komponente für das ausklappbare Slide-Menu"""
    
    def __init__(self):
        self.menu_width_open = "380px"
        self.menu_width_fullscreen = "100vw"
        self.menu_width_closed = "0px"
        
        # Subkomponenten
        self.table_builder = RunTableBuilder()
        self.charts_builder = EquityChartsBuilder()
        self.viewer = YamlViewer()  # NEU
        self.quantstats_viewer = QuantStatsViewer()  # NEU
    
    def create_sidebar(self, runs_df: pd.DataFrame, is_open: bool = False, is_fullscreen: bool = False, 
                      selected_run_indices: list = None, checkbox_states: dict = None, app=None) -> html.Div:
        """Erstellt NUR die Sidebar-Inhalte (ohne Toggle-Button)"""
        
        # YAML-Viewer-Callbacks automatisch registrieren wie beim Param Analyzer
        if app is not None:
            self.viewer.register_callbacks(app)
            self.quantstats_viewer.register_callbacks(app)  # NEU
        
        sidebar_content = []

        # YAML + QuantStats Controls (nur im Fullscreen-Modus)
        yaml_controls = html.Div()
        quantstats_controls = html.Div()  # NEU
        if is_fullscreen:
            # YAML Controls
            viewer_components = self.viewer.build_components(runs_df, selected_run_indices or [], app=app)
            yaml_controls = viewer_components["controls"]
            
            # QuantStats Controls
            quantstats_components = self.quantstats_viewer.build_components(runs_df, selected_run_indices or [], app=app)
            quantstats_controls = quantstats_components["controls"]

        # Header Layout (jetzt mit YAML + QuantStats)
        header = self._create_header(runs_df, is_fullscreen, yaml_controls, quantstats_controls)
        sidebar_content.append(header)

        # Run-Tabelle erstellen
        run_table = self.table_builder.create_table(runs_df, is_fullscreen, checkbox_states)

        # Equity Curves für Fullscreen-Modus
        equity_charts = html.Div()
        if is_fullscreen:
            equity_charts = self.charts_builder.create_equity_charts(runs_df, selected_run_indices)
        
        # Fullscreen Toggle Button
        fullscreen_button = self._create_fullscreen_button(is_fullscreen)
        
        # Hauptinhalt Container
        main_content = self._create_main_content(run_table, equity_charts, fullscreen_button, is_fullscreen)

        sidebar_content.append(main_content)
        # Store NICHT mehr hinzufügen - kommt aus Haupt-Layout
        # if yaml_store:
        #     sidebar_content.append(yaml_store)
        if is_fullscreen:
            sidebar_content.append(self.viewer.get_modal())

        return html.Div([html.Div(), html.Div(sidebar_content)])
    
    def _fmt_ns_timestamp(self, val):
        import pandas as pd
        try:
            if pd.isna(val):
                return "N/A"
            # Nanosekunden -> Datum
            if isinstance(val, (int, float)) and val > 1e15:
                return pd.to_datetime(int(val), unit='ns').strftime('%Y-%m-%d %H:%M:%S')
            # Fallback normale Konvertierung
            return pd.to_datetime(val).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(val)

    def _fmt_elapsed(self, val):
        try:
            v = float(val)
            # Wenn sehr groß -> vermutlich ns
            if v > 1e9:
                seconds = v / 1e9
            else:
                seconds = v
            if seconds < 60:
                return f"{seconds:.2f}s"
            if seconds < 3600:
                return f"{seconds/60:.2f}m"
            if seconds < 86400:
                return f"{seconds/3600:.2f}h"
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}d {hours}h" if hours else f"{days}d"
        except Exception:
            return str(val)

    def _create_fullscreen_button(self, is_fullscreen: bool) -> html.Button:
        """Erstellt Fullscreen Toggle Button"""
        return html.Button([
            html.Div("⛶", style={'fontSize': '17px', 'lineHeight': '1', 'fontWeight': '600'})
        ],
            id="fullscreen-toggle-btn",
            style={
                'background': 'linear-gradient(120deg,#6d28d9 0%,#7c3aed 50%,#8b5cf6 100%)',  # PURPLE
                'color': 'white',
                'border': 'none',
                'borderRadius': '14px',
                'width': '56px',
                'height': '42px',
                'cursor': 'pointer',
                'boxShadow': '0 4px 18px -4px rgba(124,58,237,0.45)',  # Purple glow
                'transition': 'all .28s cubic-bezier(.4,0,.2,1)',
                'display': 'none' if is_fullscreen else 'flex',
                'alignItems': 'center',
                'justifyContent': 'center',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontSize': '15px',
                'opacity': '.95',
                'backdropFilter': 'blur(6px)',
                'marginTop': '10px'
            }
        )
    
    def _create_header(self, runs_df: pd.DataFrame, is_fullscreen: bool, yaml_controls=None, quantstats_controls=None) -> html.Div:
        """Erstellt Header mit zentrierter Überschrift"""
        # NEU: Info-Bar Daten aus erster Zeile
        info_bar = html.Div()
        if not runs_df.empty:
            row = runs_df.iloc[0]
            run_started = self._fmt_ns_timestamp(row.get('run_started'))
            run_finished = self._fmt_ns_timestamp(row.get('run_finished'))
            backtest_start = self._fmt_ns_timestamp(row.get('backtest_start'))
            backtest_end = self._fmt_ns_timestamp(row.get('backtest_end'))
            elapsed_time = self._fmt_elapsed(row.get('elapsed_time'))

            if is_fullscreen:
                # Vollformat (bestehende Chips beibehalten)
                def chip(label, value):
                    return html.Span([
                        html.Span(label, style={
                            'fontWeight': '600',
                            'color': '#1f2937',
                            'marginRight': '4px'
                        }),
                        html.Span(value, style={
                            'fontWeight': '500',
                            'color': '#374151'
                        })
                    ], style={
                        'display': 'inline-flex',
                        'alignItems': 'center',
                        'gap': '2px',
                        'background': 'linear-gradient(135deg,rgba(255,255,255,0.55),rgba(255,255,255,0.35))',
                        'padding': '4px 10px',
                        'borderRadius': '10px',
                        'border': '1px solid rgba(167,139,250,0.55)',
                        'boxShadow': '0 1px 2px rgba(124,58,237,0.10) inset',
                        'backdropFilter': 'blur(6px)',
                        'fontSize': '10.5px'
                    })

                info_bar = html.Div([
                    chip('Run Started', run_started),
                    chip('Run Finished', run_finished),
                    chip('Backtest Start', backtest_start),
                    chip('Backtest End', backtest_end),
                    chip('Backtest Duration', elapsed_time)
                ], style={
                    'display': 'flex',
                    'flexWrap': 'wrap',
                    'gap': '6px',
                    'justifyContent': 'center',
                    'padding': '8px 14px 12px 14px',
                    'paddingRight': '220px',   # was 260px
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'letterSpacing': '0.15px',
                    'background': 'linear-gradient(100deg,#f5f3ff 0%,#faf5ff 60%,rgba(255,255,255,0.9) 100%)'
                })
            else:
                # NEU: Vertikale, sehr schlanke Liste ohne Kachel-/Box-Styling
                def row(label, value):
                    return html.Div([
                        html.Span(f"{label}:", style={
                            'fontWeight': '600',
                            'color': '#111827',
                            'marginRight': '6px'
                        }),
                        html.Span(value, style={
                            'fontWeight': '400',
                            'color': '#374151'
                        })
                    ], style={
                        'display': 'flex',
                        'alignItems': 'baseline',
                        'fontSize': '11px',
                        'lineHeight': '1.15'
                    })

                info_bar = html.Div([
                    row('Run Started', run_started),
                    row('Run Finished', run_finished),
                    row('Backtest', f"{backtest_start} → {backtest_end}"),
                    row('Backtest Duration', elapsed_time)  # renamed
                ], style={
                    'display': 'flex',
                    'flexDirection': 'column',
                    'gap': '3px',
                    'padding': '6px 14px 8px 14px',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'background': 'linear-gradient(90deg,#fafafa 0%,#ffffff 100%)',
                    'borderBottom': '1px solid rgba(229,231,235,0.85)',
                    'boxSizing': 'border-box'
                })

        header_style = {
            'background': 'linear-gradient(145deg,#ffffff 0%,#f8fafc 55%,#eef2f6 100%)',
            'backdropFilter': 'blur(20px)',
            'borderBottom': '1px solid rgba(226,232,240,0.9)',
            'position': 'relative',
            'boxShadow': '0 2px 6px -2px rgba(0,0,0,0.06)',
            'overflow': 'visible',
            'zIndex': 18000   # NEU höher als Tabelle
        }

        # Controls absolut ganz rechts oben im Header platzieren
        toolbar = None
        if is_fullscreen:
            def has_content(block):
                return bool(block and getattr(block, "children", None) and
                            not (isinstance(block.style, dict) and block.style.get("height") == "0px"))
            yc_ok = has_content(yaml_controls)
            qc_ok = has_content(quantstats_controls)
            if yc_ok or qc_ok:
                toolbar_children = []
                if yc_ok:
                    toolbar_children.append(html.Div(yaml_controls, style={'display': 'flex'}))
                if yc_ok and qc_ok:
                    toolbar_children.append(html.Div(style={
                        'width': '1px',
                        'alignSelf': 'stretch',
                        'background': 'rgba(0,0,0,0.08)',
                        'margin': '0 6px'
                    }))
                if qc_ok:
                    toolbar_children.append(html.Div(quantstats_controls, style={'display': 'flex'}))
                toolbar = html.Div(
                    toolbar_children,
                    className="run-tools-toolbar",
                    style={
                        'position': 'absolute',
                        'top': '5px',      # was 6px
                        'right': '16px',
                        'display': 'flex',
                        'alignItems': 'center',
                        'gap': '8px',
                        'padding': '3px 9px',  # tighter
                        'background': 'linear-gradient(135deg,rgba(255,255,255,0.92),rgba(248,250,252,0.96))',
                        'backdropFilter': 'blur(8px)',
                        'border': '1px solid rgba(226,232,240,0.9)',
                        'borderRadius': '10px',
                        'boxShadow': '0 3px 10px -3px rgba(0,0,0,0.14)',
                        'zIndex': 20000,   # NEU
                        'overflow': 'visible',
                        'lineHeight': '1'
                    }
                )
        return html.Div([
            html.Div([
                info_bar,
                toolbar
            ], style={
                'position': 'relative',
                'paddingTop': '2px',
                'paddingBottom': '6px',
                'borderBottom': '1px solid rgba(196,181,253,0.6)',
                'marginBottom': '2px',
                'overflow': 'visible'
            }),
            html.Div([
                html.H2("Backtest Runs", style={
                    'color': '#1a1a1a',  # vorher #2e1065
                    'margin': '0',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontWeight': '700',
                    'fontSize': '30px' if is_fullscreen else '26px',
                    'letterSpacing': '-0.03em',
                    'textAlign': 'center',
                    'textShadow': '0 1px 0 rgba(255,255,255,0.7)'
                }),
                html.Div([
                    html.Span(f"{len(runs_df)}", style={
                        'color': '#7c3aed',
                        'fontWeight': '700',
                        'fontSize': ('17px' if is_fullscreen else '15px')  # verkleinert
                    }),
                    html.Span(" total runs", style={
                        'color': '#374151',
                        'fontSize': ('17px' if is_fullscreen else '15px'),  # gleiche kleinere Größe
                        'marginLeft': '4px',
                        'fontWeight': '500'
                    })
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center',
                    'marginTop': '6px'
                })
            ], style={
                'padding': '16px 26px 4px 26px'
            })
        ], style=header_style)
    
    def _create_main_content(self, run_table, equity_charts, fullscreen_button, is_fullscreen: bool) -> html.Div:
        """Erstellt Hauptinhalt-Container"""
        param_analyzer_btn = html.Button(
            "Parameter Analyzer",
            id="param-analyzer-open-btn",
            style={
                'display': 'flex' if is_fullscreen else 'none',
                'marginTop': '4px',
                'background': 'linear-gradient(90deg,#4338ca 0%,#6366f1 50%,#8b5cf6 100%)',
                'color': '#fff',
                'border': 'none',
                'borderRadius': '12px',
                'padding': '10px 20px',
                'fontFamily': 'Inter,system-ui,sans-serif',
                'fontWeight': '600',
                'cursor': 'pointer',
                'boxShadow': '0 4px 14px -2px rgba(99,102,241,0.45)',
                'letterSpacing': '.5px'
            }
        )
        analyzer_panel = html.Div(id="param-analyzer-panel", style={
            'display': 'none',
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '100vw',
            'height': '100vh',
            'zIndex': '35000',  # war 1100, jetzt garantiert ganz oben!
            'background': 'linear-gradient(135deg,rgba(17,24,39,0.92),rgba(17,24,39,0.96))',
            'backdropFilter': 'blur(12px)',
            'padding': '40px 48px',
            'overflowY': 'auto',
            'boxSizing': 'border-box'
        }, children=[
            html.Button("Close ✕", id="param-analyzer-close-btn", style={
                'position': 'absolute',
                'top': '24px',
                'right': '28px',
                'background': '#334155',
                'color': '#e2e8f0',
                'border': '1px solid #475569',
                'borderRadius': '10px',
                'padding': '10px 18px',
                'cursor': 'pointer',
                'fontFamily': 'Inter',
                'fontWeight': '600',
                'fontSize': '14px',
                'boxShadow': '0 4px 14px -2px rgba(0,0,0,0.55)'
            }),
            html.Div(id="param-analyzer-content")
        ])

        return html.Div([
            run_table,
            equity_charts,
            param_analyzer_btn,
            analyzer_panel,
            html.Div([fullscreen_button], style={
                'display': 'flex' if not is_fullscreen else 'none',
                'justifyContent': 'center',
                'paddingTop': '18px',
                'borderTop': '1px solid rgba(226,232,240,0.55)',
                'marginTop': '18px'
            })
        ], style={
            'padding': '28px 30px 26px 30px' if is_fullscreen else '22px 26px 26px 26px',
            'height': 'calc(100vh - 130px)',
            'overflowY': 'auto',
            'overflowX': 'hidden',
            'display': 'flex',
            'flexDirection': 'column',
            'rowGap': '14px',
            'scrollbarWidth': 'thin'
        })
