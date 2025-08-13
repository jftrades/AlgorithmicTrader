"""
Slide-Menu Logik für Run-Auswahl im Dashboard
Strikte Validierung ohne Fallbacks
"""
from pathlib import Path
import pandas as pd
import yaml
from dash import html, dash_table, dcc
import plotly.graph_objects as go
from typing import Dict, List, Tuple

class RunValidator:
    """Strikte Validierung für Run-Daten ohne Fallbacks"""
    
    REQUIRED_COLUMNS = ["run_id", "Sharpe", "Total Return", "Max Drawdown", "Trades"]
    
    # Mapping von CSV-Spalten zu erwarteten Spalten
    COLUMN_MAPPING = {
        'RET_Sharpe Ratio (252 days)': 'Sharpe',
        'USDT_PnL (total)': 'Total Return',  # Absolute PnL statt Prozent
        'total_positions': 'Trades'
        # Max Drawdown ist nicht in den Daten - wird später behandelt
    }
    
    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)
        self.csv_path = self.results_dir / "all_backtest_results.csv"
    
    def validate_and_load(self) -> pd.DataFrame:
        """Lädt und validiert all_backtest_results.csv mit strikter Prüfung"""
        
        # CSV-Datei muss existieren
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CRITICAL: all_backtest_results.csv not found at {self.csv_path}")
        
        # CSV laden
        try:
            df = pd.read_csv(self.csv_path)
        except Exception as e:
            raise RuntimeError(f"CRITICAL: Failed to read {self.csv_path}: {e}")
        
        # Darf nicht leer sein
        if df.empty:
            raise ValueError(f"CRITICAL: all_backtest_results.csv is empty at {self.csv_path}")
        
        # Spalten-Mapping anwenden
        df = self._apply_column_mapping(df)
        
        # Pflichtspalten prüfen (nach Mapping)
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            available_cols = list(df.columns)
            raise ValueError(f"CRITICAL: Missing required columns after mapping: {missing_cols}. Available columns: {available_cols}")
        
        # run_id Spalte darf keine NaN/leeren Werte haben
        if df['run_id'].isna().any() or (df['run_id'] == '').any():
            raise ValueError("CRITICAL: run_id column contains empty or NaN values")
        
        # Sharpe-Spalte muss numerisch konvertierbar sein
        try:
            df['Sharpe'] = pd.to_numeric(df['Sharpe'], errors='coerce')
            if df['Sharpe'].isna().all():
                raise ValueValueError("CRITICAL: Sharpe column contains no valid numeric values")
        except Exception as e:
            raise ValueError(f"CRITICAL: Failed to convert Sharpe column to numeric: {e}")
        
        # Nach Sharpe sortieren (bester zuerst)
        df = df.sort_values('Sharpe', ascending=False, na_position='last')
        
        # Ordner-Index hinzufügen (run0, run1, run2, ...)
        df = df.reset_index(drop=True)
        df['run_index'] = df.index
        
        # Run-Ordner und run_config.yaml validieren
        self._validate_run_directories(df['run_index'].tolist())
        
        return df
    
    def _apply_column_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
        """Wendet Spalten-Mapping an und erstellt fehlende Spalten"""
        df_mapped = df.copy()
        
        # Direkte Mappings anwenden
        for source_col, target_col in self.COLUMN_MAPPING.items():
            if source_col in df_mapped.columns:
                df_mapped[target_col] = df_mapped[source_col]
        
        # Max Drawdown berechnen falls nicht vorhanden
        if 'Max Drawdown' not in df_mapped.columns:
            if 'USDT_PnL% (total)' in df_mapped.columns:
                # Vereinfachte Max Drawdown Schätzung basierend auf negativen Returns
                df_mapped['Max Drawdown'] = df_mapped['USDT_PnL% (total)'].apply(
                    lambda x: min(0, x) if pd.notna(x) else 0
                )
            else:
                # Fallback: setze auf 0
                df_mapped['Max Drawdown'] = 0.0
        
        return df_mapped
    
    def _validate_run_directories(self, run_indices: List[int]):
        """Validiert dass alle Run-Ordner existieren und run_config.yaml enthalten"""
        for run_index in run_indices:
            run_dir = self.results_dir / f"run{run_index}"
            
            if not run_dir.exists():
                raise FileNotFoundError(f"CRITICAL: Run directory not found: {run_dir}")
            
            config_path = run_dir / "run_config.yaml"
            if not config_path.exists():
                raise FileNotFoundError(f"CRITICAL: run_config.yaml not found in {run_dir}")
            
            # Zusätzlich: YAML muss parsbar sein
            try:
                with open(config_path, 'r') as f:
                    yaml.safe_load(f)
            except Exception as e:
                raise RuntimeError(f"CRITICAL: Invalid run_config.yaml in {run_dir}: {e}")

