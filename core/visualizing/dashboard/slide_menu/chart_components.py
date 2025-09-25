"""
Chart-Komponenten für Equity-Kurven im Slide-Menu
"""
from pathlib import Path
import pandas as pd
from dash import html, dcc
import plotly.graph_objects as go

class EquityChartsBuilder:
    """Erstellt Equity-Kurven für ausgewählte Runs"""
    
    def __init__(self):
        self.metric_configs = {
            'total_equity': {
                'title': 'Total Equity Evolution',
                'color_scheme': ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b'],
                'unit': 'USDT',
                'description': 'Account balance over time'
            },
            'total_position': {
                'title': 'Position Size Over Time', 
                'color_scheme': ['#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#ff9896', '#c5b0d5'],
                'unit': 'Size',
                'description': 'Active position sizes'
            },
            'total_realized_pnl': {
                'title': 'Realized PnL Accumulation',
                'color_scheme': ['#2ca02c', '#d62728', '#ff7f0e', '#1f77b4', '#9467bd', '#8c564b'],
                'unit': 'USDT',
                'description': 'Cumulative realized profits/losses'
            },
            'total_unrealized_pnl': {
                'title': 'Unrealized PnL Fluctuation',
                'color_scheme': ['#ff7f0e', '#2ca02c', '#d62728', '#1f77b4', '#9467bd', '#c5b0d5'],
                'unit': 'USDT',
                'description': 'Current unrealized profits/losses'
            }
        }
    
    def create_equity_charts(self, runs_df: pd.DataFrame, selected_run_indices: list = None) -> html.Div:
        """Hauptmethode für Equity-Charts"""
        
        # Wenn keine Runs ausgewählt, zeige Anleitung
        if not selected_run_indices:
            return self._create_instruction_panel()
        
        # Equity-Daten laden
        equity_data = self._load_equity_data(runs_df, selected_run_indices)
        
        if not equity_data:
            return self._create_no_data_panel()
        
        # Charts erstellen
        charts = self._create_charts(equity_data)
        
        return self._create_charts_container(equity_data, charts)
    
    def _create_instruction_panel(self) -> html.Div:
        """Erstellt Anleitung für Run-Auswahl"""
        return html.Div([
            html.H3("Equity Curves Analysis", style={
                'color': '#2c3e50',
                'marginTop': '30px',
                'marginBottom': '5px',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontWeight': '700',
                'fontSize': '24px',
                'borderBottom': '3px solid #667eea',
                'paddingBottom': '10px'
            }),
            html.Div([
                html.H4("Select Runs to Compare", style={
                    'color': '#4a5568',
                    'textAlign': 'center',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontWeight': '600',
                    'marginBottom': '15px',
                    'fontSize': '20px'
                }),
                html.P("Click checkboxes next to runs in the table above to see their equity curves", style={
                    'color': '#6c757d',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'textAlign': 'center',
                    'fontSize': '16px',
                    'margin': '0',
                    'lineHeight': '1.5'
                }),
                html.P("Tip: You can select multiple runs for comparison", style={
                    'color': '#9ca3af',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'textAlign': 'center',
                    'fontSize': '14px',
                    'margin': '15px 0 0 0',
                    'fontStyle': 'italic'
                })
            ], style={
                'backgroundColor': '#f8f9fa',
                'border': '2px dashed #d1d5db',
                'borderRadius': '16px',
                'padding': '40px 20px',
                'margin': '30px 0',
                'textAlign': 'center'
            })
        ], style={
            'marginTop': '30px',
            'borderTop': '2px solid rgba(102, 126, 234, 0.2)',
            'paddingTop': '20px'
        })
    
    def _create_no_data_panel(self) -> html.Div:
        """Erstellt Panel für fehlende Daten"""
        return html.Div([
            html.H3("Equity Curves Analysis", style={
                'color': '#2c3e50',
                'marginTop': '30px',
                'marginBottom': '15px',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontWeight': '600',
                'fontSize': '20px'
            }),
            html.Div([
                html.P("No data found for selected runs", style={
                    'color': '#dc3545',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'textAlign': 'center',
                    'fontWeight': '500'
                })
            ], style={
                'backgroundColor': '#fff5f5',
                'border': '1px solid #fed7d7',
                'borderRadius': '8px',
                'padding': '20px',
                'margin': '20px 0'
            })
        ])
    
    def _load_equity_data(self, runs_df: pd.DataFrame, selected_run_indices: list) -> dict:
        """Lädt Equity-Daten für ausgewählte Runs"""
        selected_runs_df = runs_df.iloc[selected_run_indices].copy()
        
        # Pfad zu Results-Verzeichnis
        current_file_path = Path(__file__).resolve()
        algorithmic_trader_root = current_file_path.parents[4]
        results_dir = algorithmic_trader_root / "data" / "DATA_STORAGE" / "results"
        
        equity_data = {}
        available_metrics = ['total_equity', 'total_position', 'total_realized_pnl', 'total_unrealized_pnl']
        
        for _, run_row in selected_runs_df.iterrows():
            run_id = str(run_row['run_id'])
            run_index = int(run_row['run_index'])
            
            run_dir = results_dir / run_id
            general_indicators_dir = run_dir / "general" / "indicators"
            
            if not run_dir.exists() or not general_indicators_dir.exists():
                continue
                
            run_data = {}
            for metric in available_metrics:
                csv_path = general_indicators_dir / f"{metric}.csv"
                
                if csv_path.exists():
                    try:
                        df = pd.read_csv(csv_path)
                        
                        if not df.empty and 'timestamp' in df.columns and 'value' in df.columns:
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns', errors='coerce')
                            df = df.dropna(subset=['timestamp', 'value'])
                            df['value'] = pd.to_numeric(df['value'], errors='coerce')
                            df = df.dropna(subset=['value'])
                            df = df.sort_values('timestamp').reset_index(drop=True)
                            
                            if not df.empty:
                                run_data[metric] = df
                    except Exception:
                        pass
            
            if run_data:
                run_id_short = run_id[:8] if len(run_id) > 8 else run_id
                display_name = f"Run{run_index} ({run_id_short})"
                equity_data[display_name] = run_data
        
        return equity_data
    
    def _create_charts(self, equity_data: dict) -> list:
        """Erstellt Charts für alle Metriken"""
        charts = []
        
        for metric, config in self.metric_configs.items():
            # Prüfe ob mindestens ein Run diesen Metric hat
            runs_with_metric = [run_name for run_name, run_data in equity_data.items() if metric in run_data]
            
            if not runs_with_metric:
                continue
                
            fig = go.Figure()
            
            for i, run_name in enumerate(runs_with_metric):
                df = equity_data[run_name][metric]
                color = config['color_scheme'][i % len(config['color_scheme'])]
                
                # Statistiken für bessere Hover-Info
                start_value = df['value'].iloc[0] if len(df) > 0 else 0
                end_value = df['value'].iloc[-1] if len(df) > 0 else 0
                change = end_value - start_value
                change_pct = (change / start_value * 100) if start_value != 0 else 0
                
                fig.add_trace(go.Scatter(
                    x=df['timestamp'],
                    y=df['value'],
                    mode='lines',
                    name=f"{run_name} ({change:+.2f} {config['unit']})",
                    line=dict(color=color, width=2.5),
                    hovertemplate=f'<b>{run_name}</b><br>' +
                                'Time: %{x|%Y-%m-%d %H:%M}<br>' +
                                f'Value: %{{y:,.2f}} {config["unit"]}<br>' +
                                f'Change: {change:+.2f} {config["unit"]} ({change_pct:+.1f}%)<br>' +
                                '<extra></extra>'
                ))
            
            # Chart Layout
            fig.update_layout(
                title={
                    'text': f"{config['title']}<br><sub style='font-size:12px;color:#666'>{config['description']}</sub>",
                    'font': {'size': 18, 'family': 'Inter, system-ui, sans-serif', 'color': '#2c3e50'},
                    'x': 0.5,
                    'xanchor': 'center'
                },
                xaxis_title="Time",
                yaxis_title=f"Value ({config['unit']})",
                template="plotly_white",
                hovermode='x unified',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    font=dict(size=11),
                    bgcolor="rgba(255,255,255,0.8)",
                    bordercolor="rgba(0,0,0,0.1)",
                    borderwidth=1
                ),
                margin=dict(t=80, b=50, l=70, r=30),
                height=380,
                plot_bgcolor="rgba(248,249,250,0.8)",
                xaxis=dict(
                    showgrid=True,
                    gridwidth=1,
                    gridcolor="rgba(0,0,0,0.1)",
                    zeroline=False
                ),
                yaxis=dict(
                    showgrid=True,
                    gridwidth=1,
                    gridcolor="rgba(0,0,0,0.1)",
                    zeroline=True,
                    zerolinecolor="rgba(0,0,0,0.3)",
                    zerolinewidth=1
                )
            )
            
            charts.append(
                html.Div([
                    dcc.Graph(
                        figure=fig,
                        config={
                            'displayModeBar': True, 
                            'displaylogo': False,
                            'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                            'toImageButtonOptions': {
                                'format': 'png',
                                'filename': f'{metric}_comparison',
                                'height': 500,
                                'width': 1200,
                                'scale': 1
                            }
                        }
                    )
                ], style={
                    'backgroundColor': 'white',
                    'borderRadius': '16px',
                    'padding': '20px',
                    'margin': '20px 0',
                    'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
                    'border': '1px solid rgba(226, 232, 240, 0.8)'
                })
            )
        
        return charts
    
    def _create_charts_container(self, equity_data: dict, charts: list) -> html.Div:
        """Erstellt Container für alle Charts"""
        return html.Div([
            html.Div([
                html.H3("Equity Curves Analysis", style={
                    'color': '#2c3e50',
                    'marginTop': '30px',
                    'marginBottom': '5px',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontWeight': '700',
                    'fontSize': '24px',
                    'borderBottom': '3px solid #667eea',
                    'paddingBottom': '10px'
                }),
                html.P(f"Comparing {len(equity_data)} selected runs across {len(charts)} metrics", style={
                    'color': '#718096',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontSize': '14px',
                    'marginBottom': '20px'
                })
            ]),
            html.Div(charts, style={
                'maxHeight': 'calc(60vh)',
                'overflowY': 'auto',
                'paddingRight': '10px'
            })
        ], style={
            'marginTop': '30px',
            'borderTop': '2px solid rgba(102, 126, 234, 0.2)',
            'paddingTop': '20px'
        })
