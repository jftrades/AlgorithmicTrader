# core/visualizing/dashboard/components.py
from dash import html, dcc, dash_table
import pandas as pd
import re


# --------- Trade-Details: Defaults ---------
def get_default_trade_details():
    """Standard Trade-Details Anzeige."""
    return [
        html.Div([
            html.H4("Trade Details", style={
                'color': '#34495e',
                'marginBottom': '10px',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontWeight': '500',
                'textAlign': 'center',
                'fontSize': '16px'
            }),
            html.P("Click on a trade marker in the chart below to see details", style={
                'color': '#6c757d',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'textAlign': 'center',
                'fontSize': '14px',
                'margin': '0'
            })
        ])
    ]


def get_default_trade_details_with_message():
    """Trade-Details mit Hinweis-Message (wenn nicht auf Marker geklickt wurde)."""
    return [
        html.Div([
            html.H4("Trade Details", style={
                'color': '#34495e',
                'marginBottom': '10px',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontWeight': '500',
                'textAlign': 'center',
                'fontSize': '16px'
            }),
            html.P("Please click directly on a trade marker (triangle) to see details", style={
                'color': '#dc3545',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'textAlign': 'center',
                'fontSize': '14px'
            })
        ])
    ]


# --------- Trade-Details: Inhalt aus einer Trade-Zeile ---------
def create_trade_details_content(trade_data: pd.Series):
    """Erstellt den Inhalt für das Trade-Details Panel (kompakt für oberhalb des Charts)."""

    def format_value(key, value):
        """Formatiert Werte basierend auf dem Feldtyp."""
        if pd.isna(value) or value is None:
            return "N/A"

        key_lower = str(key).lower()

        # Timestamp-Felder
        if 'timestamp' in key_lower:
            try:
                if isinstance(value, (int, float)) and value > 1e15:
                    return pd.to_datetime(value, unit='ns').strftime('%Y-%m-%d %H:%M:%S')
                else:
                    return pd.to_datetime(value).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return str(value)

        # Preis-Felder
        elif any(term in key_lower for term in ['price', 'sl', 'tp']):
            try:
                return f"{float(value):.4f}"
            except Exception:
                return str(value)

        # P&L-Felder (mit +/- Vorzeichen)
        elif 'pnl' in key_lower or 'p&l' in key_lower:
            try:
                pnl_value = float(value)
                sign = "+" if pnl_value >= 0 else ""
                return f"{sign}{pnl_value:.4f}"
            except Exception:
                return str(value)

        # Gebühren-Felder
        elif 'fee' in key_lower:
            try:
                return f"{float(value):.6f}"
            except Exception:
                return str(value)

        # Größe/Menge
        elif 'size' in key_lower or 'quantity' in key_lower:
            try:
                return f"{float(value):.6f}"
            except Exception:
                return str(value)

        # Enum/Booleans
        elif key_lower in ['type', 'action']:
            return str(value).upper()

        # Default
        else:
            return str(value)

    # Action-Farbe
    action = str(trade_data.get('action', '')).upper()
    action_color = '#28a745' if action == 'BUY' else '#dc3545'

    # Wichtigste Felder
    key_fields = [
        'timestamp', 'action', 'open_price_actual', 'close_price_actual',
        'closed_timestamp', 'tradesize', 'sl', 'tp', 'realized_pnl', 'fee'
    ]

    main_info = []
    for field in key_fields:
        if field in trade_data.index and not pd.isna(trade_data[field]):
            label = {
                'timestamp': 'Entry Time',
                'action': 'Action',
                'open_price_actual': 'Open Price',
                'close_price_actual': 'Close Price',
                'closed_timestamp': 'Exit Time',
                'tradesize': 'Size',
                'sl': 'SL',
                'tp': 'TP',
                'realized_pnl': 'P&L',
                'fee': 'Fee'
            }.get(field, field)

            value = format_value(field, trade_data[field])
            main_info.append(f"{label}: {value}")

    # Kompakte horizontale Anzeige
    return [
        html.Div([
            # Header mit Action
            html.Div([
                html.Span(f"{action} SIGNAL", style={
                    'backgroundColor': action_color,
                    'color': 'white',
                    'padding': '4px 12px',
                    'borderRadius': '15px',
                    'fontSize': '12px',
                    'fontWeight': '600',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'marginRight': '15px'
                }),
                html.Span(f"ID: {trade_data.get('id', 'N/A')}", style={
                    'color': '#6c757d',
                    'fontSize': '12px',
                    'fontFamily': 'Inter, system-ui, sans-serif'
                })
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'marginBottom': '10px'
            }),

            # Hauptinformationen in Grid
            html.Div([
                html.Div(info, style={
                    'backgroundColor': 'white',
                    'padding': '8px 12px',
                    'borderRadius': '6px',
                    'border': '1px solid #e9ecef',
                    'fontSize': '13px',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'color': '#28a745' if 'P&L: +' in info else '#dc3545' if 'P&L: -' in info else '#495057',
                    'textAlign': 'center',
                    'margin': '3px'
                }) for info in main_info
            ], style={
                'display': 'flex',
                'flexWrap': 'wrap',
                'gap': '5px'
            })
        ])
    ]


