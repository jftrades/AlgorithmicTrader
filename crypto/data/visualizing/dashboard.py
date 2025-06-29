import dash
from dash import dcc, html, Input, Output, callback_context
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import os

# Einfaches Dashboard
app = dash.Dash(__name__)
app.title = "Simple Trading Dashboard"

# Klasse für das Trading Dashboard
class TradingDashboard:
    def __init__(self):
        self.bars_df = None
        self.trades_df = None
        self.indicators_df = {}
        self.nautilus_result = None
        self.metrics = None
        
        # Pfad zu den gespeicherten CSVs (gleich wie im DataCollector)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = Path(base_dir) / "DATA_STORAGE" / "results"

    def load_data_from_csv(self):
        """Lädt alle CSV-Dateien aus dem DataCollector-Pfad."""
        try:
            # Bars laden
            bars_path = self.data_path / "bars.csv"
            if bars_path.exists():
                self.bars_df = pd.read_csv(bars_path)
                print(f"Bars geladen: {len(self.bars_df)} Einträge")
            
            # Trades laden
            trades_path = self.data_path / "trades.csv"
            if trades_path.exists():
                self.trades_df = pd.read_csv(trades_path)
                print(f"Trades geladen: {len(self.trades_df)} Einträge")
            
            # Indikatoren laden (mit Plot-ID aus dritter Spalte)
            indicators_path = self.data_path / "indicators"
            if indicators_path.exists():
                for csv_file in indicators_path.glob("*.csv"):
                    indicator_name = csv_file.stem
                    indicator_df = pd.read_csv(csv_file)
                    
                    # Prüfe ob dritte Spalte (plot_id) vorhanden ist
                    if len(indicator_df.columns) >= 3:
                        plot_id = indicator_df.iloc[0, 2] if len(indicator_df) > 0 else 1  # Default zu Plot 1
                        indicator_df['plot_id'] = plot_id  # Plot-ID als Spalte hinzufügen
                        print(f"Indikator {indicator_name} geladen: {len(indicator_df)} Einträge, Plot-ID: {plot_id}")
                    else:
                        indicator_df['plot_id'] = 1  # Default zu Plot 1 falls keine Plot-ID
                        print(f"Indikator {indicator_name} geladen: {len(indicator_df)} Einträge, Plot-ID: 1 (default)")
                    
                    self.indicators_df[indicator_name] = indicator_df
                    
        except Exception as e:
            print(f"Fehler beim Laden der CSV-Dateien: {e}")

    def collect_results(self, results):
        """Extrahiert nur USDT-Metriken aus dem Nautilus result[0] Objekt."""
        self.nautilus_result = results

        if results and len(results) > 0:
            result_obj = results[0]
            try:
                # Extrahiere nur USDT-Metriken aus stats_pnls und stats_returns
                usdt_metrics = {}
                if hasattr(result_obj, "stats_pnls") and "USDT" in result_obj.stats_pnls:
                    for key, val in result_obj.stats_pnls["USDT"].items():
                        usdt_metrics[key.replace('_', ' ').title()] = val
                if hasattr(result_obj, "stats_returns"):
                    for key, val in result_obj.stats_returns.items():
                        usdt_metrics[key.replace('_', ' ').title()] = val

                # Füge ggf. weitere relevante Felder hinzu mit Datum-Konvertierung
                if hasattr(result_obj, "run_id"):
                    usdt_metrics["Run ID"] = result_obj.run_id
                if hasattr(result_obj, "backtest_start"):
                    # Konvertiere Nano-Timestamp zu lesbarem Datum
                    start_ts = result_obj.backtest_start
                    if isinstance(start_ts, (int, float)) and start_ts > 1e15:  # Nano-Timestamp
                        start_date = pd.to_datetime(start_ts, unit='ns').strftime('%Y-%m-%d %H:%M:%S UTC')
                        usdt_metrics["Backtest Start"] = start_date
                    else:
                        usdt_metrics["Backtest Start"] = str(start_ts)
                if hasattr(result_obj, "backtest_end"):
                    # Konvertiere Nano-Timestamp zu lesbarem Datum
                    end_ts = result_obj.backtest_end
                    if isinstance(end_ts, (int, float)) and end_ts > 1e15:  # Nano-Timestamp
                        end_date = pd.to_datetime(end_ts, unit='ns').strftime('%Y-%m-%d %H:%M:%S UTC')
                        usdt_metrics["Backtest End"] = end_date
                    else:
                        usdt_metrics["Backtest End"] = str(end_ts)
                if hasattr(result_obj, "elapsed_time"):
                    elapsed = getattr(result_obj, "elapsed_time", None)
                    if elapsed is not None:
                        usdt_metrics["Elapsed Time (s)"] = f"{elapsed:.2f}"
                    else:
                        usdt_metrics["Elapsed Time (s)"] = "N/A"
                if hasattr(result_obj, "iterations"):
                    usdt_metrics["Iterations"] = getattr(result_obj, "iterations", None)
                if hasattr(result_obj, "total_events"):
                    usdt_metrics["Total Events"] = getattr(result_obj, "total_events", None)
                if hasattr(result_obj, "total_orders"):
                    usdt_metrics["Total Orders"] = getattr(result_obj, "total_orders", None)
                if hasattr(result_obj, "total_positions"):
                    usdt_metrics["Total Positions"] = getattr(result_obj, "total_positions", None)

                self.metrics = usdt_metrics
                print("USDT-Metriken extrahiert:", self.metrics)
            except Exception as e:
                print(f"Fehler beim Extrahieren der USDT-Metriken: {e}")
                self.metrics = self._get_fallback_metrics()
        else:
            print("Keine Ergebnisse übergeben")
            self.metrics = self._get_fallback_metrics()

    def _get_fallback_metrics(self):
        """Fallback-Metriken falls Extraktion fehlschlägt."""
        return {
            'Total Return': "N/A",
            'Win Rate': "N/A", 
            'Max Drawdown': "N/A",
            'Sharpe Ratio': "N/A",
            'Total Trades': "N/A",
            'Profit Factor': "N/A"
        }

    def visualize(self, visualize_after_backtest=False):
        """Startet das Dashboard mit den geladenen Daten."""

        if visualize_after_backtest:
            dashboard_app = DashboardApp(
                bars_df=self.bars_df,
                trades_df=self.trades_df,
                indicators_df=self.indicators_df,
                metrics=self.metrics,
                nautilus_result=self.nautilus_result  # <-- Pass result for units
            )
            dashboard_app.run(debug=True, port=8050)

