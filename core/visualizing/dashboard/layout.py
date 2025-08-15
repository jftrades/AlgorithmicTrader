# core/visualizing/dashboard/layout.py
from dash import html, dcc
from core.visualizing.dashboard.slide_menu import SlideMenuComponent
import pandas as pd
import os

def build_metrics_panel(metrics_path):
    if not os.path.exists(metrics_path):
        return html.Div("No metrics available.", style={'color': '#888', 'fontStyle': 'italic', 'marginTop': '20px'})
    df = pd.read_csv(metrics_path)
    if df.empty:
        return html.Div("No metrics available.", style={'color': '#888', 'fontStyle': 'italic', 'marginTop': '20px'})
    metrics = df.iloc[0].to_dict()
    # Professionelles Card-Layout
    card_style = {
        'background': 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)',
        'borderRadius': '14px',
        'boxShadow': '0 2px 12px rgba(0,0,0,0.07)',
        'padding': '24px 32px',
        'margin': '24px 0 0 0',
        'display': 'flex',
        'flexWrap': 'wrap',
        'gap': '32px',
        'justifyContent': 'center'
    }
    item_style = {
        'minWidth': '160px',
        'margin': '0 12px',
        'padding': '12px 0',
        'textAlign': 'center'
    }
    value_style = {
        'fontSize': '1.7rem',
        'fontWeight': '700',
        'color': '#3b4252',
        'marginBottom': '4px'
    }
    label_style = {
        'fontSize': '0.95rem',
        'color': '#6b7280',
        'fontWeight': '500',
        'letterSpacing': '0.01em'
    }
    # Reihenfolge und Labels für Anzeige
    show_keys = [
        ("final_realized_pnl", "Final Realized PnL"),
        ("winrate", "Winrate"),
        ("long_short_ratio", "Long/Short Ratio"),
        ("n_trades", "Trades"),
        ("n_long_trades", "Long Trades"),
        ("n_short_trades", "Short Trades"),
        ("avg_win", "Ø Win"),
        ("avg_loss", "Ø Loss"),
        ("max_win", "Max Win"),
        ("max_loss", "Max Loss"),
        ("max_consecutive_wins", "Max Consecutive Wins"),
        ("max_consecutive_losses", "Max Consecutive Losses"),
        ("commissions", "Commissions"),
    ]
    items = []
    # kleine Helferfunktion zur konsistenten Formatierung
    def _fmt(key, val):
        try:
            if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and val == ""):
                return "N/A"
            k = str(key).lower()
            # Currency-like keys -> USDT (4 decimals)
            currency_keys = {'final_realized_pnl', 'avg_win', 'avg_loss', 'max_win', 'max_loss', 'commissions', 'commission', 'realized_pnl', 'unrealized_pnl'}
            if any(ck in k for ck in currency_keys):
                v = float(val)
                return f"{v:.4f}"
            # Counters / integer-like
            count_terms = ['n_trades', 'n_long_trades', 'n_short_trades', 'trades', 'long_trades', 'short_trades', 'total', 'count', 'iterations', 'positions', 'max_consecutive']
            if any(ct in k for ct in count_terms):
                try:
                    return str(int(float(val)))
                except Exception:
                    s = str(val)
                    return s[:-2] if s.endswith('.0') else s
            # Winrate -> percent
            if 'winrate' in k or 'win rate' in k or 'win_rate' in k:
                v = float(val)
                return f"{(v*100 if v <= 1 else v):.2f}%"
            # Fallback: floats -> 4 decimals, sonst str
            if isinstance(val, float) or isinstance(val, int):
                if abs(float(val) - int(float(val))) < 1e-9:
                    return f"{int(float(val))}"
                return f"{float(val):.4f}"
            return str(val)
        except Exception:
            return str(val)
    for key, label in show_keys:
        raw = metrics.get(key, "")
        # append unit to label for currency-like keys
        currency_keys = {'final_realized_pnl', 'avg_win', 'avg_loss', 'max_win', 'max_loss', 'commissions', 'commission', 'realized_pnl', 'unrealized_pnl'}
        display_label = f"{label} (USD/T)" if any(ck in key.lower() for ck in currency_keys) else label
        val = _fmt(key, raw)
        items.append(
            html.Div([
                html.Div(val, style=value_style),
                html.Div(display_label, style=label_style)
            ], style=item_style)
        )
    return html.Div(items, style=card_style)