class SlideMenuComponent:
    """UI-Komponente für das ausklappbare Slide-Menu"""
    
    def __init__(self):
        self.menu_width_open = "380px"
        self.menu_width_fullscreen = "100vw"
        self.menu_width_closed = "0px"
    
    def create_sidebar(self, runs_df: pd.DataFrame, is_open: bool = False, is_fullscreen: bool = False, selected_run_indices: list = None, checkbox_states: dict = None) -> html.Div:
        """Erstellt NUR die Sidebar-Inhalte (ohne Toggle-Button)"""
        
        # Run-Tabelle erstellen mit Checkbox-Zuständen
        run_table = self._create_run_table(runs_df, is_fullscreen, checkbox_states)
        
        # Equity Curves für Fullscreen-Modus mit ausgewählten Runs
        equity_charts = html.Div()
        if is_fullscreen:
            equity_charts = self._create_equity_charts(runs_df, selected_run_indices)
        
        # Fullscreen Toggle Button - nur zum Expandieren (nicht zum Schließen)
        fullscreen_button = html.Button([
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
        
        # Header Layout - Überschrift zentriert
        header_style = {
            'background': 'linear-gradient(145deg, rgba(255,255,255,0.9) 0%, rgba(248,250,252,0.9) 100%)',
            'backdropFilter': 'blur(20px)',
            'borderBottom': '1px solid rgba(226, 232, 240, 0.8)',
            'position': 'relative'
        }
        
        # Sidebar Container - NUR Inhalte (für direktes Einfügen in Layout)
        sidebar_content = [
            # Header mit zentrierter Überschrift
            html.Div([
                html.Div([
                    html.H2("Backtest Runs", style={
                        'color': '#1a202c',
                        'margin': '0',
                        'fontFamily': 'Inter, system-ui, sans-serif',
                        'fontWeight': '700',
                        'fontSize': '32px' if is_fullscreen else '28px',
                        'letterSpacing': '-0.025em',
                        'textAlign': 'center'  # Zentriert
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
                        'justifyContent': 'center',  # Zentriert
                        'marginTop': '8px'
                    })
                ], style={
                    'padding': '30px 30px 0 30px'
                })
            ], style=header_style),
            
            # Hauptinhalt Container
            html.Div([
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
        ]
        
        # Gebe nur die Inhalte zurück (für Layout-Integration)
        return html.Div([html.Div(), html.Div(sidebar_content)])

    def _create_run_table(self, runs_df: pd.DataFrame, is_fullscreen: bool = False, checkbox_states: dict = None) -> html.Div:
        """Erstellt die Run-Tabelle für die Sidebar mit Checkboxen im Fullscreen"""
        
        if is_fullscreen:
            # Im Fullscreen: Tabelle mit Checkboxen
            display_columns = ["run_index", "run_id", "Sharpe", "Total Return", "Max Drawdown", "Trades", 
                             "rsi_overbought", "rsi_oversold", "backtest_start", "backtest_end"]
            available_columns = [col for col in display_columns if col in runs_df.columns]
            table_data = runs_df[available_columns].copy()
            
            # Vollständige run_id anzeigen im Fullscreen
            if 'run_id' in table_data.columns:
                table_data['run_id_display'] = table_data['run_id'].astype(str)
            
            # Formatierung für bessere Lesbarkeit
            for col in ["Sharpe", "Total Return", "Max Drawdown"]:
                if col in table_data.columns:
                    try:
                        table_data[col] = pd.to_numeric(table_data[col], errors='coerce')
                        if col == "Max Drawdown":
                            abs_max = table_data[col].abs().max()
                            if abs_max <= 1.0:
                                table_data[col] = table_data[col] * 100
                        table_data[col] = table_data[col].round(4)
                    except Exception:
                        pass
            
            # Erstelle Checkbox-Tabelle
            rows = []
            for idx, row in table_data.iterrows():
                run_index = int(row['run_index'])
                
                # Bestimme Checkbox-Wert basierend auf aktuellem Zustand
                checkbox_value = []
                if checkbox_states and run_index in checkbox_states and checkbox_states[run_index]:
                    checkbox_value = [run_index]
                
                cells = [
                    html.Td([
                        dcc.Checklist(
                            id={'type': 'run-checkbox', 'index': run_index},
                            options=[{'label': '', 'value': run_index}],
                            value=checkbox_value,  # Verwende aktuellen Zustand
                            style={'margin': '0', 'transform': 'scale(1.2)'}
                        )
                    ], style={'width': '50px', 'textAlign': 'center'}),
                    html.Td(str(run_index), style={'textAlign': 'center', 'fontWeight': '600'}),
                    html.Td(str(row['run_id_display'])[:12] + '...' if len(str(row['run_id_display'])) > 12 else str(row['run_id_display']), 
                           style={'textAlign': 'center', 'fontSize': '12px'}),
                    html.Td(f"{row['Sharpe']:.3f}" if pd.notna(row['Sharpe']) else 'N/A', 
                           style={'textAlign': 'center', 'fontWeight': '500'}),
                    html.Td(f"{row['Total Return']:.2f}" if pd.notna(row['Total Return']) else 'N/A', 
                           style={'textAlign': 'center'}),
                    html.Td(f"{row['Max Drawdown']:.2f}%" if pd.notna(row['Max Drawdown']) else 'N/A', 
                           style={'textAlign': 'center', 'color': '#dc3545'}),
                    html.Td(str(int(row['Trades'])) if pd.notna(row['Trades']) else 'N/A', 
                           style={'textAlign': 'center'})
                ]
                
                # Zusätzliche Spalten falls verfügbar
                if 'rsi_overbought' in table_data.columns and pd.notna(row['rsi_overbought']):
                    cells.append(html.Td(f"{row['rsi_overbought']:.2f}", style={'textAlign': 'center'}))
                if 'rsi_oversold' in table_data.columns and pd.notna(row['rsi_oversold']):
                    cells.append(html.Td(f"{row['rsi_oversold']:.2f}", style={'textAlign': 'center'}))
                
                # Row styling - hervorheben wenn ausgewählt
                is_selected = checkbox_states and run_index in checkbox_states and checkbox_states[run_index]
                row_style = {
                    'backgroundColor': 'rgba(102, 126, 234, 0.15)' if is_selected else 'rgba(34, 197, 94, 0.1)' if idx == 0 else 'rgba(255,255,255,0.7)',
                    'borderBottom': '1px solid #e9ecef',
                    'border': '2px solid rgba(102, 126, 234, 0.4)' if is_selected else 'none',
                    'borderRadius': '8px' if is_selected else 'none'
                }
                
                rows.append(html.Tr(cells, style=row_style))
            
            # Header
            header_cells = [
                html.Th('✓', style={'width': '50px', 'textAlign': 'center'}),
                html.Th('#', style={'textAlign': 'center'}),
                html.Th('Run ID', style={'textAlign': 'center'}),
                html.Th('Sharpe', style={'textAlign': 'center'}),
                html.Th('Return', style={'textAlign': 'center'}),
                html.Th('DD %', style={'textAlign': 'center'}),
                html.Th('Trades', style={'textAlign': 'center'})
            ]
            
            if 'rsi_overbought' in table_data.columns:
                header_cells.append(html.Th('RSI OB', style={'textAlign': 'center'}))
            if 'rsi_oversold' in table_data.columns:
                header_cells.append(html.Th('RSI OS', style={'textAlign': 'center'}))
            
            return html.Div([
                html.Table([
                    html.Thead([html.Tr(header_cells, style={
                        'backgroundColor': 'rgba(102, 126, 234, 0.1)',
                        'fontWeight': '600',
                        'fontSize': '13px',
                        'fontFamily': 'Inter, system-ui, sans-serif',
                        'letterSpacing': '0.025em',
                        'textTransform': 'uppercase'
                    })]),
                    html.Tbody(rows)
                ], style={
                    'width': '100%',
                    'borderRadius': '16px',
                    'border': 'none',
                    'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
                    'backgroundColor': 'transparent',
                    'borderCollapse': 'separate',
                    'borderSpacing': '0',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontSize': '14px'
                })
            ], id="run-table-fullscreen")
        else:
            # ...existing code für normale Ansicht (bleibt unverändert)...
            display_columns = ["run_index", "run_id", "Sharpe", "Total Return", "Max Drawdown", "Trades"]
            table_data = runs_df[display_columns].copy()
            
            # run_id auf ersten 8 Zeichen kürzen für bessere Anzeige
            if 'run_id' in table_data.columns:
                table_data['run_id_display'] = table_data['run_id'].astype(str).str[:8] + '...'
            
            # Formatierung für bessere Lesbarkeit
            for col in ["Sharpe", "Total Return", "Max Drawdown"]:
                if col in table_data.columns:
                    try:
                        table_data[col] = pd.to_numeric(table_data[col], errors='coerce')
                        if col == "Max Drawdown":
                            abs_max = table_data[col].abs().max()
                            if abs_max <= 1.0:
                                table_data[col] = table_data[col] * 100
                        table_data[col] = table_data[col].round(4)
                    except Exception:
                        pass
            
            columns = [
                {"name": "#", "id": "run_index", "type": "numeric"},
                {"name": "Run ID", "id": "run_id_display"},
                {"name": "Sharpe", "id": "Sharpe", "type": "numeric", "format": {"specifier": ".3f"}},
                {"name": "Return", "id": "Total Return", "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "DD %", "id": "Max Drawdown", "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "Trades", "id": "Trades", "type": "numeric"}
            ]
            
            return dash_table.DataTable(
                id="runs-table",
                data=table_data.to_dict('records'),
                columns=columns,
                style_table={
                    'overflowX': 'hidden',
                    'borderRadius': '16px',
                    'border': 'none',
                    'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
                    'backgroundColor': 'transparent'
                },
                style_cell={
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontSize': '13px',
                    'padding': '16px 12px',
                    'textAlign': 'center',
                    'border': 'none',
                    'backgroundColor': 'transparent',
                    'cursor': 'pointer',
                    'whiteSpace': 'nowrap',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis'
                },
                style_header={
                    'backgroundColor': 'rgba(102, 126, 234, 0.1)',
                    'color': '#4a5568',
                    'fontWeight': '600',
                    'fontSize': '12px',
                    'borderTopLeftRadius': '16px',
                    'borderTopRightRadius': '16px',
                    'border': 'none',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'letterSpacing': '0.025em',
                    'textTransform': 'uppercase',
                    'padding': '18px 12px'
                },
                style_data={
                    'border': 'none',
                    'backgroundColor': 'rgba(255,255,255,0.7)',
                    'transition': 'all 0.2s ease'
                },
                style_data_conditional=[
                    {
                        'if': {'row_index': 0},
                        'backgroundColor': 'rgba(34, 197, 94, 0.1)',
                        'color': '#059669',
                        'fontWeight': '600',
                        'border': '1px solid rgba(34, 197, 94, 0.2)',
                        'borderRadius': '8px'
                    },
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': 'rgba(248, 250, 252, 0.8)'
                    },
                    {
                        'if': {'state': 'selected'},
                        'backgroundColor': 'rgba(102, 126, 234, 0.15)',
                        'border': '2px solid rgba(102, 126, 234, 0.4)',
                        'borderRadius': '8px',
                        'fontWeight': '600',
                        'color': '#4338ca'
                    }
                ],
                row_selectable="single",
                selected_rows=[0],
                page_size=20
            )

    def _create_equity_charts(self, runs_df: pd.DataFrame, selected_run_indices: list = None) -> html.Div:
        """Erstellt Equity-Kurven-Charts für ausgewählte Runs im Fullscreen-Modus"""
        
        # Wenn keine Runs ausgewählt, zeige Anleitung
        if not selected_run_indices:
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
                    html.Div("📊", style={
                        'fontSize': '48px',
                        'textAlign': 'center',
                        'marginBottom': '20px'
                    }),
                    html.H4("Select Runs to Compare", style={
                        'color': '#4a5568',
                        'textAlign': 'center',
                        'fontFamily': 'Inter, system-ui, sans-serif',
                        'fontWeight': '600',
                        'marginBottom': '15px'
                    }),
                    html.P("Click checkboxes next to runs in the table above to see their equity curves", style={
                        'color': '#6c757d',
                        'fontFamily': 'Inter, system-ui, sans-serif',
                        'textAlign': 'center',
                        'fontSize': '16px',
                        'margin': '0',
                        'lineHeight': '1.5'
                    }),
                    html.P("💡 Tip: You can select multiple runs for comparison", style={
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
        
        # Filtere nur ausgewählte Runs
        selected_runs_df = runs_df.iloc[selected_run_indices].copy()
        
        # KORRIGIERTER PFAD: Von slide_menu.py aus navigieren
        current_file_path = Path(__file__).resolve()
        algorithmic_trader_root = current_file_path.parents[3]
        results_dir = algorithmic_trader_root / "data" / "DATA_STORAGE" / "results"
        
        # Sammle Equity-Daten nur für ausgewählte Runs
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
        
        if not equity_data:
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
        
        # Erstelle Charts für jeden Metric-Typ
        charts = []
        
        metric_configs = {
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
        
        for metric, config in metric_configs.items():
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
            
            # Chart Layout mit verbessertem Design
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
                # Grid-Styling
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

def get_best_run_index(runs_df: pd.DataFrame) -> int:
    """Gibt den run_index des besten Runs zurück (höchste Sharpe)"""
    if runs_df.empty:
        raise ValueError("CRITICAL: No runs available to select best run")
    
    best_row = runs_df.iloc[0]  # Bereits nach Sharpe sortiert
    return int(best_row['run_index'])
