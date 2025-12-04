import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import os
from dash import dash_table
from dash import dcc

# Einfaches Dashboard
app = dash.Dash(__name__)
app.title = "Simple Trading Dashboard"

# Klasse für das Trading Dashboard
class TradingDashboard:
    def __init__(self, data_path=None):
        self.bars_df = None
        self.trades_df = None
        self.indicators_df = {}
        self.nautilus_result = None
        self.metrics = None
        self.all_results_df = None
        
        # Pfad zu den gespeicherten CSVs (gleich wie im DataCollector)
        if data_path is not None:
            self.data_path = Path(data_path)
        else:
            base_dir = Path(__file__).resolve().parents[2]
            self.data_path = base_dir / "data" / "DATA_STORAGE" / "results"
        
        self.collectors_data = {}
        self.selected_collector = None

    def load_data_from_csv(self):
        """Lädt Collector-Struktur aus run-Verzeichnis:
        runX/
          <collector_a>/(bars-*.csv,trades.csv,indicators/*.csv)
          <collector_b>/
          general/indicators/...
        """
        try:
            # Erkennen ob wir direkt in einem run-Verzeichnis sind (enthält run_config.yaml)
            run_config = self.data_path / "run_config.yaml"
            root = self.data_path if run_config.exists() else self.data_path
            self.collectors_data = {}
            for sub in root.iterdir():
                if not sub.is_dir():
                    continue
                name = sub.name
                if name.startswith("run"):  # nur echte Collector-Folder
                    continue
                collector = self._load_collector_data(sub)
                if collector:
                    self.collectors_data[name] = collector
                    print(f"Collector geladen: {name}")
            if not self.collectors_data:
                print("Keine Collector-Daten gefunden.")
            else:
                self.selected_collector = list(self.collectors_data.keys())[0]
                self._set_active_collector_data()
                print(f"Standard-Collector gesetzt: {self.selected_collector}")
            # all_backtest_results.csv (eine Ebene höher)
            abr = self.data_path.parent / "all_backtest_results.csv"
            if abr.exists():
                try:
                    self.all_results_df = pd.read_csv(abr)
                except Exception as e:
                    print(f"all_backtest_results.csv Ladefehler: {e}")
        except Exception as e:
            print(f"Fehler beim Laden der neuen Struktur: {e}")

    def _load_collector_data(self, folder: Path):
        """Lädt einen einzelnen Collector (bars-*.csv, trades.csv, indicators/*.csv)."""
        try:
            data = {"bars_df": None, "trades_df": None, "indicators_df": {}}
            # Bars (alle zusammenführen; wähle kürzestes Intervall für Hauptchart)
            bar_files = list(folder.glob("bars-*.csv"))
            bars_list = []
            for f in bar_files:
                try:
                    df = pd.read_csv(f)
                    if not df.empty and "timestamp" in df.columns:
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns")
                        df = df.sort_values("timestamp").reset_index(drop=True)
                        df["timeframe"] = f.stem.replace("bars-", "")
                        bars_list.append(df)
                except Exception as e:
                    print(f"Bars-Datei Fehler {f}: {e}")
            if bars_list:
                # Für Hauptchart kürzestes Intervall wählen (heuristisch nach Sekunden)
                def _tf_rank(tf):
                    # Beispiele: 5M, 1h, 15M, 1D
                    import re
                    m = re.match(r"(\d+)([smMhHdD])", tf)
                    if not m:
                        return 10**9
                    val = int(m.group(1))
                    unit = m.group(2).lower()
                    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 10**6)
                    return val * mult
                best = sorted(bars_list, key=lambda d: _tf_rank(d["timeframe"].iloc[0]))[0]
                data["bars_df"] = best
            # Trades
            trades_path = folder / "trades.csv"
            if trades_path.exists():
                try:
                    tdf = pd.read_csv(trades_path)
                    if not tdf.empty and "timestamp" in tdf.columns:
                        for c in ["timestamp", "closed_timestamp"]:
                            if c in tdf.columns:
                                tdf[c] = pd.to_datetime(tdf[c], unit="ns", errors="ignore")
                        data["trades_df"] = tdf
                except Exception as e:
                    print(f"Trades Fehler {trades_path}: {e}")
            # Indicators
            ind_dir = folder / "indicators"
            if ind_dir.exists():
                for ind_file in ind_dir.glob("*.csv"):
                    try:
                        idf = pd.read_csv(ind_file)
                        if not idf.empty and "timestamp" in idf.columns:
                            idf["timestamp"] = pd.to_datetime(idf["timestamp"], unit="ns")
                            if "plot_id" not in idf.columns:
                                # Heuristik: Equity etc. in separatem Plot
                                base = ind_file.stem.lower()
                                pid = 0
                                if any(k in base for k in ["equity", "position", "unrealized", "realized", "total_"]):
                                    pid = 2
                                elif "rsi" in base:
                                    pid = 1
                                idf["plot_id"] = pid
                            data["indicators_df"][ind_file.stem] = idf
                    except Exception as e:
                        print(f"Indicator Fehler {ind_file}: {e}")
            if any([data["bars_df"] is not None, data["trades_df"] is not None, data["indicators_df"]]):
                return data
            return None
        except Exception as e:
            print(f"Collector Ladefehler {folder}: {e}")
            return None

    def _set_active_collector_data(self):
        if self.selected_collector in self.collectors_data:
            c = self.collectors_data[self.selected_collector]
            self.bars_df = c["bars_df"]
            self.trades_df = c["trades_df"]
            self.indicators_df = c["indicators_df"]

    def set_collector(self, name):
        if name in self.collectors_data:
            self.selected_collector = name
            self._set_active_collector_data()
            return True
        return False

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
                nautilus_result=self.nautilus_result,  # <-- Pass result for units
                collectors_data=self.collectors_data,
                selected_collector=self.selected_collector
            )
            dashboard_app.run(debug=True, port=8050)

