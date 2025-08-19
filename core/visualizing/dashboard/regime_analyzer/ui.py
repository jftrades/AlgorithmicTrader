from pathlib import Path
from typing import Optional
import pandas as pd
from dash import html, dcc
from .service import RegimeService

_service: Optional[RegimeService] = None

def build_regime_layout(runs_df: Optional[pd.DataFrame] = None,
                        results_root: Optional[Path] = None,
                        preferred_run: Optional[str] = None,
                        **kwargs):
    global _service
    base_dir = results_root.parent.parent.parent if results_root else Path(".")
    _service = RegimeService(base_dir)
    
    # Get available runs
    available_runs = _service.get_available_runs()
    
    # Load initial data
    initial_run = preferred_run if preferred_run in available_runs else (available_runs[0] if available_runs else "run0")
    data_loaded = _service.load_data(initial_run) if available_runs else False
    
    # Get available indicators
    features = _service.get_feature_names() if data_loaded else []
    
    return html.Div([        
        # Header Section - FUTURISTIC DARK MODE
        html.Div([
            html.H1("REGIME ANALYZER", style={
                'color': '#ffffff',
                'fontSize': '28px',
                'fontWeight': '300',
                'letterSpacing': '3px',
                'margin': '0 0 8px 0',
                'textAlign': 'center',
                'fontFamily': '"Inter", "Segoe UI", sans-serif'
            }),
            html.P("Advanced Performance Analysis Across Indicator Regimes", style={
                'color': '#9ca3af',
                'fontSize': '14px',
                'textAlign': 'center',
                'margin': '0 0 0 0',
                'fontWeight': '400',
                'textTransform': 'uppercase',
                'letterSpacing': '1px'
            })
        ], style={
            'padding': '32px 0 24px 0',
            'borderBottom': '1px solid #374151',
            'background': 'linear-gradient(135deg, #1f2937 0%, #111827 100%)'
        }),

        # Control Panel - FUTURISTIC DARK MODE
        html.Div([
            html.H3("Analysis Configuration", style={
                'color': '#f9fafb',
                'fontSize': '16px',
                'fontWeight': '500',
                'margin': '0 0 24px 0',
                'textTransform': 'uppercase',
                'letterSpacing': '1px'
            }),
            
            # Row 1: Primary Controls
            html.Div([
                html.Div([
                    html.Label("Run Selection", style={
                        'fontWeight': '500',
                        'color': '#d1d5db',
                        'display': 'block',
                        'marginBottom': '8px',
                        'fontSize': '13px',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.5px'
                    }),
                    dcc.Dropdown(
                        id='regime-run-selector',
                        options=[{'label': run, 'value': run} for run in available_runs],
                        value=initial_run,
                        placeholder="Select run...",
                        className="regime-dropdown",  # FIX: Use className instead of Style
                        style={
                            'marginBottom': '16px'
                        }
                    )
                ], style={'width': '18%', 'display': 'inline-block', 'marginRight': '2%'}),  # FIX: Reduced width
                
                html.Div([
                    html.Label("Analysis Type", style={
                        'fontWeight': '500',
                        'color': '#d1d5db',
                        'display': 'block',
                        'marginBottom': '8px',
                        'fontSize': '13px',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.5px'
                    }),
                    dcc.Dropdown(
                        id='regime-analysis-type',
                        options=[
                            {'label': 'Index Analysis', 'value': 'index'},  # FIX: Removed emoji
                            {'label': 'Crypto Analysis', 'value': 'crypto'}  # FIX: Removed emoji
                        ],
                        value='crypto',
                        className="regime-dropdown",
                        style={
                            'marginBottom': '16px'
                        }
                    )
                ], style={'width': '18%', 'display': 'inline-block', 'marginRight': '2%'}),  # NEW: Analysis Type
                
                html.Div([
                    html.Label("Analysis Mode", style={
                        'fontWeight': '500',
                        'color': '#d1d5db',
                        'display': 'block',
                        'marginBottom': '8px',
                        'fontSize': '13px',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.5px'
                    }),
                    dcc.Dropdown(
                        id='regime-data-mode',
                        options=[
                            {'label': 'Equity Analysis', 'value': 'equity'},
                            {'label': 'Trade Entry Analysis', 'value': 'trade_entry'}
                        ],
                        value='equity',
                        className="regime-dropdown",  # FIX: Use className instead of Style
                        style={
                            'marginBottom': '16px'
                        }
                    )
                ], style={'width': '18%', 'display': 'inline-block', 'marginRight': '2%'}),  # FIX: Reduced width
                
                html.Div([
                    html.Label("Feature Selection", style={
                        'fontWeight': '500',
                        'color': '#d1d5db',
                        'display': 'block',
                        'marginBottom': '8px',
                        'fontSize': '13px',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.5px'
                    }),
                    dcc.Dropdown(
                        id='regime-feature-selector',
                        options=[{'label': f, 'value': f} for f in features],
                        value=features[0] if features else None,
                        placeholder="Select feature...",
                        className="regime-dropdown",  # FIX: Use className instead of Style
                        style={
                            'marginBottom': '16px'
                        }
                    )
                ], style={'width': '18%', 'display': 'inline-block', 'marginRight': '2%'}),  # FIX: Reduced width
                
                html.Div([
                    html.Label("Return Configuration", style={
                        'fontWeight': '500',
                        'color': '#d1d5db',
                        'display': 'block',
                        'marginBottom': '8px',
                        'fontSize': '13px',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.5px'
                    }),
                    dcc.Dropdown(
                        id='regime-return-type',
                        options=[
                            {'label': 'Current Return', 'value': 'equity_return'},
                            {'label': 'Cumulative Return', 'value': 'cumulative_return'},
                            {'label': 'Forward Return (Custom)', 'value': 'forward_return_custom'}
                        ],
                        value='forward_return_custom',
                        className="regime-dropdown",
                        style={
                            'marginBottom': '8px'
                        },
                        disabled=False
                    ),
                    # FIX: Forward Return Time Range Input
                    html.Div(id='forward-return-time-container', children=[
                        html.Label("Forward Time Range", style={
                            'fontWeight': '400',
                            'color': '#9ca3af',
                            'display': 'block',
                            'marginBottom': '8px',
                            'fontSize': '11px',
                            'textTransform': 'uppercase',
                            'letterSpacing': '0.5px'
                        }),
                        html.Div([
                            dcc.Input(
                                id='forward-time-value',
                                type='number',
                                min=1,
                                max=999999,  # FIX: Entferne 5000 Limit, jetzt viel höher
                                step=1,
                                value=1,
                                style={
                                    'width': '60px',
                                    'padding': '4px 8px',
                                    'borderRadius': '4px',
                                    'border': '1px solid #4b5563',
                                    'backgroundColor': '#374151',
                                    'color': '#f9fafb',
                                    'fontSize': '12px',
                                    'textAlign': 'center'
                                }
                            ),
                            dcc.Dropdown(
                                id='forward-time-unit',
                                options=[
                                    {'label': 'Minutes', 'value': 'minutes'},
                                    {'label': 'Hours', 'value': 'hours'},
                                    {'label': 'Days', 'value': 'days'},
                                    {'label': 'Weeks', 'value': 'weeks'},
                                    {'label': 'Periods', 'value': 'periods'}  # Raw data points
                                ],
                                value='hours',
                                className="regime-dropdown",
                                style={
                                    'width': '100px',
                                    'marginLeft': '8px',
                                    'fontSize': '11px'
                                }
                            )
                        ], style={
                            'display': 'flex',
                            'alignItems': 'center',
                            'gap': '0px'
                        }),
                        html.Div(id='forward-time-preview', style={
                            'fontSize': '10px',
                            'color': '#6b7280',
                            'marginTop': '4px',
                            'fontStyle': 'italic'
                        })
                    ], style={'marginTop': '8px'})
                ], style={'width': '20%', 'display': 'inline-block'})  # FIX: Adjusted width
            ]),
            
            # Row 2: Secondary Controls
            html.Div([
                html.Div([
                    html.Label("Visualization Type", style={
                        'fontWeight': '500',
                        'color': '#d1d5db',
                        'display': 'block',
                        'marginBottom': '12px',
                        'fontSize': '13px',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.5px'
                    }),
                    dcc.RadioItems(
                        id='regime-analysis-mode',
                        options=[
                            {'label': ' Binned Analysis', 'value': 'bins'},
                            {'label': ' Continuous Analysis', 'value': 'continuous'}
                        ],
                        value='bins',
                        style={'marginBottom': '16px'},
                        labelStyle={
                            'display': 'inline-block', 
                            'marginRight': '24px',
                            'color': '#e5e7eb',
                            'fontSize': '14px',
                            'fontWeight': '400'
                        }
                    )
                ], style={'width': '35%', 'display': 'inline-block', 'marginRight': '5%'}),
                
                html.Div([
                    html.Label("Bin Configuration", style={
                        'fontWeight': '500',
                        'color': '#d1d5db',
                        'display': 'block',
                        'marginBottom': '12px',
                        'fontSize': '13px',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.5px'
                    }),
                    dcc.Slider(
                        id='regime-bins-slider',
                        min=5,
                        max=20,
                        step=1,
                        value=10,
                        marks={
                            i: {'label': str(i), 'style': {'color': '#9ca3af', 'fontSize': '10px'}} 
                            for i in range(5, 21, 5)
                        },
                        tooltip={"placement": "bottom", "always_visible": True}
                    )
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '5%'}),
                
                html.Div([
                    html.Button("ANALYZE", id='regime-analyze-btn', 
                              style={
                                  'background': 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
                                  'color': '#ffffff',
                                  'border': 'none',
                                  'padding': '14px 28px',
                                  'borderRadius': '6px',
                                  'fontSize': '13px',
                                  'fontWeight': '600',
                                  'cursor': 'pointer',
                                  'width': '100%',
                                  'marginTop': '16px',
                                  'letterSpacing': '1px',
                                  'textTransform': 'uppercase',
                                  'transition': 'all 0.2s ease',
                                  'boxShadow': '0 4px 12px rgba(99, 102, 241, 0.3)'
                              })
                ], style={'width': '25%', 'display': 'inline-block', 'verticalAlign': 'top'})
            ])
        ], style={
            'background': '#1f2937',
            'padding': '28px',
            'borderRadius': '8px',
            'margin': '24px 0',
            'border': '1px solid #374151',
            'boxShadow': '0 4px 16px rgba(0, 0, 0, 0.1)'
        }),

        # Performance Summary Card
        html.Div(id='regime-summary-card', children=[], style={
            'margin': '24px 0'
        }),

        # Analysis Results - FUTURISTIC DARK MODE
        html.Div([
            html.H3("Analysis Results", style={
                'color': '#f9fafb',
                'fontSize': '16px',
                'fontWeight': '500',
                'margin': '0 0 20px 0',
                'textTransform': 'uppercase',
                'letterSpacing': '1px'
            }),
            html.Div(id='regime-analysis-results', children=[
                html.Div([
                    html.Div("Configure parameters and execute analysis to view results", style={
                        'textAlign': 'center',
                        'color': '#9ca3af',
                        'fontSize': '14px',
                        'fontWeight': '400',
                        'marginBottom': '8px'
                    }),
                    html.Div("Select your analysis parameters above and click ANALYZE", style={
                        'textAlign': 'center',
                        'color': '#6b7280',
                        'fontSize': '12px',
                        'fontWeight': '400'
                    })
                ], style={
                    'padding': '48px 32px',
                    'background': '#111827',
                    'borderRadius': '8px',
                    'border': '2px dashed #374151'
                })
            ])
        ], style={'margin': '24px 0'})

    ], style={
        'padding': '0',
        'maxWidth': '1400px',
        'margin': '0 auto',
        'background': '#0f172a',
        'minHeight': '100vh',
        'fontFamily': '"Inter", "Segoe UI", sans-serif'
    })

