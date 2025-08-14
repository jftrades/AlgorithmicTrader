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
    
    def _extract_param_columns(self, runs_df: pd.DataFrame) -> list:
        """
        Liefert dynamisch alle Parameter-Spalten (alle Spalten vor 'run_id').
        Bedingungen:
          - 'run_id' muss existieren
          - Parameter-Spalten werden in Original-Reihenfolge übernommen
        """
        if 'run_id' not in runs_df.columns:
            return []
        cols = list(runs_df.columns)
        cut = cols.index('run_id')
        # Alles vor run_id sind Parameter
        return cols[:cut]

    def _create_fullscreen_table(self, runs_df: pd.DataFrame, checkbox_states: dict = None) -> html.Div:
        """Erstellt Fullscreen-Tabelle mit Checkboxen"""
        # Zusätzliche Performance-Metriken für Fullscreen
        perf_columns_order = [
            "Sharpe",
            "Total Return",
            "USDT_PnL% (total)",
            "Max Drawdown",
            "USDT_Win Rate",
            "USDT_Expectancy",
            "Returns Volatility (252 days)",
            "Average (Return)",
            "Average Win (Return)",
            "Average Loss (Return)",
            "Sortino Ratio (252 days)",
            "Profit Factor",
            "Risk Return Ratio",
            "Trades"
        ]
        param_cols = self._extract_param_columns(runs_df)  # NEU
        base_cols = ["run_index", "run_id"] + perf_columns_order + param_cols
        available_columns = [c for c in base_cols if c in runs_df.columns]
        table_data = runs_df[available_columns].copy()

        if 'run_id' in table_data.columns:
            table_data['run_id_display'] = table_data['run_id'].astype(str)

        table_data = self._format_table_data(table_data)

        rows = self._create_table_rows(
            table_data,
            checkbox_states,
            extra_perf_cols=[c for c in perf_columns_order if c in table_data.columns],
            param_cols=[c for c in param_cols if c in table_data.columns]
        )

        header_cells = self._create_fullscreen_header(
            table_data,
            extra_perf_cols=[c for c in perf_columns_order if c in table_data.columns],
            param_cols=[c for c in param_cols if c in table_data.columns]
        )

        return html.Div([
            html.Table([
                html.Thead([html.Tr(header_cells, style={
                    'background': 'linear-gradient(90deg,#f5f3ff 0%,#faf5ff 100%)',
                    'fontWeight': '600',
                    'fontSize': '12px',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'letterSpacing': '0.05em',
                    'textTransform': 'uppercase',
                    'color': '#2d3748'
                })]),
                html.Tbody(rows)
            ], style={
                'width': '100%',
                'borderRadius': '18px',
                'border': '1px solid rgba(196,181,253,0.9)',
                'background': 'linear-gradient(145deg,rgba(255,255,255,0.85),rgba(250,245,255,0.85))',
                'backdropFilter': 'blur(6px)',
                'borderCollapse': 'separate',
                'borderSpacing': '0',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontSize': '13px',
                'boxShadow': '0 4px 18px -6px rgba(124,58,237,0.15)',
                'overflow': 'hidden',              # NEU: clippt Inhalt
                'backgroundClip': 'padding-box'    # stabilere Kanten
            })
        ], id="run-table-fullscreen", style={'marginTop': '4px'})
    
    def _create_normal_table(self, runs_df: pd.DataFrame) -> dash_table.DataTable:
        """Erstellt normale DataTable"""
        # Dynamische Parameter auch in der normalen Tabelle ans Ende hängen
        param_cols = self._extract_param_columns(runs_df)
        display_core = ["run_index", "run_id", "Total Return", "Sharpe", "Max Drawdown"]
        display_columns = display_core + [c for c in param_cols if c not in display_core]
        display_columns = [c for c in display_columns if c in runs_df.columns]
        table_data = runs_df[display_columns].copy()
        table_data = self._format_table_data(table_data)

        # Spaltenbeschreibung dynamisch erzeugen
        col_defs = [
            {"name": "#", "id": "run_index", "type": "numeric"},
            {"name": "Run ID", "id": "run_id"},
            {"name": "Absolute Return", "id": "Total Return", "type": "numeric", "format": {"specifier": ".2f"}},
            {"name": "Sharpe", "id": "Sharpe", "type": "numeric", "format": {"specifier": ".3f"}},
            {"name": "Max DD", "id": "Max Drawdown", "type": "numeric", "format": {"specifier": ".2f"}}
        ]
        for p in [c for c in param_cols if c in table_data.columns]:
            if p not in ["run_index", "run_id", "Total Return", "Sharpe", "Max Drawdown"]:
                col_defs.append({"name": p, "id": p})

        return dash_table.DataTable(
            id="runs-table",
            data=table_data.to_dict('records'),
            columns=col_defs,
            style_table={
                'overflowX': 'hidden',
                'borderRadius': '16px',
                'border': '1px solid rgba(196,181,253,0.9)',
                'background': 'linear-gradient(145deg,#ffffff,#faf5ff)',
                'boxShadow': '0 4px 16px -4px rgba(124,58,237,0.18)'
            },
            style_cell={
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontSize': '12.5px',
                'padding': '9px 8px',
                'textAlign': 'center',
                'border': 'none',
                'backgroundColor': 'transparent',
                'cursor': 'pointer'
            },
            style_header={
                'background': 'linear-gradient(90deg,#f5f3ff 0%,#faf5ff 100%)',
                'color': '#2d3748',
                'fontWeight': '600',
                'fontSize': '11px',
                'border': 'none',
                'letterSpacing': '0.06em',
                'textTransform': 'uppercase',
                'padding': '12px 8px'
            },
            style_data={
                'border': 'none',
                'backgroundColor': 'rgba(255,255,255,0.55)',
                'transition': 'background-color .18s ease'
            },
            style_data_conditional=[
                {'if': {'row_index': 0}, 'backgroundColor': 'rgba(124,58,237,0.10)', 'color': '#1a1a1a', 'fontWeight': '600'},
                {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgba(245,243,255,0.65)'},
                {'if': {'state': 'selected'},
                 'backgroundColor': 'rgba(139,92,246,0.20)',
                 'border': '1px solid rgba(139,92,246,0.40)',
                 'fontWeight': '600',
                 'color': '#1a1a1a'},
                {'if': {'row_index': 'even'}, 'backgroundColor': 'rgba(255,255,255,0.55)'}
            ],
            style_cell_conditional=[
                {'if': {'column_id': 'run_id'}, 'display': 'none'}  # wirklich verstecken
            ],
            style_as_list_view=True,
            row_selectable="multi",          # geändert von 'single' -> Multi-Choice aktiv
            selected_rows=[0],               # initial weiterhin erster Run ausgewählt
            page_size=25
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
        # Zusätzliche Prozent-/Rate-Felder runden
        for pct_col in [
            "USDT_PnL% (total)", "USDT_Win Rate", "Returns Volatility (252 days)",
            "Average (Return)", "Average Win (Return)", "Average Loss (Return)"
        ]:
            if pct_col in table_data.columns:
                try:
                    table_data[pct_col] = pd.to_numeric(table_data[pct_col], errors='coerce')
                except Exception:
                    pass
        return table_data
    
    def _create_table_rows(self, table_data: pd.DataFrame, checkbox_states: dict = None,
                           extra_perf_cols: list = None, param_cols: list = None) -> list:
        """Erstellt Tabellen-Zeilen mit Checkboxen"""
        # Erweiterte Version für Fullscreen (checkbox_states nur relevant bei Fullscreen)
        extra_perf_cols = extra_perf_cols or []
        param_cols = param_cols or []
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
                        style={'margin': '0', 'transform': 'scale(1.1)'}
                    )
                ], style={'width': '40px', 'textAlign': 'center'}),
                html.Td(str(run_index), style={'textAlign': 'center', 'fontWeight': '600'}),
                html.Td(row.get('run_id_display', row.get('run_id', '')), style={'textAlign': 'center', 'fontSize': '11px'})
            ]

            def fmt_num(v, dec=2):
                try:
                    v = float(v)
                    return f"{v:.{dec}f}"
                except Exception:
                    return "N/A"

            for col in extra_perf_cols:
                val = row.get(col)
                style = {'textAlign': 'center', 'fontSize': '11px'}
                label = col
                if col in ["USDT_PnL% (total)", "USDT_Win Rate",
                           "Returns Volatility (252 days)", "Average (Return)",
                           "Average Win (Return)", "Average Loss (Return)"]:
                    # Prozent
                    try:
                        v = float(val)
                        if v <= 1 and v >= -1:
                            v *= 100  # falls als Ratio
                        val_out = f"{v:.2f}%"
                    except Exception:
                        val_out = "N/A"
                elif col == "Sharpe":
                    val_out = fmt_num(val, 3)
                    style['fontWeight'] = '500'
                elif col in ["Profit Factor", "Risk Return Ratio", "Sortino Ratio (252 days)"]:
                    val_out = fmt_num(val, 2)
                elif col in ["USDT_Expectancy", "Total Return"]:
                    val_out = fmt_num(val, 2)
                elif col == "Max Drawdown":
                    val_out = fmt_num(val, 2)
                else:
                    val_out = fmt_num(val, 2)
                cells.append(html.Td(val_out, style=style))

            # Dynamische Parameter
            for pcol in param_cols:
                if pcol in ['run_index', 'run_id']: 
                    continue
                val = row.get(pcol)
                try:
                    if pd.api.types.is_numeric_dtype(table_data[pcol]):
                        val_out = fmt_num(val, 4)
                    else:
                        val_out = str(val)
                except Exception:
                    val_out = str(val)
                cells.append(html.Td(val_out, style={'textAlign': 'center', 'fontSize': '11px'}))

            # Entferne YAML-Button aus der Tabelle

            # Row styling - hervorheben wenn ausgewählt
            is_selected = checkbox_states and run_index in checkbox_states and checkbox_states[run_index]
            row_style = {
                'backgroundColor': (
                    'linear-gradient(90deg,rgba(139,92,246,0.18),rgba(139,92,246,0.10))' if is_selected else
                    'rgba(124,58,237,0.10)' if idx == 0 else
                    'rgba(255,255,255,0.55)'
                ),
                'borderBottom': '1px solid rgba(221,214,254,0.8)',
                'transition': 'background .22s ease',
            }
            
            rows.append(html.Tr(cells, style=row_style))
        
        return rows
    
    def _create_fullscreen_header(self, table_data: pd.DataFrame, extra_perf_cols: list = None,
                                  param_cols: list = None) -> list:
        """Erstellt Header für Fullscreen-Tabelle"""
        extra_perf_cols = extra_perf_cols or []
        param_cols = param_cols or []
        header_cells = [
            html.Th('✓', style={'width': '40px', 'textAlign': 'center'}),
            html.Th('#', style={'textAlign': 'center'}),
            html.Th('Run ID', style={'textAlign': 'center'})
        ]

        col_name_map = {
            "Total Return": "Absolute Return",
            "USDT_PnL% (total)": "PnL %",
            "USDT_Win Rate": "Win Rate",
            "USDT_Expectancy": "Expectancy",
            "Returns Volatility (252 days)": "Volatility",
            "Average (Return)": "Avg Ret",
            "Average Win (Return)": "Avg Win",
            "Average Loss (Return)": "Avg Loss",
            "Sortino Ratio (252 days)": "Sortino",
            "Risk Return Ratio": "RR Ratio",
            "Max Drawdown": "Max DD",
            "Trades": "Trades"
        }

        for col in extra_perf_cols:
            header_cells.append(html.Th(col_name_map.get(col, col), style={'textAlign': 'center'}))

        # Parameter-Header am Ende
        for pcol in param_cols:
            if pcol in ['run_index', 'run_id']:
                continue
            header_cells.append(html.Th(pcol, style={'textAlign': 'center'}))

        # Entferne YAML-Button Header

        return header_cells
