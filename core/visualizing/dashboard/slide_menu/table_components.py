"""
Tabellen-Komponenten für das Slide-Menu
"""
import pandas as pd
from dash import html, dash_table, dcc

class RunTableBuilder:
    """Erstellt Run-Tabellen für normale und Fullscreen-Ansicht"""
    
    def create_table(self, runs_df: pd.DataFrame, is_fullscreen: bool = False, checkbox_states: dict = None) -> html.Div:
        """Hauptmethode für Tabellen-Erstellung"""
        if is_fullscreen:
            return self._create_fullscreen_table(runs_df, checkbox_states)
        else:
            return self._create_normal_table(runs_df)
    
    def _create_fullscreen_table(self, runs_df: pd.DataFrame, checkbox_states: dict = None) -> html.Div:
        """Erstellt Fullscreen-Tabelle mit Checkboxen"""
        display_columns = ["run_index", "run_id", "Sharpe", "Total Return", "Max Drawdown", "Trades", 
                         "rsi_overbought", "rsi_oversold", "backtest_start", "backtest_end"]
        available_columns = [col for col in display_columns if col in runs_df.columns]
        table_data = runs_df[available_columns].copy()
        
        # Vollständige run_id anzeigen im Fullscreen
        if 'run_id' in table_data.columns:
            table_data['run_id_display'] = table_data['run_id'].astype(str)
        
        # Daten formatieren
        table_data = self._format_table_data(table_data)
        
        # Tabellen-Zeilen erstellen
        rows = self._create_table_rows(table_data, checkbox_states)
        
        # Header erstellen
        header_cells = self._create_fullscreen_header(table_data)
        
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
    
    def _create_normal_table(self, runs_df: pd.DataFrame) -> dash_table.DataTable:
        """Erstellt normale DataTable"""
        display_columns = ["run_index", "run_id", "Sharpe", "Total Return", "Max Drawdown", "Trades"]
        table_data = runs_df[display_columns].copy()
        
        # run_id auf ersten 8 Zeichen kürzen für bessere Anzeige
        if 'run_id' in table_data.columns:
            table_data['run_id_display'] = table_data['run_id'].astype(str).str[:8] + '...'
        
        # Daten formatieren
        table_data = self._format_table_data(table_data)
        
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
    
    def _format_table_data(self, table_data: pd.DataFrame) -> pd.DataFrame:
        """Formatiert Tabellendaten für bessere Lesbarkeit"""
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
        return table_data
    
    def _create_table_rows(self, table_data: pd.DataFrame, checkbox_states: dict = None) -> list:
        """Erstellt Tabellen-Zeilen mit Checkboxen"""
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
                        value=checkbox_value,
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
        
        return rows
    
    def _create_fullscreen_header(self, table_data: pd.DataFrame) -> list:
        """Erstellt Header für Fullscreen-Tabelle"""
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
        
        return header_cells
