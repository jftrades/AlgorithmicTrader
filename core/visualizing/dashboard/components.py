# core/visualizing/dashboard/components.py
from dash import html, dcc, dash_table
import pandas as pd
import re

# --------- Trade-Details: Defaults ---------
def get_default_trade_details():
    return html.Div([
        html.Div("Trade Details", style={
            'fontSize': '15px', 'fontWeight': '600', 'marginBottom': '6px',
            'fontFamily': 'Inter, system-ui, sans-serif', 'color': '#2c3e50'
        }),
        html.Div("No trade selected", style={
            'fontSize': '12px', 'color': '#6c757d', 'fontStyle': 'italic'
        })
    ])

def get_default_trade_details_with_message(msg="Click a trade marker to view details"):
    return html.Div([
        html.Div("Trade Details", style={
            'fontSize': '15px', 'fontWeight': '600', 'marginBottom': '6px',
            'fontFamily': 'Inter, system-ui, sans-serif', 'color': '#2c3e50'
        }),
        html.Div(msg, style={
            'fontSize': '12px', 'color': '#6c757d', 'fontStyle': 'italic'
        })
    ])

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
def render_metrics_cards(flat_metrics: dict):
    """
    Render metrics in a responsive card grid (improved design).
    flat_metrics: simple key->value dict (already flattened / selected).
    """
    if not flat_metrics:
        return html.Div("No metrics available", style={
            'textAlign': 'center',
            'color': '#6c757d',
            'fontFamily': 'Inter, system-ui, sans-serif',
            'padding': '20px'
        })

    def classify(k):
        lk = k.lower()
        if any(w in lk for w in ['pnl', 'profit', 'commission', 'ø win', 'avg win', 'avg loss', 'max win', 'max loss']):
            return 'currency'
        if any(w in lk for w in ['trade', 'trades', 'positions', 'count', 'iterations', 'consecutive']):
            return 'count'
        if 'winrate' in lk or 'win rate' in lk:
            return 'percent'
        return 'generic'

    def fmt(k, v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/A"
        cls = classify(k)
        try:
            if cls == 'currency':
                return f"{float(v):.4f}"
            if cls == 'count':
                iv = int(float(v))
                return f"{iv}"
            if cls == 'percent':
                f = float(v)
                return f"{(f*100 if f <= 1 else f):.2f}%"
            f = float(v)
            if abs(f - int(f)) < 1e-9:
                return str(int(f))
            return f"{f:.4f}"
        except Exception:
            return str(v)

    cards = []
    for k, v in flat_metrics.items():
        cls = classify(k)
        accent = {
            'currency': '#6366f1',
            'count': '#0ea5e9',
            'percent': '#10b981',
            'generic': '#475569'
        }.get(cls, '#475569')
        cards.append(
            html.Div([
                html.Div(k, style={
                    'fontSize': '11px',
                    'letterSpacing': '.5px',
                    'textTransform': 'uppercase',
                    'color': '#64748b',
                    'fontWeight': '600',
                    'marginBottom': '6px'
                }),
                html.Div(fmt(k, v), style={
                    'fontSize': '20px',
                    'fontWeight': '600',
                    'color': accent,
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'textShadow': '0 1px 0 rgba(0,0,0,0.04)'
                })
            ], style={
                'background': 'linear-gradient(135deg,#ffffff 0%,#f8fafc 100%)',
                'border': '1px solid #e2e8f0',
                'borderRadius': '14px',
                'padding': '14px 16px 16px 16px',
                'minWidth': '140px',
                'flex': '1 1 160px',
                'boxShadow': '0 4px 14px -4px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04)',
                'transition': 'transform .18s ease, box-shadow .18s ease',
                'display': 'flex',
                'flexDirection': 'column'
            })
        )
    return html.Div(cards, style={
        'display': 'flex',
        'flexWrap': 'wrap',
        'gap': '14px',
        'alignItems': 'stretch',
        'justifyContent': 'flex-start',
        'marginTop': '4px'
    })

def create_metrics_table(metrics: dict, nautilus_result, layout_mode: str = "cards"):
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

    # UPDATED: include underscore variants
    CURRENCY_KEYWORDS = [
        'pnl','profit','commission','avg win','avg loss','max win','max loss','expectancy',
        'avg_win','avg_loss','max_win','max_loss'
    ]
    COUNT_KEYWORDS = ['trade','trades','positions','count','iterations','consecutive','n_','n ']

    def _inline_classify(k: str):
        kl = k.lower()
        kl_sp = kl.replace('_', ' ')
        if any(w in kl_sp for w in CURRENCY_KEYWORDS) and 'pnl%' not in kl and '% pnl' not in kl:
            return 'currency'
        if 'winrate' in kl or 'win rate' in kl:
            return 'percent'
        if any(w in kl for w in COUNT_KEYWORDS):
            return 'count'
        return 'generic'

    def _is_pnl_key(k: str):
        kl = k.lower()
        return (
            ('pnl' in kl and 'pnl%' not in kl) or
            kl.endswith('_pnl') or
            'final_realized_pnl' in kl or
            'realized_pnl' in kl
        )

    def _inline_fmt(k, v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/A"
        t = _inline_classify(k)
        try:
            if t == 'count':
                return str(int(float(v)))
            if t == 'percent':
                f = float(v)
                return f"{(f*100 if f <= 1 else f):.2f}%"
            # currency & generic -> two decimals
            f = float(v)
            return f"{f:.2f}"
        except Exception:
            return str(v)

    def _value_color(k, v):
        if _is_pnl_key(k):
            try:
                return '#10b981' if float(v) >= 0 else '#ef4444'
            except Exception:
                return '#111827'
        cls = _inline_classify(k)
        if cls == 'currency':
            return '#111827'  # black for non-PnL currency metrics
        return {
            'count': '#0ea5e9',
            'percent': '#0f766e',
            'generic': '#475569'
        }.get(cls, '#475569')

    def _unit_for(k):
        cls = _inline_classify(k)
        if cls == 'currency':
            return 'USD(T)'
        if cls == 'percent':
            return ''  # never add second % unit
        return ''

    def _inline_chip(label, raw_value):
        fmt = _inline_fmt(label, raw_value)
        unit = _unit_for(label)
        # guard: don't show unit if value already ends with % or N/A
        if fmt.endswith('%'):
            unit = ''
        color = _value_color(label, raw_value)
        return html.Div([
            html.Span(label, style={
                'fontSize': '10px','letterSpacing':'.45px','textTransform':'uppercase',
                'color':'#64748b','fontWeight':'600','display':'block','marginBottom':'2px'
            }),
            html.Span(fmt, style={
                'fontSize': '15px','fontWeight':'700','color': color,
                'fontFamily':'Inter, system-ui, sans-serif','lineHeight':'1.1'
            }),
            (html.Span(unit, style={
                'fontSize':'10px','fontWeight':'600','color':'#475569','marginTop':'2px',
                'letterSpacing':'.5px'
            }) if unit else None)
        ], style={
            'flex':'0 0 auto',
            'padding':'10px 14px 9px 14px',
            'background':'linear-gradient(145deg,#ffffff 0%,#f6f9fb 100%)',
            'border':'1px solid #e2e8f0',
            'borderRadius':'14px',
            'boxShadow':'0 2px 6px -2px rgba(0,0,0,0.07)',
            'display':'flex',
            'flexDirection':'column',
            'alignItems':'flex-start',
            'minWidth':'118px'
        })

    # --- Nested inline (multi-run) vertical layout ---
    if layout_mode == "inline" and isinstance(metrics, dict) and any(isinstance(v, dict) for v in metrics.values()):
        nested = {}
        for run_key, maybe in metrics.items():
            if isinstance(maybe, dict):
                for inst_key, md in maybe.items():
                    if isinstance(md, dict):
                        nested.setdefault(str(run_key), {})[str(inst_key)] = md
        segments = []
        for run_id, inst_map in nested.items():
            for inst_id, mdict in inst_map.items():
                chips = [_inline_chip(k, v) for k, v in mdict.items()]
                segments.append(
                    html.Div([
                        html.Div([
                            html.Span(run_id, style={
                                'padding':'4px 10px','background':'#1e3a8a','color':'#fff',
                                'fontSize':'11px','fontWeight':'600','borderRadius':'10px',
                                'letterSpacing':'.5px','marginRight':'6px'
                            }),
                            html.Span(inst_id, style={
                                'padding':'4px 10px','background':'#0f766e','color':'#fff',
                                'fontSize':'11px','fontWeight':'600','borderRadius':'10px',
                                'letterSpacing':'.5px'
                            })
                        ], style={'display':'flex','alignItems':'center','marginBottom':'10px','gap':'4px'}),
                        html.Div(chips, style={
                            'display':'flex','flexWrap':'wrap','gap':'10px'
                        })
                    ], style={
                        'background':'linear-gradient(135deg,#ffffff,#f1f5f9)',
                        'border':'1px solid #e2e8f0',
                        'borderRadius':'18px',
                        'padding':'16px 18px 14px 18px',
                        'boxShadow':'0 4px 16px -4px rgba(0,0,0,0.10),0 2px 6px rgba(0,0,0,0.04)',
                        'flex':'0 0 auto',
                        'width':'100%',
                        'boxSizing':'border-box'
                    })
                )
        if segments:
            return html.Div([
                html.Div("Metrics (Runs × Instruments)", style={
                    'fontSize':'15px','fontWeight':'700','color':'#0f172a',
                    'margin':'0 0 14px 0','letterSpacing':'-0.4px'
                }),
                html.Div(segments, style={
                    'display':'flex','flexDirection':'column','gap':'18px','width':'100%'
                })
            ], style={
                'background':'linear-gradient(125deg,#ffffff,#eef2f7)',
                'border':'1px solid #dfe6ee',
                'borderRadius':'22px',
                'padding':'20px 22px 22px 22px',
                'boxShadow':'0 6px 22px -6px rgba(0,0,0,0.12),0 3px 8px rgba(0,0,0,0.05)',
                'width':'100%','boxSizing':'border-box','margin':'0'
            })

    # --- Flat inline single-run (no outer frame to avoid double border) ---
    if layout_mode == "inline" and isinstance(metrics, dict) and not any(isinstance(v, dict) for v in metrics.values()):
        perf, trade, other = {}, {}, {}
        for k, v in metrics.items():
            kl = k.lower()
            if any(w in kl for w in ['return','pnl','profit','drawdown','sharpe','sortino']):
                perf[k] = v
            elif any(w in kl for w in ['trade','win','loss','position','consecutive']):
                trade[k] = v
            else:
                other[k] = v
        ordered = {**perf, **trade, **other}
        chips = [_inline_chip(k, v) for k, v in ordered.items()]
        return html.Div([
            html.Div("Metrics", style={
                'fontSize':'15px','fontWeight':'700','color':'#0f172a',
                'margin':'0 0 10px 0','letterSpacing':'-0.4px'
            }),
            html.Div(chips, style={
                'display':'flex','flexWrap':'wrap','gap':'10px','width':'100%','boxSizing':'border-box'
            })
        ], style={
            'width':'100%','boxSizing':'border-box','margin':'0'
        })

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

    if layout_mode == "cards" and isinstance(metrics, dict) and not any(isinstance(v, dict) for v in metrics.values()):
        # flatten all three groups preserving insertion order
        flat = {}
        flat.update(performance_metrics)
        flat.update(trade_metrics)
        flat.update(general_info)
        return html.Div([
            html.Div("Metrics", style={
                'fontSize': '15px',
                'fontWeight': '700',
                'color': '#1e293b',
                'marginBottom': '10px',
                'letterSpacing': '-0.5px'
            }),
            render_metrics_cards(flat)
        ])

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
