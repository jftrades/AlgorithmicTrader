from dash import html, dcc
from .service import ParameterAnalysisService

def build_analyzer_layout(runs_df, service: ParameterAnalysisService):
    metric_options = [{'label': m, 'value': m} for m in service.available_metrics(runs_df)]
    param_cols = service.run_param_columns(runs_df)
    param_options = [{'label': p, 'value': p} for p in param_cols]

    def dark_dropdown_style():
        return {
            'control': {
                'backgroundColor': '#0f172a',
                'borderColor': '#334155',
                'color': '#f1f5f9',
                'minHeight': '42px',
                'boxShadow': 'none',
                '&:hover': {'borderColor': '#6366f1'},
                'border': '1px solid #334155'
            },
            'placeholder': {'color': '#f1f5f9', 'fontWeight': '500'},
            'singleValue': {'color': '#f1f5f9', 'fontWeight': '600'},
            'input': {'color': '#f1f5f9'},
            'menu': {
                'backgroundColor': '#1e293b',
                'border': '1px solid #334155',
                'maxHeight': '340px',
                'boxShadow': '0 8px 22px -6px rgba(0,0,0,0.55)'
            },
            'option': {
                'backgroundColor': '#1e293b',
                'color': '#e2e8f0',
                'padding': '10px 14px',
                '&:hover': {'backgroundColor': '#334155', 'color': '#f8fafc'},
                'cursor': 'pointer'
            },
            'option--is-selected': {
                'backgroundColor': '#6366f1',
                'color': '#ffffff',
                'fontWeight': '600'
            },
            'indicatorSeparator': {'backgroundColor': '#334155'},
            'dropdownIndicator': {'color': '#94a3b8'},
            'clearIndicator': {'color': '#64748b'}
        }

    return html.Div([
        # Debug-Info
        html.Div([
            html.P(f"Loaded {len(runs_df)} runs, {len(param_options)} parameters, {len(metric_options)} metrics", 
                   style={'color': '#94a3b8', 'fontSize': '12px', 'margin': '0 0 20px 0'})
        ]),
        
        html.Div([
            html.Div([
                html.H2("Parameter Analyzer", style={
                    'margin': '0', 'color': '#f1f5f9', 'fontFamily': 'Inter',
                    'fontSize': '32px', 'fontWeight': '700', 'letterSpacing': '-.02em'
                }),
                html.P("Explore performance metrics across parameter combinations.",
                       style={'margin': '6px 0 0 0', 'color': '#94a3b8', 'fontSize': '15px', 'fontFamily': 'Inter'})
            ])
        ], style={'display': 'flex', 'justifyContent': 'space-between',
                  'alignItems': 'flex-start', 'marginBottom': '30px'}),

        html.Div([
            # NEU: Horizontaler Toolbar statt vertikaler Sidebar
            html.Div([
                # Metric
                html.Div([
                    html.Label("Target Metric", style=_label(marginTop=0)),
                    dcc.Dropdown(
                        id="param-analyzer-run-metric",
                        options=metric_options,
                        placeholder="Select metric",
                        clearable=False,
                        style=dark_dropdown_style()
                    )
                ], style={'display': 'flex', 'flexDirection': 'column', 'minWidth': '180px'}),
                # X
                html.Div([
                    html.Label("X Parameter", style=_label(marginTop=0)),
                    dcc.Dropdown(
                        id="param-analyzer-xparam",
                        options=param_options,
                        placeholder="X param",
                        clearable=False,
                        style=dark_dropdown_style()
                    )
                ], style={'display': 'flex', 'flexDirection': 'column', 'minWidth': '160px'}),
                # Y
                html.Div([
                    html.Label("Y Parameter", style=_label(marginTop=0)),
                    dcc.Dropdown(
                        id="param-analyzer-yparam",
                        options=param_options,
                        placeholder="Y param",
                        clearable=False,
                        style=dark_dropdown_style()
                    )
                ], style={'display': 'flex', 'flexDirection': 'column', 'minWidth': '160px'}),
                # Z
                html.Div([
                    html.Label("Z Parameter (Optional)", style=_label(marginTop=0)),
                    dcc.Dropdown(
                        id="param-analyzer-zparam",
                        options=param_options,
                        placeholder="Z param",
                        clearable=True,
                        style=dark_dropdown_style()
                    )
                ], style={'display': 'flex', 'flexDirection': 'column', 'minWidth': '180px'}),
                # Agg
                html.Div([
                    html.Label("Aggregation", style=_label(marginTop=0)),
                    dcc.Dropdown(
                        id="param-analyzer-aggfunc",
                        options=[{'label': a.title(), 'value': a} for a in ['mean','median','max','min','std']],
                        value='mean',
                        clearable=False,
                        style=dark_dropdown_style()
                    )
                ], style={'display': 'flex', 'flexDirection': 'column', 'minWidth': '140px'}),
                # Buttons
                html.Div([
                    html.Button("2D Analysis", id="param-analyzer-refresh-btn", n_clicks=0, style=_primary_btn()),
                    html.Button("3D Analysis", id="param-analyzer-3d-btn", n_clicks=0, style=_primary_btn()),
                    html.Button("Full Pair Matrix", id="param-analyzer-build-matrix-btn", n_clicks=0, style=_secondary_btn())
                ], style={
                    'display': 'flex',
                    'gap': '12px',
                    'flexWrap': 'wrap',
                    'alignItems': 'center',
                    'paddingTop': '6px',
                    'minWidth': '300px'
                })
            ], style={
                'display': 'flex',
                'flexWrap': 'wrap',
                'gap': '20px 28px',
                'alignItems': 'flex-end',
                'background': 'linear-gradient(135deg,#1e293b,#0f172a)',
                'padding': '20px 26px 18px 26px',
                'border': '1px solid #334155',
                'borderRadius': '18px',
                'boxShadow': '0 6px 18px -4px rgba(0,0,0,0.55)',
                'marginBottom': '32px'
            }),
            # Ergebnisse (volle Breite)
            html.Div([
                html.Div(id="param-analyzer-results-container", style={'width': '100%'}),
                html.Div(id="param-analyzer-matrix-container", style={'width': '100%', 'marginTop': '28px'})
            ], style={
                'display': 'flex',
                'flexDirection': 'column',
                'gap': '0px',
                'flex': '1 1 auto',
                'width': '100%'
            })
        ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '0px'})
    ], className="param-analyzer-root")

