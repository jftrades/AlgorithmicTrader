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
    def _fmt(key, val):
        try:
            if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and val == ""):
                return "N/A"
            k = str(key).lower()
            currency_keys = {'final_realized_pnl', 'avg_win', 'avg_loss', 'max_win', 'max_loss', 'commissions', 'commission', 'realized_pnl', 'unrealized_pnl'}
            if any(ck in k for ck in currency_keys):
                v = float(val)
                return f"{v:.4f}"
            count_terms = ['n_trades', 'n_long_trades', 'n_short_trades', 'trades', 'long_trades', 'short_trades', 'total', 'count', 'iterations', 'positions', 'max_consecutive']
            if any(ct in k for ct in count_terms):
                try:
                    return str(int(float(val)))
                except Exception:
                    s = str(val)
                    return s[:-2] if s.endswith('.0') else s
            if 'winrate' in k or 'win rate' in k or 'win_rate' in k:
                v = float(val)
                return f"{(v*100 if v <= 1 else v):.2f}%"
            if isinstance(val, float) or isinstance(val, int):
                if abs(float(val) - int(float(val))) < 1e-9:
                    return f"{int(float(val))}"
                return f"{float(val):.4f}"
            return str(val)
        except Exception:
            return str(val)
    for key, label in show_keys:
        raw = metrics.get(key, "")
        currency_keys = {'final_realized_pnl', 'avg_win', 'avg_loss', 'max_win', 'max_loss', 'commissions', 'commission', 'realized_pnl', 'unrealized_pnl'}
        display_label = f"{label} (USD/T)" if any(ck in key.lower() for ck in currency_keys) else label
        val = _fmt(key, raw)
        items.append(
            html.Div([
                html.Div(val, className="metric-value"),
                html.Div(display_label, className="metric-label")
            ], className="metric-item")
        )
    return html.Div(items, className="metrics-panel")

def build_layout(collectors, selected=None, runs_df=None, menu_open=False, run_id=None):
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
        className="btn-floating primary shadow-lg",
        style={
            'position': 'fixed',
            'top': '25px',
            'left': '25px',
            'zIndex': '1002'
        }
    )
    
    slide_menu_content = []
    if runs_df is not None:
        from core.visualizing.dashboard.callbacks.menu import slide_menu_component
        sidebar = slide_menu_component.create_sidebar(runs_df, menu_open, is_fullscreen=False)
        if hasattr(sidebar, 'children') and len(sidebar.children) > 1:
            slide_menu_content = sidebar.children[1].children

    single_mode = bool(run_id) and isinstance(collectors, (list, tuple)) and len(collectors) == 1
    default_menu_width = "380px"
    compact_menu_width = "320px"
    menu_width = compact_menu_width if single_mode else default_menu_width
    menu_padding = "16px" if single_mode else "22px"
    menu_item_gap = "8px" if single_mode else "12px"

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
        className="side-menu glass-panel",
        style={
            'position': 'fixed',
            'top': '0',
            'left': f'-{menu_width}' if not menu_open else '0',
            'width': menu_width,
            'height': '100vh',
            'background': 'linear-gradient(145deg, #ffffff 0%, #f8fafc 50%, #f1f5f9 100%)',
            'boxShadow': 'none',
            'borderRight': '1px solid rgba(226,232,240,0.8)',
            'zIndex': '1001',
            'transition': 'all 0.4s cubic-bezier(0.4,0,0.2,1)',
            'overflow': 'hidden'
        }
    )

    fullscreen_close_button = html.Button([
        html.Div("✕", style={
            'fontSize': '20px',
            'lineHeight': '1',
            'fontWeight': 'bold'
        })
    ],
        id="fullscreen-close-btn",
        className="btn-circle danger-gradient shadow-xl",
        style={
            'display': 'none',
            'position': 'fixed',
            'bottom': '25px',
            'right': '25px',
            'zIndex': '1003'
        }
    )

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
    ], className="app-header gradient-primary shadow-md")

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
    ], className="panel box border subtle-shadow")

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
    ], className="panel box glass-panel trade-details")

    price_block = html.Div([
        html.Div([
            html.Div([
                # COMPACT toolbar (slider left, actions right)
                html.Div(className="chart-toolbar compact", children=[
                    html.Div(className="slider-block", children=[
                        dcc.RangeSlider(
                            id="time-range-slider",
                            min=0, max=100, value=[0, 100],
                            allowCross=False,
                            step=1,
                            updatemode='mouseup',
                            className="range-slider flex"
                        ),
                        html.Div(id="time-range-display", className="range-summary")
                    ]),
                    html.Div(className="toolbar-actions", children=[
                        dcc.Dropdown(
                            id="timeframe-dropdown",
                            options=[], value=None, clearable=False,
                            placeholder="TF",
                            className="tf-dropdown compact"
                        ),
                        html.Button("Trades",
                                    id="toggle-trades-btn",
                                    n_clicks=0,
                                    className="btn btn-toggle mini",
                                    style={})
                    ])
                ])
            ]),
            dcc.Graph(id='price-chart', style={'height': '650px'})
        ], className="price-chart-container compact")
    ], className="panel chart-panel compact")

    indicators_container = html.Div([ html.Div(id='indicators-container') ],
                                    className="indicators-wrapper")

    metrics_panel = None
    from pathlib import Path
    results_root = Path(__file__).resolve().parents[3] / "data" / "DATA_STORAGE" / "results"
    if run_id:
        run_dir = results_root / str(run_id)
        if run_dir.exists() and run_dir.is_dir():
            if selected:
                candidate = run_dir / str(selected) / "trade_metrics.csv"
                if candidate.exists():
                    metrics_panel = build_metrics_panel(str(candidate))
            if metrics_panel is None:
                candidate2 = run_dir / "trade_metrics.csv"
                if candidate2.exists():
                    metrics_panel = build_metrics_panel(str(candidate2))
        else:
            pass
    else:
        pass

    if not metrics_panel:
        metrics_panel = html.Div(
            "No metrics available", 
            id="metrics-panel",
            className="panel empty metrics-wrapper"
        )
    else:
        metrics_panel = html.Div(metrics_panel, id="metrics-panel", className="panel metrics-wrapper")

    refresh = html.Div([
        html.Button('Update Dashboard', id='refresh-btn', n_clicks=0,
            className="btn primary-gradient lg shadow-md")
    ], className="centered block-mt")

    main_content = html.Div([
        header, collector_dropdown, trade_details_panel, price_block,
        indicators_container, metrics_panel, refresh
    ], id="main-content", className="main-content")

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
        dcc.Store(id='menu-open-store', data=menu_open),
        dcc.Store(id='menu-fullscreen-store', data=False),
        dcc.Store(id='selected-run-store', data=run_id),
        dcc.Store(id='run-yaml-store', data={}),
        dcc.Store(id='quantstats-status', data=""),
        dcc.Store(id='show-trades-store', data=True),
        dcc.Store(id='time-slider-store', data=None),  # NEW: persist range slider selection
    ], className="app-root font-default")