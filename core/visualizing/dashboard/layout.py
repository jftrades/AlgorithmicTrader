# core/visualizing/dashboard/layout.py
from dash import html, dcc
from core.visualizing.dashboard.slide_menu import SlideMenuComponent

def build_layout(collectors, selected=None, runs_df=None, menu_open=False):
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
        menu_component = SlideMenuComponent()
        sidebar = menu_component.create_sidebar(runs_df, menu_open, is_fullscreen=False)
        # Extrahiere nur die Sidebar-Inhalte
        if hasattr(sidebar, 'children') and len(sidebar.children) > 1:
            slide_menu_content = sidebar.children[1].children
    
    slide_menu = html.Div(
        slide_menu_content,
        id="slide-menu",
        style={
            'position': 'fixed',
            'top': '0',
            'left': '-380px' if not menu_open else '0',
            'width': '380px',
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

    metrics_block = html.Div([
        html.Div([
            html.H3("Performance Metrics", style={
                'color':'#2c3e50','marginBottom':'20px',
                'fontFamily':'Inter, system-ui, sans-serif','fontWeight':'600',
                'fontSize':'20px','letterSpacing':'-0.01em'
            }),
            html.Div(id='metrics-display', style={
                'background':'linear-gradient(145deg, #f8f9fa 0%, #ffffff 100%)',
                'border':'1px solid rgba(222, 226, 230, 0.6)','borderRadius':'12px',
                'padding':'25px'
            })
        ], style={
            'background':'#ffffff','borderRadius':'16px','padding':'25px',
            'boxShadow':'0 4px 20px rgba(0,0,0,0.08)',
            'border':'1px solid rgba(222, 226, 230, 0.6)'
        })
    ], style={'margin':'15px 20px'})

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
        indicators_container, metrics_block, refresh   # all_results entfernt
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
        dcc.Store(id='selected-run-store', data=None)
    ], style={
        # Globale Styles direkt hier
        'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
    })