def _label(marginTop=4):
    return {
        'display': 'block', 'fontFamily': 'Inter', 'fontSize': '13px', 'letterSpacing': '.5px',
        'fontWeight': '600', 'color': '#cbd5e1', 'marginTop': f'{marginTop}px',
        'marginBottom': '6px', 'textTransform': 'uppercase'
    }

def _dropdown_style():
    return {
        'background': '#0f172a', 'color': '#f1f5f9', 'border': '1px solid #334155',
        'borderRadius': '10px', 'fontFamily': 'Inter', 'fontSize': '14px'
    }

def _primary_btn():
    return {
        'background': 'linear-gradient(90deg,#6366f1,#8b5cf6)', 'color': '#fff', 'border': 'none',
        'borderRadius': '12px', 'padding': '12px 20px', 'fontFamily': 'Inter', 'fontWeight': '600',
        'cursor': 'pointer', 'fontSize': '14px', 'letterSpacing': '.5px',
        'boxShadow': '0 4px 14px -2px rgba(99,102,241,0.55)'
    }

def _secondary_btn():
    return {
        'background': '#334155', 'color': '#e2e8f0', 'border': '1px solid #475569',
        'borderRadius': '12px', 'padding': '12px 20px', 'fontFamily': 'Inter',
        'fontWeight': '600', 'cursor': 'pointer', 'fontSize': '14px', 'letterSpacing': '.5px'
    }