# Dashboard App Klasse
class DashboardApp:
    def __init__(self, title="Simple Trading Dashboard", bars_df=None, trades_df=None, indicators_df=None, metrics=None, nautilus_result=None, collectors_data=None, selected_collector=None):
        self.app = dash.Dash(__name__, suppress_callback_exceptions=True)
        self.app.title = title
        self.bars_df = bars_df
        self.trades_df = trades_df
        self.indicators_df = indicators_df or {}
        self.metrics = metrics or {}
        self.nautilus_result = nautilus_result  # <-- Store result for units
        self.selected_trade_index = None  # Für visuelles Feedback bei angeklickten Trades
        self.collectors_data = collectors_data or {}
        self.selected_collector = selected_collector
        self.app.layout = self._create_layout()
        self._register_callbacks()

    def _create_layout(self):
        # Header mit Gradient-Background
        header = html.Div([
            html.Div("by Raph & Ferdi", style={
                'position': 'absolute',
                'top': '8px',
                'right': '15px',
                'color': 'rgba(255,255,255,0.6)',
                'fontSize': '10px',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontWeight': '400',
                'letterSpacing': '0.5px'
            }),
            html.H1("Algorithmic Trading Dashboard", style={
                'textAlign': 'center', 
                'color': '#ffffff', 
                'marginBottom': '0px',
                'marginTop': '0px',
                'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
                'fontWeight': '700',
                'letterSpacing': '-0.02em',
                'fontSize': '2rem',
                'textShadow': '0 2px 4px rgba(0,0,0,0.1)'
            }),
            html.P("Professional Trading Analytics & Performance Monitoring", style={
                'textAlign': 'center',
                'color': 'rgba(255,255,255,0.9)',
                'fontFamily': 'Inter, system-ui, sans-serif',
                'fontSize': '0.9rem',
                'fontWeight': '400',
                'margin': '5px 0 0 0',
                'letterSpacing': '0.01em'
            })
        ], style={
            'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            'padding': '15px 20px',
            'marginBottom': '0px',
            'borderRadius': '0',
            'boxShadow': '0 4px 16px rgba(0,0,0,0.1)',
            'position': 'relative',
            'display': 'flex',
            'flexDirection': 'column',
            'justifyContent': 'center',
            'alignItems': 'center',
            'minHeight': '85px'
        })

        # Collector Dropdown
        collector_dropdown = html.Div([
            html.H4("Collector / Instrument", style={
                'color': '#2c3e50','marginBottom': '8px','fontFamily': 'Inter, system-ui','fontWeight': '600','fontSize': '16px'
            }),
            dcc.Dropdown(
                id='collector-dropdown',
                options=[{'label': k, 'value': k} for k in self.collectors_data.keys()],
                value=self.selected_collector,
                placeholder="Select collector...",
                style={'fontFamily': 'Inter, system-ui'}
            )
        ], style={
            'background': 'linear-gradient(145deg,#ffffff,#f8f9fa)',
            'border': '1px solid rgba(222,226,230,0.6)',
            'borderRadius': '16px',
            'padding': '15px',
            'margin': '15px 20px',
            'boxShadow': '0 4px 12px rgba(0,0,0,0.06)'
        })

        # Main Content Container
        main_content = html.Div([
            # Trade Details Panel
            html.Div([
                html.Div(id='trade-details-panel', children=[
                    html.Div([
                        html.H4("Trade Details", style={
                            'color': '#2c3e50',
                            'marginBottom': '10px',
                            'fontFamily': 'Inter, system-ui, sans-serif',
                            'fontWeight': '600',
                            'textAlign': 'center',
                            'fontSize': '18px',
                            'letterSpacing': '-0.01em'
                        }),
                        html.P("Click on a trade marker in the chart below to see details", style={
                            'color': '#6c757d',
                            'fontFamily': 'Inter, system-ui, sans-serif',
                            'textAlign': 'center',
                            'fontSize': '14px',
                            'margin': '0',
                            'fontWeight': '400'
                        })
                    ])
                ])
            ], style={
                'background': 'linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%)',
                'border': '1px solid rgba(222, 226, 230, 0.6)',
                'borderRadius': '0 0 16px 16px',
                'padding': '20px',
                'marginBottom': '15px',
                'maxHeight': '300px',
                'overflowY': 'auto',
                'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
                'backdropFilter': 'blur(10px)',
                'position': 'relative'
            }),

            # Hauptchart für Bars und Trades
            html.Div([
                html.Div([
                    html.H3("Price Data & Trading Signals", style={
                        'color': '#2c3e50', 
                        'marginBottom': '20px',
                        'fontFamily': 'Inter, system-ui, sans-serif',
                        'fontWeight': '600',
                        'fontSize': '20px',
                        'letterSpacing': '-0.01em'
                    }),
                    dcc.Graph(id='price-chart', style={'height': '650px'})
                ], style={
                    'background': '#ffffff',
                    'borderRadius': '16px',
                    'padding': '25px',
                    'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
                    'border': '1px solid rgba(222, 226, 230, 0.6)'
                })
            ], style={'margin': '15px 20px'}),
            
            # Container für alle Indikator-Subplots
            html.Div([
                html.Div(id='indicators-container')
            ], style={'margin': '10px 20px'}),
            
            # Performance Metriken
            html.Div([
                html.Div([
                    html.H3("Performance Metrics", style={
                        'color': '#2c3e50', 
                        'marginBottom': '20px',
                        'fontFamily': 'Inter, system-ui, sans-serif',
                        'fontWeight': '600',
                        'fontSize': '20px',
                        'letterSpacing': '-0.01em'
                    }),
                    html.Div(id='metrics-display', style={
                        'background': 'linear-gradient(145deg, #f8f9fa 0%, #ffffff 100%)',
                        'border': '1px solid rgba(222, 226, 230, 0.6)',
                        'borderRadius': '12px',
                        'padding': '25px'
                    })
                ], style={
                    'background': '#ffffff',
                    'borderRadius': '16px',
                    'padding': '25px',
                    'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
                    'border': '1px solid rgba(222, 226, 230, 0.6)'
                })
            ], style={'margin': '15px 20px'}),

            # Übersichtstabelle für alle Runs
            html.Div([
                html.H3("All Backtest Results", style={
                    'color': '#2c3e50',
                    'marginBottom': '20px',
                    'fontFamily': 'Inter, system-ui, sans-serif',
                    'fontWeight': '600',
                    'fontSize': '20px',
                    'letterSpacing': '-0.01em'
                }),
                html.Div(id='all-results-table'),
                dcc.Store(id='filter-sharpe-active', data=False)
            ], style={'margin': '15px 20px'}),

            # Refresh Button
            html.Div([
                html.Button('Update Dashboard', id='refresh-btn', n_clicks=0,
                            style={
                                'padding': '14px 32px',
                                'fontSize': '16px',
                                'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                'color': 'white',
                                'border': 'none',
                                'borderRadius': '25px',
                                'cursor': 'pointer',
                                'fontFamily': 'Inter, system-ui, sans-serif',
                                'fontWeight': '600',
                                'letterSpacing': '0.01em',
                                'boxShadow': '0 4px 15px rgba(102, 126, 234, 0.4)',
                                'transition': 'all 0.3s ease',
                                'textShadow': '0 1px 2px rgba(0,0,0,0.1)'
                            })
            ], style={
                'textAlign': 'center',
                'margin': '30px 0'
            })
        ], style={
            'maxWidth': '100%',
            'margin': '0',
            'padding': '0'
        })

        return html.Div([header, collector_dropdown, main_content], style={
            'minHeight': '100vh',
            'background': 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
            'fontFamily': 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
        })

    def _register_callbacks(self):
        # FIX: merged duplicate callbacks (previously caused duplicate outputs error)
        @self.app.callback(
            [
                Output('price-chart', 'figure'),
                Output('indicators-container', 'children'),
                Output('metrics-display', 'children'),
                Output('trade-details-panel', 'children'),
                Output('all-results-table', 'children')
            ],
            [
                Input('collector-dropdown', 'value'),
                Input('refresh-btn', 'n_clicks'),
                Input('price-chart', 'clickData'),
                Input('filter-sharpe-active', 'data')
            ],
            prevent_initial_call=False
        )
        def unified_dashboard_callback(sel_collector, refresh_clicks, clickData, filter_active):
            try:
                ctx = dash.callback_context
                triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'init'

                # 1. Collector change
                if triggered_id == 'collector-dropdown' and sel_collector and sel_collector in self.collectors_data:
                    data = self.collectors_data[sel_collector]
                    self.selected_collector = sel_collector
                    self.bars_df = data["bars_df"]
                    self.trades_df = data["trades_df"]
                    self.indicators_df = data["indicators_df"]
                    self.selected_trade_index = None

                # 2. Indicators
                try:
                    indicators_components = self.create_indicator_subplots()
                except Exception as e:
                    print(f"Fehler bei Indikatoren: {e}")
                    indicators_components = []

                # 3. Metrics
                try:
                    metrics_table = self.create_metrics_table()
                except Exception as e:
                    print(f"Fehler bei Metriken: {e}")
                    metrics_table = html.Div("Metrics could not be loaded")

                # 4. All results table (with optional Sharpe filter)
                try:
                    all_results_table = self.create_all_results_table(filter_active)
                except Exception as e:
                    print(f"Fehler bei all_results_table: {e}")
                    all_results_table = html.Div("Backtest results could not be loaded")

                # 5. Trade click handling
                if triggered_id == 'price-chart' and clickData and self.trades_df is not None and not self.trades_df.empty:
                    try:
                        trade_point = next((p for p in clickData['points'] if 'customdata' in p), None)
                        if trade_point is not None:
                            trade_index = trade_point['customdata']
                            if trade_index in self.trades_df.index:
                                self.selected_trade_index = trade_index
                                trade_details = self.create_trade_details_content(self.trades_df.loc[trade_index])
                            else:
                                self.selected_trade_index = None
                                trade_details = self.get_default_trade_details()
                        else:
                            self.selected_trade_index = None
                            trade_details = self.get_default_trade_details_with_message()
                    except Exception as e:
                        print(f"Fehler bei Trade-Details: {e}")
                        self.selected_trade_index = None
                        trade_details = self.get_default_trade_details()
                else:
                    # Reset selection on other triggers
                    self.selected_trade_index = None
                    trade_details = self.get_default_trade_details()

                # 6. Price chart
                try:
                    price_fig = self.create_price_chart()
                except Exception as e:
                    print(f"Fehler bei Chart-Erstellung: {e}")
                    price_fig = go.Figure().update_layout(title="Chart could not be loaded")

                return price_fig, indicators_components, metrics_table, trade_details, all_results_table

            except Exception as e:
                print(f"Allgemeiner Callback-Fehler: {e}")
                empty_fig = go.Figure().update_layout(title="Error loading dashboard")
                return empty_fig, [], html.Div("Error"), self.get_default_trade_details(), html.Div("Error")

        @self.app.callback(
            Output('filter-sharpe-active', 'data'),
            Input('custom-filter-btn', 'n_clicks'),
            State('filter-sharpe-active', 'data'),
            prevent_initial_call=True
        )
        def toggle_sharpe_filter(n_clicks, current_state):
            if n_clicks is None:
                return False
            return not current_state

        # Indicator sync callbacks remain unchanged
        try:
            self._register_indicator_sync_callbacks()
        except Exception as e:
            print(f"Fehler bei Indikator-Callbacks: {e}")

    def create_all_results_table(self, filter_active=False):
        """Erstellt eine cleane, sortierbare Tabelle für alle Runs."""
        results_path = Path(__file__).resolve().parents[2] / "data" / "DATA_STORAGE" / "results" / "all_backtest_results.csv"
        if not results_path.exists():
            return html.Div("No backtest results found.", style={'textAlign': 'center', 'color': '#6c757d'})
        try:
            all_results_df = pd.read_csv(results_path)
        except Exception as e:
            print(f"Fehler beim Laden von all_backtest_results.csv: {e}")
            return html.Div("No backtest results found.", style={'textAlign': 'center', 'color': '#6c757d'})
        if all_results_df.empty:
            return html.Div("No backtest results found.", style={'textAlign': 'center', 'color': '#6c757d'})

        # Finde Sharpe-Ratio-Spalte robust
        sharpe_col = None
        for col in all_results_df.columns:
            if "sharpe" in col.lower():
                sharpe_col = col
                break

        # Finde erste numerische Spalte für Default-Sortierung
        sort_by = None
        for col in all_results_df.columns:
            if pd.api.types.is_numeric_dtype(all_results_df[col]):
                sort_by = col
                break

        columns = [{"name": i, "id": i, "deletable": False, "selectable": False, "hideable": False} for i in all_results_df.columns]

        # Filter-Button
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

        df = all_results_df.copy()
        if filter_active:
            if sharpe_col:
                try:
                    df[sharpe_col] = pd.to_numeric(df[sharpe_col], errors='coerce')
                    df[sharpe_col] = df[sharpe_col].fillna(-1e9)
                    df = df.sort_values(by=sharpe_col, ascending=False)
                except Exception as e:
                    print(f"Fehler beim Sortieren nach Sharpe Ratio: {e}")
            else:
                return html.Div([
                    filter_button,
                    html.Div("No Sharpe Ratio column found for sorting.", style={'color': '#dc3545', 'marginTop': '10px'})
                ])
        elif sort_by:
            df = df.sort_values(by=sort_by, ascending=False)

        return html.Div([
            html.Div([
                filter_button
            ], style={'width': '100%', 'display': 'flex', 'justifyContent': 'flex-end'}),
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
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': '#f6f8fa'
                    },
                    {
                        'if': {'state': 'selected'},
                        'backgroundColor': '#e5e7eb',
                        'border': 'none',
                    },
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
        """Timestamp-basierter Hauptchart."""
        try:
            fig = go.Figure()
            # Bars
            if self.bars_df is not None and not self.bars_df.empty:
                bars = self.bars_df
                fig.add_trace(go.Candlestick(
                    x=bars['timestamp'],
                    open=bars['open'], high=bars['high'],
                    low=bars['low'], close=bars['close'],
                    name='OHLC',
                    increasing_line_color='#26a69a',
                    decreasing_line_color='#ef5350',
                    increasing_fillcolor='#26a69a',
                    decreasing_fillcolor='#ef5350',
                    showlegend=True
                ))
            # Overlay Indicators (plot_id == 0)
            for name, df in self.indicators_df.items():
                try:
                    if df.empty: continue
                    pid = int(df['plot_id'].iloc[0])
                    if pid == 0:
                        fig.add_trace(go.Scatter(
                            x=df['timestamp'],
                            y=df['value'],
                            mode='lines',
                            name=name.upper(),
                            line=dict(width=2.0)
                        ))
                except Exception as e:
                    print(f"Indicator Fehler {name}: {e}")
            # Trades
            if self.trades_df is not None and not self.trades_df.empty:
                trades = self.trades_df
                # BUY
                buy = trades[trades['action'] == 'BUY']
                if not buy.empty:
                    normal = buy.index.difference([self.selected_trade_index]) if self.selected_trade_index is not None else buy.index
                    if len(normal) > 0:
                        nb = buy.loc[normal]
                        fig.add_trace(go.Scatter(
                            x=nb['timestamp'],
                            y=nb.get('open_price_actual', nb.get('price_actual', 0)),
                            mode='markers',
                            name='BUY',
                            marker=dict(symbol='triangle-up', size=14, color='#28a745',
                                        line=dict(color='#ffffff', width=1)),
                            customdata=nb.index.tolist(),
                            hovertemplate='<b>BUY</b><br>%{x}<br>Price: %{y:.4f}<extra></extra>'
                        ))
                    if self.selected_trade_index in buy.index:
                        st = buy.loc[[self.selected_trade_index]]
                        fig.add_trace(go.Scatter(
                            x=st['timestamp'],
                            y=st.get('open_price_actual', st.get('price_actual', 0)),
                            mode='markers',
                            name='Selected BUY',
                            marker=dict(symbol='triangle-up', size=18, color='#28a745',
                                        line=dict(color='#000000', width=1)),
                            customdata=[self.selected_trade_index],
                            hovertemplate='<b>SELECTED BUY</b><br>%{x}<br>Price: %{y:.4f}<extra></extra>',
                            showlegend=False
                        ))
                # SHORT
                sell = trades[trades['action'] == 'SHORT']
                if not sell.empty:
                    normal = sell.index.difference([self.selected_trade_index]) if self.selected_trade_index is not None else sell.index
                    if len(normal) > 0:
                        ns = sell.loc[normal]
                        fig.add_trace(go.Scatter(
                            x=ns['timestamp'],
                            y=ns.get('open_price_actual', ns.get('price_actual', 0)),
                            mode='markers',
                            name='SHORT',
                            marker=dict(symbol='triangle-down', size=14, color='#dc3545',
                                        line=dict(color='#ffffff', width=1)),
                            customdata=ns.index.tolist(),
                            hovertemplate='<b>SHORT</b><br>%{x}<br>Price: %{y:.4f}<extra></extra>'
                        ))
                    if self.selected_trade_index in sell.index:
                        st = sell.loc[[self.selected_trade_index]]
                        fig.add_trace(go.Scatter(
                            x=st['timestamp'],
                            y=st.get('open_price_actual', st.get('price_actual', 0)),
                            mode='markers',
                            name='Selected SHORT',
                            marker=dict(symbol='triangle-down', size=18, color='#dc3545',
                                        line=dict(color='#000000', width=1)),
                            customdata=[self.selected_trade_index],
                            hovertemplate='<b>SELECTED SHORT</b><br>%{x}<br>Price: %{y:.4f}<extra></extra>',
                            showlegend=False
                        ))
                if self.selected_trade_index is not None:
                    self.add_trade_visualization(fig, self.selected_trade_index)
            fig.update_layout(
                xaxis_title="Time",
                yaxis_title="Price (USDT)",
                template="plotly_white",
                hovermode='closest',
                margin=dict(t=30, b=50, l=60, r=20),
                xaxis=dict(rangeslider=dict(visible=False))
            )
            return fig
        except Exception as e:
            print(f"Chart Fehler: {e}")
            f = go.Figure()
            f.update_layout(title="Chart Error")
            return f

    def add_trade_visualization(self, fig, trade_index):
        """
        Fügt professionelle Trade-Visualisierung hinzu:
        - Entry und Exit Linien (gestrichelt, dezent, über ganzen Chart)
        - TP/SL Boxen (falls vorhanden)
        - Exit-Marker (kleines schwarzes X)
        """
        try:
            if self.trades_df is None or trade_index not in self.trades_df.index:
                return
            
            trade = self.trades_df.loc[trade_index]
            
            # Trade-Daten extrahieren mit neuen CSV-Spaltennamen
            entry_time = pd.to_datetime(trade['timestamp'])
            entry_price = trade.get('open_price_actual', trade.get('price_actual', None))  # Fallback für alte Daten
            action = trade['action']  # BUY oder SHORT
            
            # Exit-Daten (falls vorhanden)
            exit_time = None
            exit_price = None
            if pd.notna(trade.get('closed_timestamp', None)) and pd.notna(trade.get('close_price_actual', None)):
                exit_time = pd.to_datetime(trade['closed_timestamp'])
                exit_price = trade['close_price_actual']
            
            # TP/SL Daten
            tp = trade.get('tp', None)
            sl = trade.get('sl', None)
            
            # 1. Entry-Linie (dezent, gestrichelt, über ganzen Zeitbereich)
            if entry_price is not None:
                self._add_price_line_full_chart(fig, entry_price, "Entry", "rgba(0,0,0,0.35)", dash="dash")
            
            # 2. Exit-Linie und Exit-Marker (falls vorhanden)
            if exit_time is not None and exit_price is not None:
                self._add_price_line_full_chart(fig, exit_price, "Exit", "rgba(0,0,0,0.35)", dash="dash")
                self._add_exit_marker_small(fig, exit_time, exit_price)
            
            # 3. TP/SL Boxen (falls vorhanden)
            if exit_time is not None and entry_price is not None and (pd.notna(tp) or pd.notna(sl)):
                self._add_tp_sl_boxes(fig, entry_time, exit_time, entry_price, action, tp, sl)
                
        except Exception as e:
            print(f"Fehler bei Trade-Visualisierung: {e}")
    
    def _add_price_line_full_chart(self, fig, price, name, color, dash="dash"):
        """Fügt eine horizontale Preis-Linie über den ganzen Chart hinzu (Timestamp-Achse)."""
        try:
            if self.bars_df is not None and not self.bars_df.empty:
                min_ts = self.bars_df['timestamp'].min()
                max_ts = self.bars_df['timestamp'].max()
            else:
                # Fallback, falls keine Bars vorhanden sind
                min_ts, max_ts = pd.Timestamp.now() - pd.Timedelta(days=1), pd.Timestamp.now()
            
            fig.add_trace(
                go.Scatter(
                    x=[min_ts, max_ts],
                    y=[price, price],
                    mode='lines',
                    name=f"{name} Line",
                    line=dict(color=color, width=1, dash=dash),
                    showlegend=False,
                    hovertemplate=f'<b>{name} Price</b><br>Price: {price:.4f} USDT<extra></extra>'
                )
            )
        except Exception as e:
            print(f"Fehler bei Vollchart-Preis-Linie: {e}")

    def _add_price_line(self, fig, time, price, name, color, dash="solid"):
        """Fügt eine horizontale Preis-Linie hinzu (Bar-Index)."""
        try:
            if self.bars_df is not None and not self.bars_df.empty:
                # Ermittle den nächsten Bar-Index zu time
                bar_indices = self.bars_df['bar_index']
                timestamps = pd.to_datetime(self.bars_df['timestamp'])
                # Finde den Bar-Index, der time am nächsten ist
                idx = (abs(timestamps - time)).idxmin()
                center_bar_index = self.bars_df.loc[idx, 'bar_index']
                min_bar_index = bar_indices.min()
                max_bar_index = bar_indices.max()
                # Linie über den ganzen Chart
                fig.add_trace(
                    go.Scatter(
                        x=[min_bar_index, max_bar_index],
                        y=[price, price],
                        mode='lines',
                        name=f"{name} Line",
                        line=dict(color=color, width=2, dash=dash),
                        showlegend=False,
                        hovertemplate=f'<b>{name} Price</b><br>Price: {price:.2f} USDT<extra></extra>'
                    )
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=[0, 1],
                        y=[price, price],
                        mode='lines',
                        name=f"{name} Line",
                        line=dict(color=color, width=2, dash=dash),
                        showlegend=False,
                        hovertemplate=f'<b>{name} Price</b><br>Price: {price:.2f} USDT<extra></extra>'
                    )
                )
        except Exception as e:
            print(f"Fehler bei Preis-Linie: {e}")
    
    def _add_exit_marker_small(self, fig, exit_time, exit_price):
        """Fügt einen kleinen schwarzen X-Marker am Exit-Punkt hinzu (Timestamp-Achse)."""
        try:
            fig.add_trace(
                go.Scatter(
                    x=[exit_time],
                    y=[exit_price],
                    mode='markers',
                    name='Trade Exit',
                    marker=dict(
                        symbol='x',
                        size=11,
                        color='#000000',
                        line=dict(color='#ffffff', width=1)
                    ),
                    showlegend=False,
                    hovertemplate='<b>Trade Exit</b><br>%{x}<br>Price: %{y:.4f} USDT<extra></extra>'
                )
            )
        except Exception as e:
            print(f"Fehler bei kleinem Exit-Marker: {e}")

    def _add_exit_marker(self, fig, exit_time, exit_price):
        """Fügt einen schwarzen X-Marker am Exit-Punkt hinzu (Bar-Index)."""
        try:
            if self.bars_df is not None and not self.bars_df.empty:
                timestamps = pd.to_datetime(self.bars_df['timestamp'])
                idx = (abs(timestamps - exit_time)).idxmin()
                exit_bar_index = self.bars_df.loc[idx, 'bar_index']
            else:
                exit_bar_index = 0
            fig.add_trace(
                go.Scatter(
                    x=[exit_bar_index],
                    y=[exit_price],
                    mode='markers',
                    name='Trade Exit',
                    marker=dict(
                        symbol='x',
                        size=15,
                        color='#000000',
                        line=dict(color='#ffffff', width=2)
                    ),
                    showlegend=False,
                    hovertemplate='<b>Trade Exit</b><br>Bar Index: %{x}<br>Price: %{y:.2f} USDT<extra></extra>'
                )
            )
        except Exception as e:
            print(f"Fehler bei Exit-Marker: {e}")
    
    def _add_tp_sl_boxes(self, fig, entry_time, exit_time, entry_price, action, tp, sl):
        """Fügt TP/SL Boxen wie im professionellen Trading-Interface hinzu."""
        try:
            is_long = action == 'BUY'
            
            # TP Box (Take Profit)
            if pd.notna(tp) and tp > 0:
                if is_long:
                    # Long: TP ist oberhalb Entry (grün)
                    box_color = "rgba(76, 175, 80, 0.2)"  # Grün
                    line_color = "#4CAF50"
                    tp_y_top = max(tp, entry_price)
                    tp_y_bottom = min(tp, entry_price)
                else:
                    # Short: TP ist unterhalb Entry (grün für Short)
                    box_color = "rgba(76, 175, 80, 0.2)"  # Grün
                    line_color = "#4CAF50"
                    tp_y_top = max(tp, entry_price)
                    tp_y_bottom = min(tp, entry_price)
                
                self._add_box(fig, entry_time, exit_time, tp_y_bottom, tp_y_top, 
                             box_color, line_color, "TP")
            
            # SL Box (Stop Loss)
            if pd.notna(sl) and sl > 0:
                if is_long:
                    # Long: SL ist unterhalb Entry (rot)
                    box_color = "rgba(244, 67, 54, 0.2)"  # Rot
                    line_color = "#F44336"
                    sl_y_top = max(sl, entry_price)
                    sl_y_bottom = min(sl, entry_price)
                else:
                    # Short: SL ist oberhalb Entry (rot für Short)
                    box_color = "rgba(244, 67, 54, 0.2)"  # Rot
                    line_color = "#F44336"
                    sl_y_top = max(sl, entry_price)
                    sl_y_bottom = min(sl, entry_price)
                
                self._add_box(fig, entry_time, exit_time, sl_y_bottom, sl_y_top, 
                             box_color, line_color, "SL")
                
        except Exception as e:
            print(f"Fehler bei TP/SL Boxen: {e}")
    
    def _add_box(self, fig, start_time, end_time, y_bottom, y_top, fill_color, line_color, label):
        """Fügt eine rechteckige Box hinzu (Timestamp-Achse)."""
        try:
            fig.add_trace(
                go.Scatter(
                    x=[start_time, end_time, end_time, start_time, start_time],
                    y=[y_bottom, y_bottom, y_top, y_top, y_bottom],
                    fill="toself",
                    fillcolor=fill_color,
                    line=dict(color=line_color, width=1),
                    mode='lines',
                    name=f"{label} Zone",
                    showlegend=False,
                    hovertemplate=f'<b>{label} Zone</b><br>Range: {y_bottom:.2f} - {y_top:.2f} USDT<extra></extra>'
                )
            )
            # Label für die Box
            mid_time = start_time + (end_time - start_time) / 2
            mid_price = (y_bottom + y_top) / 2
            fig.add_annotation(
                x=mid_time,
                y=mid_price,
                text=label,
                showarrow=False,
                font=dict(color=line_color, size=12, family="Inter, system-ui, sans-serif"),
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor=line_color,
                borderwidth=1
            )
        except Exception as e:
            print(f"Fehler bei Box-Erstellung: {e}")

    def create_indicator_subplots(self):
        """Erstellt Subplots für alle Indikatoren mit plot_id > 0 (nie im Hauptchart!)."""
        try:
            plot_groups = {}
            for name, indicator_df in self.indicators_df.items():
                if indicator_df is not None and not indicator_df.empty:
                    # Robust: plot_id aus DataFrame, fallback auf plot_number
                    if 'plot_id' in indicator_df.columns:
                        plot_id_val = int(indicator_df.iloc[0]['plot_id'])
                    elif 'plot_number' in indicator_df.columns:
                        plot_id_val = int(indicator_df.iloc[0]['plot_number'])
                    else:
                        plot_id_val = 0
                    if plot_id_val > 0:
                        if plot_id_val not in plot_groups:
                            plot_groups[plot_id_val] = []
                        plot_groups[plot_id_val].append((name, indicator_df))

            if not plot_groups:
                return html.Div("Keine Subplot-Indikatoren gefunden.")

            subplot_components = []
            for plot_id in sorted(plot_groups.keys()):
                indicators_in_plot = plot_groups[plot_id]
                plot_id_str = str(plot_id)
                indicator_names = [name for name, _ in indicators_in_plot]
                subplot_components.append(
                    html.Div([
                        html.H4(f"Indicators (Plot {plot_id_str}): {', '.join(indicator_names)}", style={
                            'color': '#2c3e50',
                            'marginBottom': '15px',
                            'fontFamily': 'Inter, system-ui, sans-serif',
                            'fontWeight': '600',
                            'fontSize': '18px',
                            'letterSpacing': '-0.01em'
                        }),
                        dcc.Graph(
                            id=f'indicators-plot-{plot_id_str}',
                            figure=self.create_subplot_figure(indicators_in_plot),
                            style={'height': '300px', 'marginBottom': '10px'}
                        )
                    ], style={
                        'background': '#ffffff',
                        'borderRadius': '16px',
                        'padding': '25px',
                        'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
                        'border': '1px solid rgba(222, 226, 230, 0.6)',
                        'marginBottom': '20px'
                    })
                )

            return html.Div(subplot_components)
        except Exception as e:
            print(f"Fehler bei Indikator-Subplots: {e}")
            return html.Div(f"Fehler bei Indikator-Subplots: {e}")

    def create_subplot_figure(self, indicators_list):
        """Erstellt Figure für einen Indikator-Subplot."""
        fig = go.Figure()
        
        colors = ['#000000', 'rgba(0,0,0,0.7)', 'rgba(0,0,0,0.5)', 'rgba(64,64,64,0.8)', 'rgba(96,96,96,0.6)']
        for i, (name, indicator_df) in enumerate(indicators_list):
            fig.add_trace(
                go.Scatter(
                    x=indicator_df['timestamp'],
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
            font=dict(family='Inter, system-ui', size=11),
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
            
            # P&L-Felder (mit +/- Vorzeichen)
            elif 'pnl' in key_lower or 'p&l' in key_lower:
                try:
                    pnl_value = float(value)
                    sign = "+" if pnl_value >= 0 else ""
                    return f"{sign}{pnl_value:.4f}"
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
        
        # main fields
        key_fields = ['timestamp', 'action', 'open_price_actual', 'close_price_actual', 'closed_timestamp', 'tradesize', 'sl', 'tp', 'realized_pnl', 'fee']
        
        main_info = []
        for field in key_fields:
            if field in trade_data and not pd.isna(trade_data[field]):
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

    def run(self, **kwargs):
        self.app.run(**kwargs)

if __name__ == "__main__":
    dashboard = DashboardApp()
    dashboard.run(debug=True, port=8050)

