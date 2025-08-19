from dash import Input, Output, State, callback_context, html
from dash.exceptions import PreventUpdate
from pathlib import Path

# Import both services
from core.visualizing.dashboard.regime_analyzer.ui import build_regime_layout
from core.visualizing.dashboard.regime_analyzer.service import RegimeService
from core.visualizing.dashboard.regime_analyzer.trade_entry_analyzer import TradeEntryAnalyzer

# Create service instances at module level
_regime_service = None
_trade_entry_analyzer = None

def register_regime_analyzer_callbacks(app, repo):
    """Register all regime analyzer callbacks including both equity and trade entry analysis."""
    global _regime_service, _trade_entry_analyzer
    
    # Panel toggle callback
    @app.callback(
        Output("regime-analyzer-panel", "style"),
        Output("regime-analyzer-content", "children"),
        Input("regime-analyzer-open-btn", "n_clicks"),
        Input("regime-analyzer-close-btn", "n_clicks"),
        State("regime-analyzer-panel", "style"),
        State("selected-run-store", "data"),
        prevent_initial_call=True
    )
    def toggle_regime_panel(open_clicks, close_clicks, current_style, selected_run_id):
        global _regime_service, _trade_entry_analyzer
        print(f"[REGIME] toggle_regime_panel called: open={open_clicks}, close={close_clicks}")
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        print(f"[REGIME] Trigger: {trigger}")
        style = dict(current_style or {})
        if trigger == "regime-analyzer-close-btn":
            style.update({'display': 'none'})
            return style, None

        if trigger == "regime-analyzer-open-btn":
            try:
                runs_df = repo.load_validated_runs()
                print(f"[REGIME] Loaded runs_df: {len(runs_df) if runs_df is not None else 'None'}")
            except Exception as e:
                print(f"[REGIME] Error loading runs_df: {e}")
                runs_df = None

            # Best-effort: determine results root from repo attributes or fallback to project layout
            results_root = None
            for attr in ('results_dir', 'results_root', 'base_dir', 'root', 'results_path', 'path'):
                if hasattr(repo, attr):
                    try:
                        results_root = Path(getattr(repo, attr))
                        print(f"[REGIME] Found results_root from {attr}: {results_root}")
                        break
                    except Exception:
                        continue
            if results_root is None:
                # fallback (same logic as layout.py)
                results_root = Path(__file__).resolve().parents[3] / "data" / "DATA_STORAGE" / "results"
                print(f"[REGIME] Using fallback results_root: {results_root}")

            # Initialize both services
            base_dir = results_root.parent.parent.parent if results_root else Path(".")
            _regime_service = RegimeService(base_dir)
            _trade_entry_analyzer = TradeEntryAnalyzer(results_root)  # FIX: Initialize trade entry analyzer
            print(f"[REGIME] Created service with base_dir: {base_dir}")

            # Determine run_id to inspect: prefer selected_run_id store, otherwise first validated run
            run_id_to_use = None
            if selected_run_id:
                try:
                    if isinstance(selected_run_id, (list, tuple)) and len(selected_run_id) > 0:
                        run_id_to_use = str(selected_run_id[0])
                    else:
                        run_id_to_use = str(selected_run_id)
                    print(f"[REGIME] Using selected_run_id: {run_id_to_use}")
                except Exception:
                    run_id_to_use = str(selected_run_id)
            elif runs_df is not None and not runs_df.empty:
                candidate = runs_df.iloc[0]
                run_id_to_use = str(candidate.get('run_id') or candidate.get('run_index') or "")
                print(f"[REGIME] Using first run from df: {run_id_to_use}")

            try:
                print(f"[REGIME] Building layout with run: {run_id_to_use}")
                layout = build_regime_layout(runs_df, results_root=results_root, preferred_run=run_id_to_use)
                print(f"[REGIME] Layout built successfully")
            except Exception as e:
                print(f"[REGIME] Error building layout: {e}")
                layout = html.Div(f"Failed to build layout: {e}", style={'color': '#f87171'})

            style.update({'display': 'block'})
            return style, layout

        raise PreventUpdate
    
    # Feature update callback - now handles both modes
    @app.callback(
        Output('regime-feature-selector', 'options'),
        Output('regime-feature-selector', 'value'),
        Input('regime-run-selector', 'value'),
        Input('regime-data-mode', 'value'),  # FIX: Add data mode as input
        prevent_initial_call=True
    )
    def update_features(selected_run, data_mode):
        global _regime_service, _trade_entry_analyzer
        
        if not selected_run:
            raise PreventUpdate
            
        if data_mode == 'trade_entry':
            # FIX: Use trade entry analyzer for trade entry mode
            if not _trade_entry_analyzer:
                return [], None
                
            # Load trade data
            trades_loaded = _trade_entry_analyzer.load_trades_data(selected_run)
            indicators_loaded = _trade_entry_analyzer.load_indicators_data(selected_run)
            
            if trades_loaded and indicators_loaded:
                _trade_entry_analyzer.create_trade_feature_data()
                features = _trade_entry_analyzer.get_available_features()
            else:
                features = []
        else:
            # FIX: Use regime service for equity mode
            if not _regime_service:
                return [], None
                
            success = _regime_service.load_data(selected_run)
            if success:
                features = _regime_service.get_feature_names()
            else:
                features = []
        
        options = [{'label': f, 'value': f} for f in features]
        default_value = features[0] if features else None
        
        return options, default_value

    # Main analysis callback - now handles analysis type, modes and forward periods
    @app.callback(
        [Output('regime-summary-card', 'children'),
         Output('regime-analysis-results', 'children')],
        [Input('regime-analyze-btn', 'n_clicks')],
        [State('regime-run-selector', 'value'),
         State('regime-analysis-type', 'value'),  # NEW: Analysis Type
         State('regime-data-mode', 'value'),
         State('regime-feature-selector', 'value'),
         State('regime-return-type', 'value'),
         State('regime-analysis-mode', 'value'),
         State('regime-bins-slider', 'value'),
         State('forward-time-value', 'value'),
         State('forward-time-unit', 'value')],
        prevent_initial_call=True
    )
    def perform_analysis(n_clicks, run_id, analysis_type, data_mode, feature, return_type, analysis_mode, n_bins, time_value, time_unit):
        global _regime_service, _trade_entry_analyzer
        
        if not n_clicks or not all([run_id, feature]) or not data_mode:
            raise PreventUpdate
            
        # Convert time range to periods
        forward_periods = 1  # default
        if return_type == 'forward_return_custom' and time_value and time_unit:
            conversion_map = {
                'minutes': 1,
                'hours': 60,
                'days': 1440,
                'weeks': 10080,
                'periods': 1
            }
            forward_periods = time_value * conversion_map.get(time_unit, 1)
            
        try:
            if data_mode == 'trade_entry':
                # Trade entry analysis doesn't use forward periods or analysis type
                if not _trade_entry_analyzer:
                    error_msg = html.Div("Trade Entry Analyzer not initialized", style={'color': '#dc2626'})
                    return error_msg, error_msg
                
                # Load and merge trade data
                trades_loaded = _trade_entry_analyzer.load_trades_data(run_id)
                indicators_loaded = _trade_entry_analyzer.load_indicators_data(run_id)
                
                if not (trades_loaded and indicators_loaded):
                    error_msg = html.Div("Failed to load trade or indicator data", style={'color': '#dc2626'})
                    return error_msg, error_msg
                
                _trade_entry_analyzer.create_trade_feature_data()
                
                # Generate trade entry analysis
                fig1, fig2 = _trade_entry_analyzer.plot_trade_entry_analysis(feature, analysis_mode, n_bins)
                summary = _trade_entry_analyzer.get_trade_performance_summary(feature)
                
                # Create summary card for trade entry analysis
                from core.visualizing.dashboard.regime_analyzer.ui import create_summary_card
                summary_card_data = {
                    'correlation': summary.get('correlation', 0),
                    'total_observations': summary.get('total_trades', 0),
                    'quartile_performance': summary.get('quartile_performance', {})
                }
                
                # NEW: Include analysis type in title
                analysis_type_label = "📈 Index" if analysis_type == 'index' else "₿ Crypto"
                summary_card = create_summary_card(summary_card_data, f"{feature} ({analysis_type_label})", "Trade PnL")
                
                # Create bin info table for trade entry if bins mode
                bin_info_element = html.Div()
                if analysis_mode == 'bins':
                    bin_analysis = _trade_entry_analyzer.analyze_trade_entry_bins(feature, n_bins)
                    if bin_analysis:
                        bin_info_element = create_trade_entry_bin_table(bin_analysis, f"{feature} ({analysis_type_label})")
                
            else:
                # Use regime service for equity analysis with analysis type and time-based forward periods
                if not _regime_service:
                    error_msg = html.Div("Regime Service not initialized", style={'color': '#dc2626'})
                    return error_msg, error_msg
                
                load_success = _regime_service.load_data(run_id)
                if not load_success:
                    error_msg = html.Div(f"Failed to load data for run: {run_id}", style={'color': '#dc2626'})
                    return error_msg, error_msg
                
                # Pass analysis type to the service for specialized handling
                _regime_service.set_analysis_type(analysis_type)  # NEW: Set analysis type
                
                # Pass calculated forward_periods to analysis functions
                fig1, fig2 = _regime_service.plot_regime_analysis(feature, analysis_mode, n_bins, return_type, forward_periods)
                summary = _regime_service.get_performance_summary(feature, return_type, forward_periods)
                
                # Create summary card with analysis type and time info
                analysis_type_label = "📈 Index" if analysis_type == 'index' else "₿ Crypto"
                time_info = f" ({time_value} {time_unit})" if return_type == 'forward_return_custom' else ""
                display_return_type = f"{return_type}{time_info}"
                
                from core.visualizing.dashboard.regime_analyzer.ui import create_summary_card, create_bin_info_table
                summary_card = create_summary_card(summary, f"{feature} ({analysis_type_label})", display_return_type)
                
                # Create bin info table for equity analysis
                bin_info_element = html.Div()
                if analysis_mode == 'bins':
                    bin_analysis = _regime_service.analyze_regime_bins(feature, n_bins, return_type, forward_periods)
                    bin_info_element = create_bin_info_table(bin_analysis, f"{feature} ({analysis_type_label})")
            
            # Create results layout (same for both modes)
            from dash import dcc
            results = html.Div([
                bin_info_element,
                html.Div([
                    dcc.Graph(figure=fig1, style={'height': '600px'})
                ], style={'width': '100%', 'marginBottom': '20px'}),
                html.Div([
                    dcc.Graph(figure=fig2, style={'height': '500px'})
                ], style={'width': '100%'})
            ])
            
            return summary_card, results
            
        except Exception as e:
            import traceback
            error_msg = html.Div([
                html.H4("⚠️ Analysis Error", style={'color': '#dc2626'}),
                html.P(f"Type: {analysis_type}, Mode: {data_mode}, Error: {str(e)}", style={'color': '#64748b'}),
                html.P(f"Time Range: {time_value} {time_unit} = {forward_periods} periods", style={'color': '#64748b', 'fontSize': '12px'})
            ], style={
                'background': '#fef2f2',
                'border': '1px solid #fecaca',
                'borderRadius': '8px',
                'padding': '20px',
                'margin': '20px 0'
            })
            return error_msg, error_msg

    # FIX: Add callback for forward time preview (ohne 5000 Max-Limit)
    @app.callback(
        Output('forward-time-preview', 'children'),
        [Input('forward-time-value', 'value'),
         Input('forward-time-unit', 'value')],
        prevent_initial_call=False
    )
    def update_time_preview(time_value, time_unit):
        if not time_value or not time_unit:
            return ""
        
        # Convert to periods (assuming 1-minute data)
        conversion_map = {
            'minutes': 1,
            'hours': 60,
            'days': 1440,  # 24 * 60
            'weeks': 10080,  # 7 * 24 * 60
            'periods': 1
        }
        
        periods = time_value * conversion_map.get(time_unit, 1)
        
        # FIX: Entferne die 5000-Limit-Warnung, zeige nur die Konvertierung
        preview_text = f"= {periods:,} data periods"
        if time_unit != 'periods':
            preview_text += f" ({time_value} {time_unit})"
        
        return preview_text

