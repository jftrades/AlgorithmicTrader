"""
Hauptkomponente für das Slide-Menu
Orchestriert die verschiedenen Subkomponenten
"""
import pandas as pd
from dash import html
from .table_components import RunTableBuilder
from .chart_components import EquityChartsBuilder

class SlideMenuComponent:
    """UI-Komponente für das ausklappbare Slide-Menu"""
    
    def __init__(self):
        self.menu_width_open = "380px"
        self.menu_width_fullscreen = "100vw"
        self.menu_width_closed = "0px"
        
        # Subkomponenten
        self.table_builder = RunTableBuilder()
        self.charts_builder = EquityChartsBuilder()
    
    def create_sidebar(self, runs_df: pd.DataFrame, is_open: bool = False, is_fullscreen: bool = False, 
                      selected_run_indices: list = None, checkbox_states: dict = None) -> html.Div:
        """Erstellt NUR die Sidebar-Inhalte (ohne Toggle-Button)"""
        
        # Run-Tabelle erstellen
        run_table = self.table_builder.create_table(runs_df, is_fullscreen, checkbox_states)
        
        # Equity Curves für Fullscreen-Modus
        equity_charts = html.Div()
        if is_fullscreen:
            equity_charts = self.charts_builder.create_equity_charts(runs_df, selected_run_indices)
        
        # Fullscreen Toggle Button
        fullscreen_button = self._create_fullscreen_button(is_fullscreen)
        
        # Header Layout
        header = self._create_header(runs_df, is_fullscreen)
        
        # Hauptinhalt Container
        main_content = self._create_main_content(run_table, equity_charts, fullscreen_button, is_fullscreen)
        
        # Sidebar Container - NUR Inhalte (für direktes Einfügen in Layout)
        sidebar_content = [header, main_content]
        
        # Gebe nur die Inhalte zurück (für Layout-Integration)
        return html.Div([html.Div(), html.Div(sidebar_content)])
    
    def _create_fullscreen_button(self, is_fullscreen: bool) -> html.Button:
        """Erstellt Fullscreen Toggle Button"""
        return html.Button([
            html.Div("⛶", style={
                'fontSize': '18px',
                'lineHeight': '1'
            })
        ],
            id="fullscreen-toggle-btn",
            style={
                'background': 'linear-gradient(135deg, #28a745 0%, #20c997 100%)',
                'color': 'white',
                'border': 'none',
                'borderRadius': '50%',
                'width': '50px',
                'height': '50px',
                'cursor': 'pointer',
                'boxShadow': '0 6px 20px rgba(40, 167, 69, 0.4)',
                'transition': 'all 0.3s cubic-bezier(0.4, 0.0, 0.2, 1)',
                'display': 'none' if is_fullscreen else 'flex',
                'alignItems': 'center',
                'justifyContent': 'center',
                'fontFamily': 'monospace',
                'fontSize': '16px',
                'opacity': '1',
                'transform': 'scale(1)',
                'marginTop': '15px'
            }
        )
    
    def _create_header(self, runs_df: pd.DataFrame, is_fullscreen: bool) -> html.Div:
        """Erstellt Header mit zentrierter Überschrift"""
        header_style = {
            'background': 'linear-gradient(145deg, rgba(255,255,255,0.9) 0%, rgba(248,250,252,0.9) 100%)',
            'backdropFilter': 'blur(20px)',
            'borderBottom': '1px solid rgba(226, 232, 240, 0.8)',
            'position': 'relative'
        }
        
        return html.Div([
            html.Div([
                html.H2("Backtest Runs", style={
                    'color': '#1a202c',
                    'margin': '0',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontWeight': '700',
                    'fontSize': '32px' if is_fullscreen else '28px',
                    'letterSpacing': '-0.025em',
                    'textAlign': 'center'
                }),
                html.Div([
                    html.Span(f"{len(runs_df)}", style={
                        'color': '#667eea',
                        'fontWeight': '700',
                        'fontSize': '20px' if is_fullscreen else '18px'
                    }),
                    html.Span(" total runs", style={
                        'color': '#718096',
                        'fontSize': '18px' if is_fullscreen else '16px',
                        'marginLeft': '4px'
                    })
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center',
                    'marginTop': '8px'
                })
            ], style={
                'padding': '30px 30px 0 30px'
            })
        ], style=header_style)
    
    def _create_main_content(self, run_table, equity_charts, fullscreen_button, is_fullscreen: bool) -> html.Div:
        """Erstellt Hauptinhalt-Container"""
        return html.Div([
            # Run-Tabelle
            run_table,
            
            # Equity Charts (nur im Fullscreen)
            equity_charts,
            
            # Fullscreen-Button am Ende (nur wenn nicht im Fullscreen)
            html.Div([
                fullscreen_button
            ], style={
                'display': 'flex' if not is_fullscreen else 'none',
                'justifyContent': 'flex-end',
                'paddingTop': '20px',
                'borderTop': '1px solid rgba(226, 232, 240, 0.5)',
                'marginTop': '20px'
            })
        ], style={
            'padding': '30px' if is_fullscreen else '25px 30px 30px 30px',
            'height': 'calc(100vh - 140px)',
            'overflowY': 'auto',
            'overflowX': 'hidden',
            'display': 'flex',
            'flexDirection': 'column'
        })
