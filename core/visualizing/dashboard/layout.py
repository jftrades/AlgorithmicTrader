# core/visualizing/dashboard/layout.py
from dash import html, dcc
from core.visualizing.dashboard.slide_menu import SlideMenuComponent
import pandas as pd
import os

def build_metrics_panel(metrics_path, single_mode: bool = False):
    """
    Placeholder panel only. Actual metrics injected later.
    single_mode -> no outer border/background to avoid double frame.
    """
    base_style = {
        'border': '1px solid #e2e8f0',
        'background': 'linear-gradient(135deg,#ffffff 0%,#f1f5f9 100%)',
        'boxShadow': '0 4px 14px -4px rgba(0,0,0,0.10), 0 2px 4px rgba(0,0,0,0.05)',
        'padding': '12px 18px 10px 18px',
        'borderRadius': '20px'
    }
    if single_mode:
        # Remove framing to avoid double border in inline usage
        base_style.update({
            'border': 'none',
            'background': 'transparent',
            'boxShadow': 'none',
            'padding': '0',
            'borderRadius': '0'
        })
    return html.Div(
        id="metrics-panel",
        children=[html.Div("Loading metrics ...",
                           style={'fontSize': '13px','color': '#64748b','fontStyle': 'italic','padding': '4px 0 0 0'})],
        style={
            **base_style,
            'minHeight': '60px',
            'width': '100%',
            'boxSizing': 'border-box',
            'margin': '18px 0 30px 0'  # bottom space increased
        }
    )

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
            'position': 'absolute','top': '6px','right': '12px',
            'color': 'rgba(255,255,255,0.65)','fontSize': '9px',
            'fontFamily': 'Inter, system-ui, sans-serif','fontWeight': '400',
            'letterSpacing': '0.4px'
        }),
        html.H1("Algorithmic Trading Dashboard", style={
            'textAlign':'center','color':'#ffffff','margin':'0',
            'fontFamily':'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
            'fontWeight':'700','letterSpacing':'-0.025em','fontSize':'1.85rem',
            'textShadow':'0 2px 4px rgba(0,0,0,0.12)'
        }),
        html.P("Professional Trading Analytics & Performance Monitoring", style={
            'textAlign':'center','color':'rgba(255,255,255,0.88)',
            'fontFamily':'Inter, system-ui, sans-serif','fontSize':'0.85rem',
            'fontWeight':'400','margin':'4px 0 0 0','letterSpacing':'0.005em'
        }),
    ], className="app-header gradient-primary shadow-md", style={
        'padding': '18px 24px 16px 24px'  # kompakter
    })

    collector_dropdown = html.Div([
        html.Div([
            html.Div("Instruments", style={
                'fontSize': '11px','fontWeight':'700','letterSpacing':'.06em',
                'color':'#1f2937','textTransform':'uppercase','marginBottom':'2px'
            }),
            html.Div("Select one or multiple symbols", style={
                'fontSize':'10px','color':'#6b7280','lineHeight':'1.2'
            })
        ], style={'marginBottom':'6px'}),
        dcc.Dropdown(
            id="collector-dropdown",
            className="instrument-dropdown",
            options=[{'label': c, 'value': c} for c in collectors],
            value=[selected] if selected else ([collectors[0]] if collectors else []),
            multi=True,
            placeholder="Choose instruments",
            clearable=False,
            style={'fontSize':'12px'}
        ),
        html.Div(id="instrument-hint", style={
            'fontSize':'10px','color':'#6b7280','marginTop':'4px','fontStyle':'italic'
        })
    ], className="panel box border subtle-shadow", style={
        'padding': '12px 16px 10px 16px',  # kompakter
        'marginBottom': '12px'  # weniger Abstand nach unten
    })

    trade_details_panel = html.Div([
        html.Div(id='trade-details-panel', children=[
            html.Div([
                html.H4("Trade Details", style={
                    'color':'#1f2937','marginBottom':'6px',
                    'fontFamily':'Inter, system-ui, sans-serif','fontWeight':'600',
                    'textAlign':'left','fontSize':'14px','letterSpacing':'-0.01em'
                }),
                html.P("Click on a trade marker in the chart below to see details", style={
                    'color':'#6b7280','fontFamily':'Inter, system-ui, sans-serif',
                    'textAlign':'left','fontSize':'12px','margin':'0','fontWeight':'400',
                    'lineHeight':'1.3'
                })
            ])
        ])
    ], className="panel box glass-panel trade-details", style={
        'padding': '12px 16px 10px 16px',  # kompakter
        'marginBottom': '12px',  # weniger Abstand
        'background': 'linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(248,250,252,0.90) 100%)',
        'border': '1px solid rgba(226,232,240,0.8)',
        'borderRadius': '12px',
        'boxShadow': '0 2px 8px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06)'
    })

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
                ], style={'marginBottom': '8px'})  # weniger Abstand zur Chart
            ]),
            dcc.Graph(id='price-chart', style={'height': '650px', 'width': '100%'})
        ], className="price-chart-container compact")
    ], className="panel chart-panel compact", style={
        'width': '100%', 
        'boxSizing': 'border-box',
        'marginBottom': '14px'  # kompakter Abstand
    })

    indicators_container = html.Div([ html.Div(id='indicators-container') ],
                                    className="indicators-wrapper")

    metrics_panel = build_metrics_panel(None, single_mode=single_mode)

    # Neuer innerer Content-Wrapper mit reduziertem Padding
    inner_padding = '24px' if single_mode else '22px'
    content_body = html.Div([
        collector_dropdown,
        trade_details_panel,
        price_block,
        indicators_container,
        metrics_panel
    ], id="content-body", style={
        'padding': f'10px {inner_padding} 50px {inner_padding}',  # top padding reduziert
        'display': 'flex',
        'flexDirection': 'column',
        'gap': '0px',  # entfernt Gap, da Komponenten eigene Margins haben
        'width': '100%',
        'boxSizing': 'border-box'
    })

    main_inner = html.Div([
        header,          # full-bleed
        content_body     # gepaddeter Bereich
    ], style={'display': 'flex','flexDirection':'column','gap':'0'})

    main_content = html.Div(main_inner, id="main-content", className="main-content", style={
        'paddingLeft': '0',
        'paddingRight': '0',
        'paddingTop': '0',          # Header hat eigenes Padding
        'paddingBottom': '0',
        'boxSizing': 'border-box',
        'width': '100%',
        'margin': '0',
        'flex': '1 1 auto',
        'alignSelf': 'stretch'
    })

    # Hidden placeholder to satisfy callbacks expecting 'refresh-btn'
    hidden_refresh_btn = html.Button(id='refresh-btn', n_clicks=0, style={'display': 'none'})

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
        hidden_refresh_btn,  # NEW hidden button
        dcc.Store(id='menu-open-store', data=menu_open),
        dcc.Store(id='menu-fullscreen-store', data=False),
        dcc.Store(id='selected-run-store', data=([run_id] if run_id else [])),
        dcc.Store(id='run-yaml-store', data={}),
        dcc.Store(id='quantstats-status', data=""),
        dcc.Store(id='show-trades-store', data=True),
        dcc.Store(id='time-slider-store', data=None),  # NEW: persist range slider selection
    ], className="app-root font-default", style={
        'overflowX': 'hidden',
        'minHeight': '100vh',
        'width': '100%',          # CHANGED from 100vw
        'maxWidth': '100%',       # ensure no overflow
        'display': 'flex',        # NEW to stabilize first paint
        'flexDirection': 'column',
        'padding':'0',          # NEW explicit
        'margin':'0'            # NEW explicit
    })