def create_trade_entry_bin_table(bin_analysis: dict, feature: str):
    """Create bin information table specifically for trade entry analysis."""
    if not bin_analysis or 'bin_ranges' not in bin_analysis or 'bin_stats' not in bin_analysis:
        return html.Div()
    
    bin_ranges = bin_analysis['bin_ranges']
    bin_stats = bin_analysis['bin_stats']
    
    print(f"[DEBUG] Trade entry bin_stats columns: {list(bin_stats.columns) if hasattr(bin_stats, 'columns') else 'No columns'}")
    print(f"[DEBUG] Trade entry bin_stats index: {list(bin_stats.index) if hasattr(bin_stats, 'index') else 'No index'}")
    print(f"[DEBUG] Trade entry bin_stats shape: {bin_stats.shape if hasattr(bin_stats, 'shape') else 'No shape'}")
    
    # Create table rows
    table_rows = []
    
    # Header - DARK THEME for trade entry
    table_rows.append(html.Tr([
        html.Th("Bin", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Entry Range", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Trades", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Avg PnL", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Win Rate", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
        html.Th("Total PnL", style={'padding': '12px', 'backgroundColor': '#374151', 'fontWeight': '600', 'color': '#f9fafb', 'fontSize': '12px', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'})
    ]))
    
    # Data rows
    for bin_range in bin_ranges:
        bin_id = bin_range['bin_id']
        range_label = bin_range['range_label']
        
        if bin_id in bin_stats.index:
            stats = bin_stats.loc[bin_id]
            
            # FIX: Use correct column names for trade entry analyzer
            count = int(stats.get('trade_count', 0))  # FIX: was 'count', now 'trade_count'
            avg_pnl = stats.get('avg_pnl', 0)  # FIX: was 'return_mean', now 'avg_pnl'
            win_rate = stats.get('win_rate', 0)  # This one is correct
            total_pnl = stats.get('total_pnl', 0)  # This one is correct
            
            print(f"[DEBUG] Bin {bin_id}: count={count}, avg_pnl={avg_pnl}, win_rate={win_rate}, total_pnl={total_pnl}")
            
            # Color coding based on performance
            pnl_color = '#10b981' if avg_pnl > 0 else '#ef4444'
            
            table_rows.append(html.Tr([
                html.Td(f"{bin_id}", style={'padding': '10px', 'fontWeight': '500', 'color': '#f9fafb', 'background': '#1f2937'}),
                html.Td(range_label, style={'padding': '10px', 'fontFamily': 'monospace', 'fontSize': '11px', 'color': '#d1d5db', 'background': '#1f2937'}),
                html.Td(f"{count:,}", style={'padding': '10px', 'textAlign': 'right', 'color': '#e5e7eb', 'background': '#1f2937'}),
                html.Td(f"{avg_pnl:.2f} USDT", style={
                    'padding': '10px', 
                    'textAlign': 'right', 
                    'color': pnl_color,
                    'fontWeight': '500',
                    'fontFamily': 'monospace',
                    'background': '#1f2937'
                }),
                html.Td(f"{win_rate:.2%}", style={'padding': '10px', 'textAlign': 'right', 'color': '#e5e7eb', 'fontFamily': 'monospace', 'background': '#1f2937'}),
                html.Td(f"{total_pnl:.2f} USDT", style={
                    'padding': '10px', 
                    'textAlign': 'right',
                    'color': pnl_color,
                    'fontFamily': 'monospace',
                    'background': '#1f2937'
                })
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
        html.H4(f"Trade Entry Bin Analysis: {feature}", style={
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