def register_regime_callbacks(app):
    # This function is no longer needed - callbacks are registered in callbacks/regime_analyzer.py
    pass

def create_summary_card(summary: dict, feature: str, return_type: str):
    """Create performance summary card with DARK THEME."""
    if not summary:
        return html.Div()
        
    correlation = summary.get('correlation', 0)
    total_obs = summary.get('total_observations', 0) or summary.get('total_trades', 0)
    quartile_perf = summary.get('quartile_performance', {})
    
    return html.Div([
        html.H4(f"Performance Summary: {feature} vs {return_type}", style={
            'color': '#f9fafb',
            'fontSize': '16px',
            'fontWeight': '500',
            'margin': '0 0 20px 0',
            'textTransform': 'uppercase',
            'letterSpacing': '1px'
        }),
        
        html.Div([
            html.Div([
                html.H5("Correlation", style={'margin': '0 0 8px 0', 'color': '#d1d5db', 'fontSize': '12px', 'fontWeight': '500', 'textTransform': 'uppercase'}),
                html.P(f"{correlation:.4f}", style={
                    'fontSize': '24px',
                    'fontWeight': '300',
                    'margin': '0',
                    'color': '#10b981' if correlation > 0 else '#ef4444'
                })
            ], style={'textAlign': 'center', 'flex': '1', 'padding': '16px', 'background': '#1f2937', 'borderRadius': '6px', 'margin': '0 8px'}),
            
            html.Div([
                html.H5("Observations", style={'margin': '0 0 8px 0', 'color': '#d1d5db', 'fontSize': '12px', 'fontWeight': '500', 'textTransform': 'uppercase'}),
                html.P(f"{total_obs:,}", style={
                    'fontSize': '24px',
                    'fontWeight': '300',
                    'margin': '0',
                    'color': '#f9fafb'
                })
            ], style={'textAlign': 'center', 'flex': '1', 'padding': '16px', 'background': '#1f2937', 'borderRadius': '6px', 'margin': '0 8px'}),
            
            html.Div([
                html.H5("Quartile Performance", style={'margin': '0 0 12px 0', 'color': '#d1d5db', 'fontSize': '12px', 'fontWeight': '500', 'textTransform': 'uppercase'}),
                html.Div([
                    html.Div(
                        f"{k}: {v:.4f}" if isinstance(v, (int, float)) else f"{k}: {v}", 
                        style={
                            'padding': '6px 12px',
                            'margin': '2px',
                            'background': '#374151',
                            'borderRadius': '4px',
                            'fontSize': '11px',
                            'color': '#e5e7eb',
                            'fontFamily': 'monospace'
                        }
                    ) for k, v in quartile_perf.items()
                ])
            ], style={'flex': '2', 'padding': '16px', 'background': '#1f2937', 'borderRadius': '6px', 'margin': '0 8px'})
        ], style={
            'display': 'flex',
            'gap': '0px',
            'alignItems': 'flex-start'
        })
    ], style={
        'background': '#111827',
        'padding': '24px',
        'borderRadius': '8px',
        'border': '1px solid #374151',
        'margin': '24px 0',
        'boxShadow': '0 4px 16px rgba(0, 0, 0, 0.1)'
    })