# --------- Metrics (nimmt Dict und optionales Nautilus-Result) ---------
def create_metrics_table(metrics: dict, nautilus_result):
    """Erstellt professionelle Metriken-Tabelle mit Einheiten.
    metrics: Dict[str, Any] – bereits extrahiert (z. B. deine self.metrics)
    nautilus_result: Optional[List[Any]] – z. B. dein self.nautilus_result (für Units)
    """
    if not metrics:
        return html.Div("No metrics available", style={
            'textAlign': 'center',
            'color': '#6c757d',
            'fontFamily': 'Inter, system-ui, sans-serif',
            'padding': '20px'
        })

    # Einheiten aus result extrahieren, falls vorhanden
    units = {}
    if nautilus_result and len(nautilus_result) > 0:
        result_obj = nautilus_result[0]

        # PnL-Metriken in USDT
        if hasattr(result_obj, 'stats_pnls') and 'USDT' in getattr(result_obj, 'stats_pnls', {}):
            try:
                for key in result_obj.stats_pnls['USDT'].keys():
                    metric_name = key.replace('_', ' ').title()
                    if 'pnl' in key.lower() and 'pnl%' not in key.lower():
                        units[metric_name] = 'USDT'
                    elif 'pnl%' in key.lower():
                        units[metric_name] = '%'
            except Exception:
                pass

        # Return-Statistiken/Ratios in Prozent (meist)
        if hasattr(result_obj, 'stats_returns'):
            try:
                for key in result_obj.stats_returns.keys():
                    metric_name = key.replace('_', ' ').title()
                    if any(term in key.lower() for term in ['volatility', 'average', 'sharpe', 'sortino']):
                        units[metric_name] = '%'
            except Exception:
                pass

        # Spezielle Behandlung
        special_units = {
            'Win Rate': '',
            'Profit Factor': '',
            'Risk Return Ratio': '',
            'Total Positions': '',
            'Total Orders': '',
            'Total Events': '',
            'Iterations': '',
            'Elapsed Time (s)': 'time',
            'Max Winner': 'USDT',
            'Avg Winner': 'USDT',
            'Min Winner': 'USDT',
            'Max Loser': 'USDT',
            'Avg Loser': 'USDT',
            'Min Loser': 'USDT',
            'Expectancy': 'USDT',
        }
        units.update(special_units)

    # Wenn metrics ein Mapping von instrument->metrics_dict ist -> Vergleichstabelle
    # Neu: unterstützt jetzt auch verschachtelte Maps: run_id -> { instrument -> metrics_dict }
    if isinstance(metrics, dict) and any(isinstance(v, dict) for v in metrics.values()):
        # Detect nested mapping: run_id -> {inst -> metrics_dict}
        first_vals = list(metrics.values())
        nested = any(isinstance(v, dict) and any(isinstance(x, dict) for x in v.values()) for v in first_vals)
        if nested:
            # metrics: { run_id: {inst: metrics_dict, ...}, ...}
            runs = list(metrics.keys())
            # collect instrument order (unique across runs)
            instruments = []
            for r in runs:
                for inst in (metrics.get(r) or {}).keys():
                    if inst not in instruments:
                        instruments.append(inst)
            # collect all metric keys across all run/inst combos
            all_keys = set()
            for r in runs:
                for inst, m in (metrics.get(r) or {}).items():
                    if isinstance(m, dict):
                        all_keys.update(m.keys())
            ordered_keys = sorted(all_keys, key=lambda s: str(s).lower())

            def _format_value(k, v):
                norm = re.sub(r'[^a-z0-9 ]', ' ', str(k).lower()).strip()
                is_currency = (
                    'pnl' in norm
                    or ('avg' in norm and ('win' in norm or 'loss' in norm))
                    or ('max' in norm and ('win' in norm or 'loss' in norm))
                    or 'commission' in norm or 'commissions' in norm or ('ø' in str(k).lower())
                )
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return "N/A"
                try:
                    if is_currency:
                        return f"{float(v):.4f}"
                    if any(w in norm for w in ['trade', 'trades', 'n_trades', 'long trades', 'short trades', 'total', 'count', 'iterations', 'positions', 'max consecutive']):
                        return str(int(float(v)))
                    if 'win rate' in norm or 'winrate' in norm or 'win_rate' in norm:
                        vv = float(v)
                        return f"{(vv*100 if vv <= 1 else vv):.1f}%"
                    f = float(v)
                    if abs(f - int(f)) < 1e-9:
                        return f"{int(f)}"
                    return f"{f:.4f}"
                except Exception:
                    return str(v)

            # Build dual-header table: first row = Metric label + run headers (colspan = number of instruments present in that run)
            # second header row = per-run instrument headers
            # construct header rows
            top_header_cells = [html.Th("Metric", style={'textAlign': 'left', 'padding':'8px 12px'})]
            second_header_cells = [html.Th("", style={'padding':'8px 12px'})]
            for r in runs:
                insts_in_run = list((metrics.get(r) or {}).keys())
                colspan = max(1, len(insts_in_run))
                top_header_cells.append(html.Th(str(r), colSpan=colspan, style={'textAlign':'center', 'padding':'8px 12px', 'fontWeight':'700'}))
                # instrument header cells for this run
                if insts_in_run:
                    for inst in insts_in_run:
                        second_header_cells.append(html.Th(str(inst), style={'textAlign':'center', 'padding':'8px 12px'}))
                else:
                    # filler cell if no instruments
                    second_header_cells.append(html.Th("", style={'padding':'8px 12px'}))

            # Build rows
            rows = []
            for key in ordered_keys:
                cells = [html.Td(str(key), style={'padding':'8px 12px', 'fontWeight':'500', 'color':'#2c3e50'})]
                for r in runs:
                    insts_in_run = list((metrics.get(r) or {}).keys())
                    if insts_in_run:
                        for inst in insts_in_run:
                            m = (metrics.get(r) or {}).get(inst) or {}
                            val = m.get(key, m.get(key.lower(), "N/A"))
                            cells.append(html.Td(_format_value(key, val), style={'padding':'8px 12px', 'textAlign':'center'}))
                    else:
                        cells.append(html.Td("N/A", style={'padding':'8px 12px', 'textAlign':'center'}))
                rows.append(html.Tr(cells))

            table = html.Table([
                html.Thead([html.Tr(top_header_cells), html.Tr(second_header_cells)]),
                html.Tbody(rows)
            ], style={
                'width': '100%',
                'backgroundColor': 'white',
                'border': '1px solid #dee2e6',
                'borderRadius': '8px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.06)',
            })
            return html.Div([
                html.H4("Metrics Comparison (Runs × Instruments)", style={'color': '#2c3e50', 'marginBottom': '12px', 'fontFamily': 'Inter, system-ui, sans-serif', 'fontWeight': '600'}),
                table
            ], style={'padding': '8px'})
        # fallback: old single-level instrument->metrics rendering continues below
        instruments = list(metrics.keys())
        all_keys = set()
        for m in metrics.values():
            if isinstance(m, dict):
                all_keys.update(m.keys())
        ordered_keys = sorted(all_keys, key=lambda s: str(s).lower())
        def _format_value(k, v):
            norm = re.sub(r'[^a-z0-9 ]', ' ', str(k).lower()).strip()
            is_currency = (
                'pnl' in norm
                or ('avg' in norm and ('win' in norm or 'loss' in norm))
                or ('max' in norm and ('win' in norm or 'loss' in norm))
                or 'commission' in norm or 'commissions' in norm or ('ø' in str(k).lower())
            )
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "N/A"
            try:
                if is_currency:
                    return f"{float(v):.4f}"
                if any(w in norm for w in ['trade', 'trades', 'n_trades', 'long trades', 'short trades', 'total', 'count', 'iterations', 'positions', 'max consecutive']):
                    return str(int(float(v)))
                if 'win rate' in norm or 'winrate' in norm or 'win_rate' in norm:
                    vv = float(v)
                    return f"{(vv*100 if vv <= 1 else vv):.1f}%"
                f = float(v)
                if abs(f - int(f)) < 1e-9:
                    return f"{int(f)}"
                return f"{f:.4f}"
            except Exception:
                return str(v)

        header = [html.Th("Metric", style={'textAlign': 'left', 'padding':'8px 12px'})] + [
            html.Th(str(inst), style={'textAlign': 'center', 'padding':'8px 12px'}) for inst in instruments
        ]
        rows = []
        for key in ordered_keys:
            cells = [html.Td(str(key), style={'padding':'8px 12px', 'fontWeight':'500', 'color':'#2c3e50'})]
            for inst in instruments:
                mv = metrics.get(inst) or {}
                val = mv.get(key, mv.get(key.lower(), "N/A"))
                cells.append(html.Td(_format_value(key, val), style={'padding':'8px 12px', 'textAlign':'center'}))
            rows.append(html.Tr(cells))

        table = html.Table([
            html.Thead(html.Tr(header)),
            html.Tbody(rows)
        ], style={
            'width': '100%',
            'backgroundColor': 'white',
            'border': '1px solid #dee2e6',
            'borderRadius': '8px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.06)',
        })
        return html.Div([
            html.H4("Metrics Comparison", style={'color': '#2c3e50', 'marginBottom': '12px', 'fontFamily': 'Inter, system-ui, sans-serif', 'fontWeight': '600'}),
            table
        ], style={'padding': '8px'})

    performance_metrics = {}
    trade_metrics = {}
    general_info = {}

    for key, value in metrics.items():
        key_lower = key.lower()
        if any(word in key_lower for word in ['return', 'pnl', 'profit', 'drawdown', 'sharpe', 'sortino']):
            performance_metrics[key] = value
        elif any(word in key_lower for word in ['trade', 'win', 'loss', 'position']):
            trade_metrics[key] = value
        else:
            general_info[key] = value

    def create_metric_row(key, value):
        einheit = units.get(key, '')
        formatted_value = value
        # Normalize key: lowercase, replace underscores and non-alnum with space
        norm = re.sub(r'[^a-z0-9 ]', ' ', str(key).lower()).strip()
        # decide whether this key is currency (we will append unit to label instead of value)
        is_currency = (
            'pnl' in norm
            or ('final' in norm and 'real' in norm)
            or ('avg' in norm and 'win' in norm)
            or ('avg' in norm and 'loss' in norm)
            or ('max' in norm and 'win' in norm)
            or ('max' in norm and 'loss' in norm)
            or 'commission' in norm
            or 'commissions' in norm
            or ('ø' in str(key).lower())
        )

        # 1) Currency-like detection (PnL, Avg/Ø Win/Loss, Max Win/Loss, Commissions)
        if is_currency:
            try:
                formatted_value = f"{float(value):.4f}"
            except Exception:
                formatted_value = f"{value}" if value is not None else "N/A"

        # 2) Integer counters (Trades, Long Trades, Short Trades, Total, Counts, Max Consecutive ...)
        elif any(w in norm for w in ['trade', 'trades', 'n trades', 'n_trades', 'long trades', 'short trades', 'total', 'count', 'counts', 'iterations', 'positions', 'max consecutive']):
            try:
                formatted_value = f"{int(float(value))}"
            except Exception:
                # if cannot convert, fall back to string without trailing .0
                s = str(value)
                if s.endswith('.0'):
                    formatted_value = s[:-2]
                else:
                    formatted_value = s

        # 3) Win rate / percent
        elif 'win rate' in norm or 'winrate' in norm or 'win_rate' in norm:
            try:
                v = float(value)
                formatted_value = f"{(v*100 if v <= 1 else v):.1f}%"
            except Exception:
                formatted_value = str(value)

        # 4) Time formatting
        elif key == 'Elapsed Time (s)':
            try:
                seconds = float(value)
                if seconds < 60:
                    formatted_value = f"{seconds:.1f}s"
                elif seconds < 3600:
                    formatted_value = f"{seconds/60:.1f}m"
                elif seconds < 86400:
                    formatted_value = f"{seconds/3600:.1f}h"
                else:
                    days = int(seconds // 86400)
                    hours = int((seconds % 86400) // 3600)
                    formatted_value = f"{days}d {hours}h" if hours else f"{days}d"
            except Exception:
                formatted_value = str(value)

        # 5) Ratios / percent heuristics
        elif ('ratio' in norm or 'volatility' in norm or 'average' in norm or 'sharpe' in norm or 'sortino' in norm) and einheit == '%':
            try:
                v = float(value)
                formatted_value = f"{(v*100 if v < 1 else v):.2f}%"
            except Exception:
                formatted_value = f"{value}%"

        # 6) Fallback numeric formatting
        else:
            try:
                f = float(value)
                if abs(f - int(f)) < 1e-9:
                    formatted_value = f"{int(f)}"
                else:
                    formatted_value = f"{f:.4f}"
            except Exception:
                formatted_value = str(value)

        # Display key with unit annotation if currency
        display_key = f"{key} (USD/T)" if is_currency else key
        return html.Tr([
            html.Td(display_key, style={
                'padding': '12px 16px',
                'fontWeight': '500',
                'color': '#2c3e50',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'borderBottom': '1px solid #e9ecef'
            }),
            html.Td(str(formatted_value), style={
                'padding': '12px 16px',
                'color': '#495057',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'borderBottom': '1px solid #e9ecef'
            })
        ])

    def create_section(title, metrics_dict):
        if not metrics_dict:
            return html.Div()
        return html.Div([
            html.H4(title, style={
                'color': '#2c3e50',
                'marginBottom': '15px',
                'marginTop': '20px',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontWeight': '600',
                'fontSize': '18px',
                'borderBottom': '2px solid #3498db',
                'paddingBottom': '8px'
            }),
            html.Table([
                html.Tbody([create_metric_row(k, v) for k, v in metrics_dict.items()])
            ], style={
                'width': '100%',
                'backgroundColor': 'white',
                'border': '1px solid #dee2e6',
                'borderRadius': '8px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
            })
        ])

    return html.Div([
        create_section("Performance", performance_metrics),
        create_section("Trading", trade_metrics),
        create_section("General", general_info)
    ])


# --------- All Backtest Results (bekommt DataFrame) ---------
def create_all_results_table(all_results_df: pd.DataFrame | None, filter_active: bool = False):
    """Erstellt eine cleane, sortierbare Tabelle für alle Runs.
       all_results_df wird von außen (Repository) übergeben.
    """
    if all_results_df is None or all_results_df.empty:
        return html.Div("No backtest results found.", style={'textAlign': 'center', 'color': '#6c757d'})

    # Spalte für Sharpe finden
    sharpe_col = None
    for col in all_results_df.columns:
        if "sharpe" in str(col).lower():
            sharpe_col = col
            break

    # erste numerische Spalte für Default-Sortierung
    sort_by = None
    for col in all_results_df.columns:
        if pd.api.types.is_numeric_dtype(all_results_df[col]):
            sort_by = col
            break

    # arbeite auf einer Kopie
    df = all_results_df.copy()
    # (reverted) Do NOT inject a synthetic 'run_id' column here — keep columns as provided by caller.

    if filter_active and sharpe_col:
        try:
            df[sharpe_col] = pd.to_numeric(df[sharpe_col], errors='coerce')
            df[sharpe_col] = df[sharpe_col].fillna(-1e9)
            df = df.sort_values(by=sharpe_col, ascending=False)
        except Exception as e:
            # suppressed debug print
            pass
    elif sort_by:
        df = df.sort_values(by=sort_by, ascending=False)

    # Columns come from the original DataFrame's columns (no automatic run_id injection)
    columns = [{"name": i, "id": i, "deletable": False, "selectable": False, "hideable": False}
               for i in all_results_df.columns]

    # Filter-Button Styles
    if filter_active:
        filter_label = "Filtered by Sharpe Ratio"
        filter_bg = "#27ae60"
        filter_color = "white"
    else:
        filter_label = "Filter by Sharpe Ratio"
        filter_bg = "#f8f9fa"
        filter_color = "#222"

    filter_button = html.Button(
        f"🔍 {filter_label}",
        id="custom-filter-btn",
        n_clicks=0,
        style={
            'float': 'right',
            'marginBottom': '18px',
            'background': filter_bg,
            'color': filter_color,
            'border': '1.5px solid #e5e7eb',
            'borderRadius': '12px',
            'padding': '8px 22px',
            'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
            'fontWeight': '600',
            'fontSize': '16px',
            'cursor': 'pointer',
            'boxShadow': 'none',
            'transition': 'background 0.2s, color 0.2s'
        }
    )

    return html.Div([
        html.Div([filter_button], style={'width': '100%', 'display': 'flex', 'justifyContent': 'flex-end'}),
        dash_table.DataTable(
            data=df.to_dict('records'),
            columns=columns,
            style_table={
                'overflowX': 'auto',
                'borderRadius': '16px',
                'background': '#fff',
                'margin': '0 0 30px 0',
                'border': '1px solid #e5e7eb',
            },
            style_cell={
                'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
                'fontSize': '16px',
                'padding': '12px 8px',
                'textAlign': 'center',
                'border': 'none',
                'background': '#fff',
            },
            style_header={
                'background': '#f8f9fa',
                'color': '#222',
                'fontWeight': '700',
                'fontSize': '17px',
                'borderTopLeftRadius': '16px',
                'borderTopRightRadius': '16px',
                'border': 'none',
                'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
                'letterSpacing': '-0.01em'
            },
            style_data={
                'border': 'none',
            },
            style_data_conditional=[
                {'if': {'row_index': 'odd'}, 'backgroundColor': '#f6f8fa'},
                {'if': {'state': 'selected'}, 'backgroundColor': '#e5e7eb', 'border': 'none'},
            ],
            style_as_list_view=True,
            filter_action='none',
            sort_action='none',
            page_size=10,
            css=[{
                'selector': '.dash-spreadsheet-container .dash-spreadsheet-inner tr:first-child th:first-child',
                'rule': 'border-top-left-radius: 16px;'
            }, {
                'selector': '.dash-spreadsheet-container .dash-spreadsheet-inner tr:first-child th:last-child',
                'rule': 'border-top-right-radius: 16px;'
            }, {
                'selector': '.dash-spreadsheet-container .dash-spreadsheet-inner tr:last-child td:first-child',
                'rule': 'border-bottom-left-radius: 16px;'
            }, {
                'selector': '.dash-spreadsheet-container .dash-spreadsheet-inner tr:last-child td:last-child',
                'rule': 'border-bottom-right-radius: 16px;'
            }]
        )
    ], style={'marginTop': '18px'})