# Dashboard App Klasse
class DashboardApp:
    def __init__(self, title="Simple Trading Dashboard", bars_df=None, trades_df=None, indicators_df=None, metrics=None, nautilus_result=None):
        self.app = dash.Dash(__name__, suppress_callback_exceptions=True)
        self.app.title = title
        self.bars_df = bars_df
        self.trades_df = trades_df
        self.indicators_df = indicators_df or {}
        self.metrics = metrics or {}
        self.nautilus_result = nautilus_result  # <-- Store result for units
        self.selected_trade_index = None  # Für visuelles Feedback bei angeklickten Trades
        self.app.layout = self._create_layout()
        self._register_callbacks()

    def _create_layout(self):
        return html.Div([
            html.H1("Algorithmic Trading Dashboard", style={
                'textAlign': 'center', 
                'color': '#2c3e50', 
                'marginBottom': '30px',
                'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
                'fontWeight': '600',
                'letterSpacing': '-0.025em'
            }),
            
            # Trade Details Panel (oberhalb des Charts als Overlay)
            html.Div([
                html.Div(id='trade-details-panel', children=[
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
                ])
            ], style={
                'backgroundColor': '#f8f9fa',
                'border': '1px solid #dee2e6',
                'borderRadius': '8px',
                'padding': '15px',
                'marginBottom': '20px',
                'maxHeight': '300px',
                'overflowY': 'auto'
            }),

            # Hauptchart für Bars und Trades (volle Breite)
            html.Div([
                html.H3("Price Data & Trading Signals", style={
                    'color': '#34495e', 
                    'marginBottom': '15px',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontWeight': '500'
                }),
                dcc.Graph(id='price-chart', style={'height': '650px'})
            ], style={'margin': '20px 0'}),
            
            # Container für dynamische Indikator-Subplots
            html.Div(id='indicators-container'),
            
            # Performance Metriken (professioneller)
            html.Div([
                html.H3("Performance Metrics", style={
                    'color': '#34495e', 
                    'marginBottom': '15px',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontWeight': '500'
                }),
                html.Div(id='metrics-display', style={
                    'backgroundColor': '#f8f9fa',
                    'border': '1px solid #dee2e6',
                    'borderRadius': '8px',
                    'padding': '20px'
                })
            ], style={'margin': '20px 0'}),
            
            html.Button('Update Dashboard', id='refresh-btn', n_clicks=0,
                        style={
                            'margin': '20px auto',
                            'padding': '12px 24px',
                            'fontSize': '16px',
                            'backgroundColor': '#3498db',
                            'color': 'white',
                            'border': 'none',
                            'borderRadius': '6px',
                            'cursor': 'pointer',
                            'display': 'block',
                            'fontFamily': 'Inter, system-ui, sans-serif',
                            'fontWeight': '500'
                        })
        ], style={
            'padding': '0 20px', 
            'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
        })

    def _register_callbacks(self):
        @self.app.callback(
            [Output('price-chart', 'figure'),
             Output('indicators-container', 'children'),
             Output('metrics-display', 'children'),
             Output('trade-details-panel', 'children')],
            [Input('refresh-btn', 'n_clicks'),
             Input('price-chart', 'clickData')],
            prevent_initial_call=False
        )
        def update_dashboard(refresh_clicks, clickData):
            try:
                # Bestimme welcher Input getriggert wurde
                ctx = dash.callback_context
                if not ctx.triggered:
                    triggered_id = 'refresh-btn'
                else:
                    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
                
                # Basis-Charts und Metriken erstellen
                try:
                    indicators_components = self.create_indicator_subplots()
                except Exception as e:
                    print(f"Fehler bei Indikatoren: {e}")
                    indicators_components = []
                
                try:
                    metrics_table = self.create_metrics_table()
                except Exception as e:
                    print(f"Fehler bei Metriken: {e}")
                    metrics_table = html.Div("Metrics could not be loaded")
                
                # Trade-Details und Chart basierend auf Click-Data
                if triggered_id == 'price-chart' and clickData and self.trades_df is not None and not self.trades_df.empty:
                    try:
                        # Suche nach Trade-Marker mit customdata in allen Points
                        trade_point = None
                        for point in clickData['points']:
                            if 'customdata' in point:
                                trade_point = point
                                break
                        
                        if trade_point is not None:
                            trade_index = trade_point['customdata']
                            if trade_index < len(self.trades_df):
                                # Setze ausgewählten Trade
                                self.selected_trade_index = trade_index
                                trade_data = self.trades_df.iloc[trade_index]
                                trade_details = self.create_trade_details_content(trade_data)
                            else:
                                self.selected_trade_index = None
                                trade_details = self.get_default_trade_details()
                        else:
                            # Klick war nicht auf Trade-Marker - Reset Selection
                            self.selected_trade_index = None
                            trade_details = self.get_default_trade_details_with_message()
                    except Exception as e:
                        print(f"Fehler bei Trade-Details: {e}")
                        self.selected_trade_index = None
                        trade_details = self.get_default_trade_details()
                else:
                    # Refresh oder kein Click-Data
                    self.selected_trade_index = None
                    trade_details = self.get_default_trade_details()
                
                # Chart mit aktuellem Selection-State erstellen
                try:
                    price_fig = self.create_price_chart()
                except Exception as e:
                    print(f"Fehler bei Chart-Erstellung: {e}")
                    # Fallback - leerer Chart
                    price_fig = go.Figure()
                    price_fig.update_layout(title="Chart could not be loaded")
                
                return price_fig, indicators_components, metrics_table, trade_details
            
            except Exception as e:
                print(f"Allgemeiner Callback-Fehler: {e}")
                # Fallback-Rückgabe
                empty_fig = go.Figure()
                empty_fig.update_layout(title="Error loading dashboard")
                return empty_fig, [], html.Div("Error"), self.get_default_trade_details()

        # Dynamische Callbacks für Indikator-Subplots nur wenn Indikatoren vorhanden
        try:
            self._register_indicator_sync_callbacks()
        except Exception as e:
            print(f"Fehler bei Indikator-Callbacks: {e}")
    
    def get_default_trade_details(self):
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
    
    def get_default_trade_details_with_message(self):
        """Trade-Details mit Hinweis-Message."""
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

    def create_price_chart(self):
        """Erstellt Chart für Bars und Trades + Indikatoren mit Plot-ID 0."""
        try:
            fig = go.Figure()
            
            # 1. OHLC Chart falls Bars vorhanden - professionelle Farben (Basis-Layer)
            if self.bars_df is not None and not self.bars_df.empty:
                try:
                    bars = self.bars_df
                    fig.add_trace(
                        go.Candlestick(
                            x=pd.to_datetime(bars['timestamp']),
                            open=bars['open'],
                            high=bars['high'], 
                            low=bars['low'],
                            close=bars['close'],
                            name='OHLC',
                            increasing_line_color='#26a69a',
                            decreasing_line_color='#ef5350',
                            increasing_fillcolor='#26a69a',
                            decreasing_fillcolor='#ef5350',
                            showlegend=True
                        )
                    )
                except Exception as e:
                    print(f"Fehler bei OHLC-Chart: {e}")

            # 2. Indikatoren mit Plot-ID 0 hinzufügen (gleicher Plot wie Bars)
            try:
                indicator_colors = ['rgba(0,0,0,0.4)', 'rgba(64,64,64,0.8)', 'rgba(139,69,19,0.8)', 'rgba(114,9,183,0.8)']
                color_idx = 0
                for name, indicator_df in self.indicators_df.items():
                    try:
                        if not indicator_df.empty and indicator_df.iloc[0]['plot_id'] == 0:
                            line_color = indicator_colors[color_idx % len(indicator_colors)]
                            fig.add_trace(
                                go.Scatter(
                                    x=pd.to_datetime(indicator_df['timestamp']),
                                    y=indicator_df['value'],
                                    mode='lines',
                                    name=f"{name.upper()}",
                                    line=dict(color=line_color, width=2.5),
                                    showlegend=True
                                )
                            )
                            color_idx += 1
                    except Exception as e:
                        print(f"Fehler bei Indikator {name}: {e}")
            except Exception as e:
                print(f"Fehler bei Indikatoren: {e}")
            
            # 3. Trade-Signale falls Trades vorhanden
            if self.trades_df is not None and not self.trades_df.empty:
                try:
                    trades = self.trades_df
                    buy_trades = trades[trades['action'] == 'BUY']
                    if not buy_trades.empty:
                        # Normale BUY Trades
                        normal_buy_trades = buy_trades[~buy_trades.index.isin([self.selected_trade_index] if self.selected_trade_index is not None else [])]
                        if not normal_buy_trades.empty:
                            fig.add_trace(
                                go.Scatter(
                                    x=pd.to_datetime(normal_buy_trades['timestamp']),
                                    y=normal_buy_trades['price_actual'],
                                    mode='markers',
                                    name='BUY Signal',
                                    marker=dict(
                                        symbol='triangle-up', 
                                        size=25,
                                        color='#28a745',
                                        line=dict(color='#ffffff', width=4),
                                        opacity=0.9
                                    ),
                                    customdata=normal_buy_trades.index.tolist(),
                                    hovertemplate='<b>BUY Signal</b><br>Time: %{x}<br>Price: %{y:.2f} USDT<extra></extra>',
                                    showlegend=True
                                )
                            )
                        
                        # Ausgewählter BUY Trade (falls vorhanden)
                        if self.selected_trade_index is not None and self.selected_trade_index in buy_trades.index:
                            selected_trade = buy_trades.loc[[self.selected_trade_index]]
                            fig.add_trace(
                                go.Scatter(
                                    x=pd.to_datetime(selected_trade['timestamp']),
                                    y=selected_trade['price_actual'],
                                    mode='markers',
                                    name='Selected BUY',
                                    marker=dict(
                                        symbol='triangle-up', 
                                        size=25,
                                        color='#28a745',
                                        line=dict(color='#000000', width=4),
                                        opacity=1.0
                                    ),
                                    customdata=[self.selected_trade_index],
                                    hovertemplate='<b>SELECTED BUY Signal</b><br>Time: %{x}<br>Price: %{y:.2f} USDT<extra></extra>',
                                    showlegend=False
                                )
                            )
                            
                    sell_trades = trades[trades['action'] == 'SHORT']
                    if not sell_trades.empty:
                        # Normale SELL Trades
                        normal_sell_trades = sell_trades[~sell_trades.index.isin([self.selected_trade_index] if self.selected_trade_index is not None else [])]
                        if not normal_sell_trades.empty:
                            fig.add_trace(
                                go.Scatter(
                                    x=pd.to_datetime(normal_sell_trades['timestamp']),
                                    y=normal_sell_trades['price_actual'],
                                    mode='markers',
                                    name='SELL Signal',
                                    marker=dict(
                                        symbol='triangle-down', 
                                        size=25,
                                        color='#dc3545',
                                        line=dict(color='#ffffff', width=4),
                                        opacity=0.9
                                    ),
                                    customdata=normal_sell_trades.index.tolist(),
                                    hovertemplate='<b>SELL Signal</b><br>Time: %{x}<br>Price: %{y:.2f} USDT<extra></extra>',
                                    showlegend=True
                                )
                            )
                        
                        # Ausgewählter SELL Trade (falls vorhanden)
                        if self.selected_trade_index is not None and self.selected_trade_index in sell_trades.index:
                            selected_trade = sell_trades.loc[[self.selected_trade_index]]
                            fig.add_trace(
                                go.Scatter(
                                    x=pd.to_datetime(selected_trade['timestamp']),
                                    y=selected_trade['price_actual'],
                                    mode='markers',
                                    name='Selected SELL',
                                    marker=dict(
                                        symbol='triangle-down', 
                                        size=25,
                                        color='#dc3545',
                                        line=dict(color='#000000', width=4),
                                        opacity=1.0
                                    ),
                                    customdata=[self.selected_trade_index],
                                    hovertemplate='<b>SELECTED SELL Signal</b><br>Time: %{x}<br>Price: %{y:.2f} USDT<extra></extra>',
                                    showlegend=False
                                )
                            )
                except Exception as e:
                    print(f"Fehler bei Trade-Signalen: {e}")
            
            # Layout-Update mit einfacheren Einstellungen
            fig.update_layout(
                title="",
                xaxis_title="Time",
                yaxis_title="Price (USDT)",
                template="plotly_white",
                showlegend=True,
                uirevision='price-chart-stable',
                hovermode='closest',
                clickmode='event',
                dragmode='zoom',  # Zoom wieder aktivieren
                xaxis_rangeslider_visible=False  # Range slider deaktivieren
            )
            
            return fig
            
        except Exception as e:
            print(f"Schwerwiegender Fehler bei Chart-Erstellung: {e}")
            # Absoluter Fallback
            fig = go.Figure()
            fig.update_layout(title="Chart Error - Please refresh")
            return fig

    def create_indicator_subplots(self):
        """Erstellt dynamische Subplots basierend auf Plot-IDs."""
        try:
            # Gruppiere Indikatoren nach Plot-ID (außer 0)
            plot_groups = {}
            for name, indicator_df in self.indicators_df.items():
                if not indicator_df.empty:
                    plot_id = indicator_df.iloc[0]['plot_id']
                    if plot_id > 0:  # Plot-ID 0 ist im Hauptchart
                        if plot_id not in plot_groups:
                            plot_groups[plot_id] = []
                        plot_groups[plot_id].append((name, indicator_df))
            
            # Wenn keine Indikatoren > Plot-ID 0, return leer
            if not plot_groups:
                return []
            
            # Erstelle Subplot-Components
            subplot_components = []
            for plot_id in sorted(plot_groups.keys()):
                indicators_in_plot = plot_groups[plot_id]
                
                # Konvertiere plot_id zu Integer-String für gültige Dash-ID
                plot_id_str = str(int(plot_id)) if isinstance(plot_id, float) else str(plot_id)
                
                # Titel für den Subplot
                indicator_names = [name for name, _ in indicators_in_plot]
                
                subplot_components.append(
                    html.Div([
                        html.H4(f"Indicators: {', '.join(indicator_names)}", style={
                            'color': '#34495e', 
                            'marginBottom': '10px',
                            'fontFamily': 'Inter, system-ui, sans-serif',
                            'fontWeight': '500'
                        }),
                        dcc.Graph(
                            id=f'indicators-plot-{plot_id_str}',
                            figure=self.create_subplot_figure(indicators_in_plot),
                            style={'height': '350px'}
                        )
                    ], style={'margin': '20px 0'})
                )
            
            return subplot_components
        except Exception as e:
            print(f"Fehler bei Indikator-Subplots: {e}")
            return []

    def create_subplot_figure(self, indicators_list):
        """Erstellt Figure für einen Indikator-Subplot."""
        fig = go.Figure()
        
        colors = ['#3498db', '#e74c3c', '#f39c12', '#9b59b6', '#1abc9c']
        for i, (name, indicator_df) in enumerate(indicators_list):
            fig.add_trace(
                go.Scatter(
                    x=pd.to_datetime(indicator_df['timestamp']),
                    y=indicator_df['value'],
                    mode='lines',  # Keine Marker!
                    name=name,
                    line=dict(color=colors[i % len(colors)], width=2),
                    hovertemplate='<b>%{fullData.name}</b><br>' +
                                'Zeit: %{x|%Y-%m-%d %H:%M:%S}<br>' +
                                'Wert: %{y:.4f}<br>' +
                                '<extra></extra>',
                    showlegend=True,
                    hoverlabel=dict(
                        bgcolor="rgba(255,255,255,0.95)",
                        bordercolor="#666",
                        font=dict(size=12, color="#222", family='Inter, system-ui, sans-serif')
                    )
                )
            )
        
        fig.update_layout(
            title="",
            xaxis_title="Time",
            yaxis_title="Value",
            template="plotly_white",
            showlegend=True,
            legend=dict(
                x=0, 
                y=1, 
                bgcolor='rgba(255,255,255,0.9)',
                font=dict(family='Inter, system-ui, sans-serif', size=11)
            ),
            uirevision=f'indicators-subplot',
            font=dict(family='Inter, system-ui, sans-serif', size=11),
            hovermode='x unified',  # Unified hover für alle Linien gleichzeitig
            margin=dict(t=30, b=60, l=60, r=20),  # Gleiche Margins wie Hauptchart
            # Crosshair-Linien auch für Subplots
            xaxis=dict(
                showspikes=True,
                spikecolor="#333333",
                spikethickness=2,
                spikedash="dot",
                spikemode="across+toaxis"
            ),
            yaxis=dict(
                showspikes=False  # Kein horizontaler Crosshair in Indikator-Charts
            )
        )
        
        return fig

    def _register_indicator_sync_callbacks(self):
        """Registriert Synchronisation für alle Indikator-Subplots."""
        try:
            # Ermittle alle Plot-IDs > 0 und konvertiere zu Integer
            plot_ids = set()
            for name, indicator_df in self.indicators_df.items():
                if not indicator_df.empty:
                    plot_id = indicator_df.iloc[0]['plot_id']
                    if plot_id > 0:
                        # Konvertiere zu Integer für konsistente Behandlung
                        plot_id_int = int(plot_id) if isinstance(plot_id, float) else plot_id
                        plot_ids.add(plot_id_int)
            
            # Wenn keine Indikator-Subplots, return
            if not plot_ids:
                return
            
            # Erstelle Sync-Callbacks für jeden Subplot
            for plot_id in plot_ids:
                # Konvertiere plot_id zu String für gültige Dash-ID
                plot_id_str = str(plot_id)
                
                @self.app.callback(
                    Output(f'indicators-plot-{plot_id_str}', 'figure', allow_duplicate=True),
                    [Input('price-chart', 'relayoutData')],
                    prevent_initial_call=True
                )
                def sync_subplot_x_axis(relayout_data, current_plot_id=plot_id):
                    try:
                        if relayout_data and ('xaxis.range[0]' in relayout_data and 'xaxis.range[1]' in relayout_data):
                            x_range = [relayout_data['xaxis.range[0]'], relayout_data['xaxis.range[1]']]
                            
                            # Finde Indikatoren für diese Plot-ID
                            indicators_for_plot = []
                            for name, indicator_df in self.indicators_df.items():
                                if not indicator_df.empty and int(indicator_df.iloc[0]['plot_id']) == current_plot_id:
                                    indicators_for_plot.append((name, indicator_df))
                            
                            # Erstelle neuen Chart mit synchronisierter X-Achse
                            fig = self.create_subplot_figure(indicators_for_plot)
                            fig.update_layout(xaxis_range=x_range)
                            
                            return fig
                        
                        # Fallback: aktuellen Chart zurückgeben
                        indicators_for_plot = []
                        for name, indicator_df in self.indicators_df.items():
                            if not indicator_df.empty and int(indicator_df.iloc[0]['plot_id']) == current_plot_id:
                                indicators_for_plot.append((name, indicator_df))
                        return self.create_subplot_figure(indicators_for_plot)
                    
                    except Exception as e:
                        print(f"Fehler bei Subplot-Sync für Plot-ID {current_plot_id}: {e}")
                        # Fallback - leerer Chart
                        return go.Figure()
        
        except Exception as e:
            print(f"Fehler bei Indikator-Sync-Callbacks: {e}")

    def create_metrics_table(self):
        """Erstellt professionelle Metriken-Tabelle mit Einheiten."""
        if not self.metrics:
            return html.Div("No metrics available", style={
                'textAlign': 'center', 
                'color': '#6c757d',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'padding': '20px'
            })
        
        # Einheiten aus result extrahieren, falls vorhanden
        units = {}
        if self.nautilus_result and len(self.nautilus_result) > 0:
            result_obj = self.nautilus_result[0]
            # Mapping für spezifische Metriken basierend auf ihrem Namen
            # PnL-Metriken in USDT
            if hasattr(result_obj, 'stats_pnls') and 'USDT' in result_obj.stats_pnls:
                for key in result_obj.stats_pnls['USDT'].keys():
                    metric_name = key.replace('_', ' ').title()
                    if 'pnl' in key.lower() and 'pnl%' not in key.lower():
                        units[metric_name] = 'USDT'
                    elif 'pnl%' in key.lower():
                        units[metric_name] = '%'
            
            # Return-Statistiken und Ratios in Prozent
            if hasattr(result_obj, 'stats_returns'):
                for key in result_obj.stats_returns.keys():
                    metric_name = key.replace('_', ' ').title()
                    # Alle Return-Metriken sind Prozentsätze, außer spezifische Ausnahmen
                    if any(term in key.lower() for term in ['volatility', 'average', 'sharpe', 'sortino']):
                        units[metric_name] = '%'
            
            # Spezielle Behandlung für bekannte Metriken
            special_units = {
                'Win Rate': '',  # Win Rate ist bereits ein Dezimalwert (0.625 = 62.5%)
                'Profit Factor': '',  # Profit Factor ist ein Verhältnis 
                'Risk Return Ratio': '',  # Ist ein Verhältnis
                'Total Positions': '',  # Anzahl, keine Einheit
                'Total Orders': '',  # Anzahl, keine Einheit
                'Total Events': '',  # Anzahl, keine Einheit
                'Iterations': '',  # Anzahl, keine Einheit
                'Elapsed Time (s)': 'time',  # Spezielle Behandlung für Zeit
                'Max Winner': 'USDT',  # Gewinn in USDT
                'Avg Winner': 'USDT',  # Gewinn in USDT
                'Min Winner': 'USDT',  # Gewinn in USDT
                'Max Loser': 'USDT',   # Verlust in USDT
                'Avg Loser': 'USDT',   # Verlust in USDT
                'Min Loser': 'USDT',   # Verlust in USDT
                'Expectancy': 'USDT',  # Erwarteter Gewinn in USDT
            }
            units.update(special_units)
        
        # Organisiere Metriken in Kategorien
        performance_metrics = {}
        trade_metrics = {}
        general_info = {}
        
        for key, value in self.metrics.items():
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
            
            # Spezielle Formatierung für verschiedene Metriken
            if key == 'Win Rate':
                # Win Rate von Dezimal zu Prozent umwandeln (0.625 -> 62.5%)
                try:
                    formatted_value = f"{float(value)*100:.1f}%"
                except Exception:
                    formatted_value = f"{value}"
            elif key == 'Elapsed Time (s)':
                # Zeit von Sekunden in lesbares Format umwandeln
                try:
                    seconds = float(value)
                    if seconds < 60:
                        formatted_value = f"{seconds:.1f}s"
                    elif seconds < 3600:
                        minutes = seconds / 60
                        formatted_value = f"{minutes:.1f}m"
                    elif seconds < 86400:
                        hours = seconds / 3600
                        formatted_value = f"{hours:.1f}h"
                    else:
                        days = seconds / 86400
                        remaining_hours = (seconds % 86400) / 3600
                        if remaining_hours >= 1:
                            formatted_value = f"{int(days)}d {int(remaining_hours)}h"
                        else:
                            formatted_value = f"{int(days)}d"
                except Exception:
                    formatted_value = f"{value}"
            elif key in ['Profit Factor', 'Risk Return Ratio']:
                # Ratios als Dezimalwerte anzeigen
                try:
                    formatted_value = f"{float(value):.2f}"
                except Exception:
                    formatted_value = f"{value}"
            elif 'Ratio' in key or 'Volatility' in key or 'Average' in key and einheit == '%':
                # Andere Prozent-Metriken
                try:
                    if float(value) < 1:  # Wenn Wert < 1, dann zu Prozent umwandeln
                        formatted_value = f"{float(value)*100:.2f}%"
                    else:  # Wenn Wert >= 1, dann bereits als Prozent interpretieren
                        formatted_value = f"{float(value):.2f}%"
                except Exception:
                    formatted_value = f"{value}%"
            elif einheit:
                # Andere Metriken mit Einheiten
                try:
                    formatted_value = f"{float(value):.2f} {einheit}"
                except Exception:
                    formatted_value = f"{value} {einheit}"
            
            return html.Tr([
                html.Td(key, style={
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
        
        def create_section(title, metrics_dict, bg_color):
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
            create_section("Performance", performance_metrics, '#f8f9fa'),
            create_section("Trading", trade_metrics, '#f8f9fa'),
            create_section("General", general_info, '#f8f9fa')
        ])

    def create_trade_details_content(self, trade_data):
        """Erstellt den Inhalt für das Trade-Details Panel (kompakt für oberhalb des Charts)."""
        
        def format_value(key, value):
            """Formatiert Werte basierend auf dem Feldtyp."""
            if pd.isna(value) or value is None:
                return "N/A"
            
            key_lower = key.lower()
            
            # Timestamp-Felder
            if 'timestamp' in key_lower:
                try:
                    if isinstance(value, (int, float)) and value > 1e15:
                        return pd.to_datetime(value, unit='ns').strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        return pd.to_datetime(value).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(value)
            
            # Preis-Felder
            elif any(term in key_lower for term in ['price', 'sl', 'tp']):
                try:
                    return f"{float(value):.4f}"
                except:
                    return str(value)
            
            # Gebühren-Felder  
            elif 'fee' in key_lower:
                try:
                    return f"{float(value):.6f}"
                except:
                    return str(value)
            
            # Größe/Menge
            elif 'size' in key_lower or 'quantity' in key_lower:
                try:
                    return f"{float(value):.6f}"
                except:
                    return str(value)
            
            # Boolean-ähnliche Werte
            elif key_lower in ['type', 'action']:
                return str(value).upper()
            
            # Default
            else:
                return str(value)
        
        # Action-basierte Farbe
        action = str(trade_data.get('action', '')).upper()
        action_color = '#28a745' if action == 'BUY' else '#dc3545'
        
        # Kompakte horizontale Darstellung für wichtigste Felder
        key_fields = ['timestamp', 'action', 'price_actual', 'tradesize', 'sl', 'tp', 'fee']
        
        main_info = []
        for field in key_fields:
            if field in trade_data and not pd.isna(trade_data[field]):
                label = {
                    'timestamp': 'Time',
                    'action': 'Action', 
                    'price_actual': 'Price',
                    'tradesize': 'Size',
                    'sl': 'SL',
                    'tp': 'TP',
                    'fee': 'Fee'
                }.get(field, field)
                
                value = format_value(field, trade_data[field])
                main_info.append(f"{label}: {value}")
        
        # Erstelle kompakte horizontale Anzeige
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
                        'color': '#495057',
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

    def run(self, **kwargs):
        self.app.run(**kwargs)

if __name__ == "__main__":
    dashboard = DashboardApp()
    dashboard.run(debug=True, port=8050)