def create_bin_info_table(bin_analysis: dict, feature: str):
    """Create bin information table with DARK THEME."""
    if not bin_analysis or 'bin_ranges' not in bin_analysis or 'bin_stats' not in bin_analysis:
        return html.Div()
    
    bin_ranges = bin_analysis['bin_ranges']
    bin_stats = bin_analysis['bin_stats']
    
    # Create table rows
    table_rows = []
    
    # Header - DARK THEME
    table_rows.append(html.Tr([
        html.Th("Bin", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Range", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Count", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Avg Return", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Win Rate", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Sharpe", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'})
    ]))
    
    # Data rows - DARK THEME
    for bin_range in bin_ranges:
        bin_id = bin_range['bin_id']
        range_label = bin_range['range_label']
        
        if bin_id in bin_stats.index:
            stats = bin_stats.loc[bin_id]
            count = int(stats['count'])
            avg_return = stats['return_mean']
            win_rate = stats['win_rate']
            sharpe = stats['sharpe']
            
            # Color coding based on performance
            return_color = '#10b981' if avg_return > 0 else '#ef4444'
            
            table_rows.append(html.Tr([
                html.Td(f"{bin_id}", style={'padding': '10px', 'fontWeight': '500', 'color': '#f9fafb', 'background': '#1f2937'}),
                html.Td(range_label, style={'padding': '10px', 'fontFamily': 'monospace', 'fontSize': '11px', 'color': '#d1d5db', 'background': '#1f2937'}),
                html.Td(f"{count:,}", style={'padding': '10px', 'textAlign': 'right', 'color': '#e5e7eb', 'background': '#1f2937'}),
                html.Td(f"{avg_return:.6f}", style={
                    'padding': '10px', 
                    'textAlign': 'right', 
                    'color': return_color,
                    'fontWeight': '500',
                    'fontFamily': 'monospace',
                    'background': '#1f2937'
                }),
                html.Td(f"{win_rate:.2%}", style={'padding': '10px', 'textAlign': 'right', 'color': '#e5e7eb', 'fontFamily': 'monospace', 'background': '#1f2937'}),
                html.Td(f"{sharpe:.4f}", style={'padding': '10px', 'textAlign': 'right', 'color': '#e5e7eb', 'fontFamily': 'monospace', 'background': '#1f2937'})
            ]))
        else:
            # No data in this bin - DARK THEME
            table_rows.append(html.Tr([
                html.Td(f"{bin_id}", style={'padding': '10px', 'fontWeight': '500', 'color': '#6b7280', 'background': '#1f2937'}),
                html.Td(range_label, style={'padding': '10px', 'fontFamily': 'monospace', 'fontSize': '11px', 'color': '#6b7280', 'background': '#1f2937'}),
                html.Td("0", style={'padding': '10px', 'textAlign': 'right', 'color': '#6b7280', 'background': '#1f2937'}),
                html.Td("—", style={'padding': '10px', 'textAlign': 'right', 'color': '#6b7280', 'background': '#1f2937'}),
                html.Td("—", style={'padding': '10px', 'textAlign': 'right', 'color': '#6b7280', 'background': '#1f2937'}),
                html.Td("—", style={'padding': '10px', 'textAlign': 'right', 'color': '#6b7280', 'background': '#1f2937'})
            ]))
    
    return html.Div([
        html.H4(f"Detailed Bin Analysis: {feature}", style={
            'color': '#f9fafb',
            'fontSize': '16px',
            'fontWeight': '500',
            'margin': '0 0 16px 0',
            'textTransform': 'uppercase',
            'letterSpacing': '1px'
        }),
        html.Table(table_rows, style={
            'width': '100%',
            'borderCollapse': 'collapse',
            'border': '1px solid #374151',
            'borderRadius': '8px',
            'overflow': 'hidden'
        })
    ], style={
        'background': '#111827',
        'padding': '24px',
        'borderRadius': '8px',
        'border': '1px solid #374151',
        'margin': '24px 0',
        'boxShadow': '0 4px 16px rgba(0, 0, 0, 0.1)'
    })