def build_layout(collectors, selected=None, runs_df=None, menu_open=False, run_id=None):
    # Menu-Toggle Button separat erstellen
    toggle_button = html.Button([
        html.Div([
            html.Div(style={
                'width': '20px',
                'height': '2px',
                'backgroundColor': 'white',
                'margin': '3px 0',
                'borderRadius': '2px',
                'transition': 'all 0.3s ease'
            }),
            html.Div(style={
                'width': '20px',
                'height': '2px',
                'backgroundColor': 'white',
                'margin': '3px 0',
                'borderRadius': '2px',
                'transition': 'all 0.3s ease'
            }),
            html.Div(style={
                'width': '20px',
                'height': '2px',
                'backgroundColor': 'white',
                'margin': '3px 0',
                'borderRadius': '2px',
                'transition': 'all 0.3s ease'
            })
        ], style={
            'display': 'flex',
            'flexDirection': 'column',
            'alignItems': 'center',
            'justifyContent': 'center'
        })
    ],
        id="menu-toggle-btn",
        style={
            'position': 'fixed',
            'top': '25px',
            'left': '25px',
            'zIndex': '1002',
            'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            'color': 'white',
            'border': 'none',
            'borderRadius': '12px',
            'width': '48px',
            'height': '48px',
            'cursor': 'pointer',
            'boxShadow': '0 8px 25px rgba(102, 126, 234, 0.4)',
            'transition': 'all 0.4s cubic-bezier(0.4, 0.0, 0.2, 1)',
            'backdropFilter': 'blur(10px)',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center'
        }
    )
    
    # Slide Menu Container (ohne Button)
    slide_menu_content = []
    if runs_df is not None:
        from core.visualizing.dashboard.callbacks.menu import slide_menu_component
        sidebar = slide_menu_component.create_sidebar(runs_df, menu_open, is_fullscreen=False)
        # Extrahiere nur die Sidebar-Inhalte
        if hasattr(sidebar, 'children') and len(sidebar.children) > 1:
            slide_menu_content = sidebar.children[1].children

    # --- NEU: adapt sidebar proportions for single-run + single-instrument mode ---
    single_mode = bool(run_id) and isinstance(collectors, (list, tuple)) and len(collectors) == 1
    # defaults
    default_menu_width = "380px"
    compact_menu_width = "320px"
    menu_width = compact_menu_width if single_mode else default_menu_width
    menu_padding = "16px" if single_mode else "22px"
    menu_item_gap = "8px" if single_mode else "12px"

    # Wrap inner content to apply consistent padding / spacing / scroll behaviour
    inner_wrapper = html.Div(
        children=slide_menu_content,
        style={
            'padding': menu_padding,
            'display': 'flex',
            'flexDirection': 'column',
            'gap': menu_item_gap,
            'overflowY': 'auto',
            'height': '100%',
            'boxSizing': 'border-box'
        }
    )

    slide_menu = html.Div(
        inner_wrapper,
        id="slide-menu",
        style={
            'position': 'fixed',
            'top': '0',
            'left': f'-{menu_width}' if not menu_open else '0',
            'width': menu_width,
            'height': '100vh',
            'background': 'linear-gradient(145deg, #ffffff 0%, #f8fafc 50%, #f1f5f9 100%)',
            'boxShadow': '4px 0 40px rgba(0,0,0,0.12), 0 0 0 1px rgba(255,255,255,0.05)' if menu_open else 'none',
            'zIndex': '1001',
            'transition': 'all 0.4s cubic-bezier(0.4, 0.0, 0.2, 1)',
            'borderRight': '1px solid rgba(226, 232, 240, 0.8)'
        }
    )

    # Fullscreen-Close-Button (rechts unten)
    fullscreen_close_button = html.Button([
        html.Div("✕", style={
            'fontSize': '20px',
            'lineHeight': '1',
            'fontWeight': 'bold'
        })
    ],
        id="fullscreen-close-btn",
        style={
            'position': 'fixed',
            'bottom': '25px',
            'right': '25px',
            'zIndex': '1003',
            'background': 'linear-gradient(135deg, #dc3545 0%, #fd7e14 100%)',
            'color': 'white',
            'border': 'none',
            'borderRadius': '50%',
            'width': '60px',
            'height': '60px',
            'cursor': 'pointer',
            'boxShadow': '0 8px 25px rgba(220, 53, 69, 0.4)',
            'transition': 'all 0.3s cubic-bezier(0.4, 0.0, 0.2, 1)',
            'display': 'none',  # Initial versteckt
            'alignItems': 'center',
            'justifyContent': 'center',
            'fontFamily': 'monospace',
            'fontSize': '20px'
        }
    )

    # Main Content mit verbessertem Styling
    main_style = {
        'minHeight':'100vh',
        'background':'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        'fontFamily':'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
        'marginLeft': '0px',
        'transition': 'margin-left 0.4s cubic-bezier(0.4, 0.0, 0.2, 1)',
        'position': 'relative',
        'zIndex': '1'
    }

    header = html.Div([
        html.Div("by Raph & Ferdi", style={
            'position': 'absolute','top': '8px','right': '15px',
            'color': 'rgba(255,255,255,0.6)','fontSize': '10px',
            'fontFamily': 'Inter, system-ui, sans-serif','fontWeight': '400',
            'letterSpacing': '0.5px'
        }),
        html.H1("Algorithmic Trading Dashboard", style={
            'textAlign':'center','color':'#ffffff','margin':'0',
            'fontFamily':'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
            'fontWeight':'700','letterSpacing':'-0.02em','fontSize':'2rem',
            'textShadow':'0 2px 4px rgba(0,0,0,0.1)'
        }),
        html.P("Professional Trading Analytics & Performance Monitoring", style={
            'textAlign':'center','color':'rgba(255,255,255,0.9)',
            'fontFamily':'Inter, system-ui, sans-serif','fontSize':'0.9rem',
            'fontWeight':'400','margin':'5px 0 0 0','letterSpacing':'0.01em'
        }),
    ], style={
        'background':'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'padding':'15px 20px','marginBottom':'0','boxShadow':'0 4px 16px rgba(0,0,0,0.1)',
        'position':'relative','display':'flex','flexDirection':'column',
        'justifyContent':'center','alignItems':'center','minHeight':'85px'
    })

    # Überarbeiteter Block für Instrumente
    collector_dropdown = html.Div([
        html.Div([
            html.Div("Instruments", style={
                'fontSize': '12px','fontWeight':'600','letterSpacing':'.08em',
                'color':'#111','textTransform':'uppercase'
            }),
            html.Div("Select one or multiple symbols", style={
                'fontSize':'11px','color':'#555','marginTop':'2px'
            })
        ], style={'marginBottom':'8px'}),
        dcc.Dropdown(
            id="collector-dropdown",
            className="instrument-dropdown",
            options=[{'label': c, 'value': c} for c in collectors],
            value=[selected] if selected else ([collectors[0]] if collectors else []),
            multi=True,
            placeholder="Choose instruments",
            clearable=False,
            style={'fontSize':'13px'}
        ),
        html.Div(id="instrument-hint", style={
            'fontSize':'11px','color':'#666','marginTop':'6px','fontStyle':'italic'
        })
    ], style={
        'background': '#ffffff',
        'border': '1px solid #d9dde2',          # was: 1px solid #000
        'borderRadius': '12px',                 # was 10px
        'padding': '16px 18px 14px 18px',       # slight adjust
        'margin': '15px 20px',
        'boxShadow': '0 2px 8px rgba(0,0,0,0.04)'  # softer (was 0 2px 4px ...)
    })

    trade_details_panel = html.Div([
        html.Div(id='trade-details-panel', children=[
            html.Div([
                html.H4("Trade Details", style={
                    'color':'#2c3e50','marginBottom':'10px',
                    'fontFamily':'Inter, system-ui, sans-serif','fontWeight':'600',
                    'textAlign':'center','fontSize':'18px','letterSpacing':'-0.01em'
                }),
                html.P("Click on a trade marker in the chart below to see details", style={
                    'color':'#6c757d','fontFamily':'Inter, system-ui, sans-serif',
                    'textAlign':'center','fontSize':'14px','margin':'0','fontWeight':'400'
                })
            ])
        ])
    ], style={
        'background':'linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%)',
        'border':'1px solid rgba(222, 226, 230, 0.6)','borderRadius':'0 0 16px 16px',
        'padding':'20px','marginBottom':'15px','maxHeight':'300px','overflowY':'auto',
        'boxShadow':'0 4px 20px rgba(0,0,0,0.08)','backdropFilter':'blur(10px)',
        'position':'relative'
    })

    price_block = html.Div([
        html.Div([
            html.H3("Price Data & Trading Signals", style={
                'color':'#2c3e50','marginBottom':'20px',
                'fontFamily':'Inter, system-ui, sans-serif','fontWeight':'600',
                'fontSize':'20px','letterSpacing':'-0.01em'
            }),
            dcc.Graph(id='price-chart', style={'height':'650px'})
        ], style={
            'background':'#ffffff','borderRadius':'16px','padding':'25px',
            'boxShadow':'0 4px 20px rgba(0,0,0,0.08)',
            'border':'1px solid rgba(222, 226, 230, 0.6)'
        })
    ], style={'margin':'15px 20px'})

    indicators_container = html.Div([ html.Div(id='indicators-container') ],
                                    style={'margin':'10px 20px'})

    metrics_panel = None
    from pathlib import Path
    # parents[3] points to project root (same as main.py ROOT); parents[4] was off-by-one
    results_root = Path(__file__).resolve().parents[3] / "data" / "DATA_STORAGE" / "results"
    # Prefer explicit run_id (passed from main). If run_id provided, look under that folder.
    if run_id:
        run_dir = results_root / str(run_id)
        if run_dir.exists() and run_dir.is_dir():
            # If selected looks like an instrument, try instrument subfolder first
            if selected:
                candidate = run_dir / str(selected) / "trade_metrics.csv"
                if candidate.exists():
                    metrics_panel = build_metrics_panel(str(candidate))
            # Fallback to run-level metrics file
            if metrics_panel is None:
                candidate2 = run_dir / "trade_metrics.csv"
                if candidate2.exists():
                    metrics_panel = build_metrics_panel(str(candidate2))
            # init metrics lookup performed
        else:
            pass
    else:
        # no run_id provided
        pass

    # Ensure metrics-panel placeholder always exists so callbacks can populate it later
    if not metrics_panel:
        metrics_panel = html.Div(
            "No metrics available", 
            id="metrics-panel",
            style={'textAlign':'center','color':'#6c757d','fontFamily':'Inter, system-ui, sans-serif','padding':'20px'}
        )
    else:
        # If we have initial content, wrap it with the id so the callback can update children
        metrics_panel = html.Div(metrics_panel, id="metrics-panel")

    refresh = html.Div([
        html.Button('Update Dashboard', id='refresh-btn', n_clicks=0,
            style={
                'padding':'14px 32px','fontSize':'16px',
                'background':'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                'color':'white','border':'none','borderRadius':'25px',
                'cursor':'pointer','fontFamily':'Inter, system-ui, sans-serif',
                'fontWeight':'600','letterSpacing':'0.01em',
                'boxShadow':'0 4px 15px rgba(102, 126, 234, 0.4)',
                'transition':'all 0.3s ease','textShadow':'0 1px 2px rgba(0,0,0,0.1)'
            })
    ], style={'textAlign':'center','margin':'30px 0'})

    main_content = html.Div([
        header, collector_dropdown, trade_details_panel, price_block,
        indicators_container, metrics_panel, refresh
    ], id="main-content", style=main_style)

    return html.Div([
        html.Div([
            html.Link(
                href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
                rel="stylesheet"
            )
        ]),
        toggle_button,
        slide_menu,
        fullscreen_close_button,
        main_content,
        # Hidden stores für Menu-State
        dcc.Store(id='menu-open-store', data=menu_open),
        dcc.Store(id='menu-fullscreen-store', data=False),
        dcc.Store(id='selected-run-store', data=run_id),
        # NEU: YAML-Store immer im Layout
        dcc.Store(id='run-yaml-store', data={}),
        # NEU: QuantStats Status Store (für Callback-Dummy)
        dcc.Store(id='quantstats-status', data=""),
    ], style={
        # Globale Styles direkt hier
        'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
    })