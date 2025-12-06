from pathlib import Path
import pandas as pd
import quantstats as qs
import webbrowser
import tempfile
from dash import html, dcc
import warnings
try:
    import matplotlib
    matplotlib.use("Agg")  # verhindert GUI Backend -> unterdrückt Thread-Warnungen
except Exception:
    pass
warnings.filterwarnings(
    "ignore",
    message="Starting a Matplotlib GUI outside of the main thread will likely fail."
)

class QuantStatsViewer:
    """
    Erstellt QuantStats-Reports für ausgewählte Runs
    """

    def __init__(self):
        self._callbacks_registered = False
        self._instance_id = id(self)
        self.debug = False

    def build_components(self, runs_df, selected_run_indices, app=None):
        """Return sidebar pieces (controls)."""
        if app is not None:
            self.register_callbacks(app)
        
        controls = self._build_controls(runs_df, selected_run_indices)
        return {"controls": controls}

    def _build_controls(self, runs_df, selected_indices):
        # Wenn keine Runs ausgewählt sind, zeige GAR NICHTS an
        if not selected_indices:
            return html.Div(style={'height': '0px', 'overflow': 'hidden'})
        
        # Run-Optionen vorbereiten
        opts = []
        for idx in selected_indices:
            if 0 <= idx < len(runs_df):
                row = runs_df.iloc[idx]
                rid = self._resolve_run_id(row)
                short = rid[:15] + ("…" if len(rid) > 15 else "")
                opts.append({"label": short, "value": rid})
        
        if not opts:
            return html.Div(style={'height': '0px', 'overflow': 'hidden'})

        run_dropdown = dcc.Dropdown(
            id="quantstats-run-select",
            options=opts,
            value=opts[0]["value"],
            clearable=False,
            searchable=False,
            style={
                'minWidth': '125px',
                'fontSize': '10.5px',
                'height': '30px',
                'padding': '0 4px'
            }
        )

        benchmark_dropdown = dcc.Dropdown(
            id="quantstats-benchmark-select",
            options=[
                {'label': 'None', 'value': ''},
                {'label': 'Bitcoin', 'value': 'BTC-USD'},
                {'label': 'Solana', 'value': 'SOL-USD'},
                {'label': 'S&P 500', 'value': '^GSPC'},
                {'label': 'Gold', 'value': 'GC=F'},
                {'label': 'Custom', 'value': 'CUSTOM'}
            ],
            value='BTC-USD',
            clearable=False,
            searchable=False,
            style={
                'minWidth': '120px',
                'fontSize': '10.5px',
                'height': '30px',
                'padding': '0 4px'
            }
        )

        custom_input = dcc.Input(
            id="quantstats-custom-symbol",
            type="text",
            placeholder="Symbol",
            style={
                'display': 'none',
                'minWidth': '100px',
                'fontSize': '10.5px',
                'padding': '5px 8px',
                'height': '30px',
                'border': '1px solid #d1d5db',
                'borderRadius': '7px'
            }
        )

        button = html.Button(
            "QuantStats",
            id="generate-quantstats-btn", 
            n_clicks=0,
            style={
                'background': 'linear-gradient(90deg,#f59e0b 0%,#d97706 100%)',
                'color': '#fff',
                'border': 'none',
                'borderRadius': '8px',
                'padding': '0 14px',
                'cursor': 'pointer',
                'fontWeight': '600',
                'fontSize': '11px',
                'boxShadow': '0 2px 5px -1px rgba(245,158,11,0.40)',
                'transition': 'background .25s',
                'whiteSpace': 'nowrap',
                'height': '34px',
                'display': 'flex',
                'alignItems': 'center'
            }
        )
        
        return html.Div([run_dropdown, benchmark_dropdown, custom_input, button], style={
            'display': 'flex',
            'alignItems': 'center',
            'gap': '6px'
        })

    def _resolve_run_id(self, row):
        rid = str(row.get('run_id') or "").strip()
        if rid:
            return rid
        idx = row.get('run_index')
        return f"run{idx}" if idx is not None else "run_unknown"

    def _results_dir(self):
        current = Path(__file__).resolve()
        return current.parents[4] / "data" / "DATA_STORAGE" / "results"

    def _find_equity_csv(self, run_id):
        """Findet die total_equity.csv für einen Run"""
        run_dir = self._results_dir() / run_id
        
        # check general/indicators folder first
        general_indicators_dir = run_dir / "general" / "indicators"
        if general_indicators_dir.exists():
            equity_file = general_indicators_dir / "total_equity.csv"
            if equity_file.exists():
                self._log(f"Found equity file in general: {equity_file}")
                return equity_file
        
        self._log(f"No total_equity.csv found for run {run_id}")
        return None

    def _generate_quantstats_report(self, run_id, benchmark_symbol=None):
        """Generiert QuantStats-Report und öffnet ihn im Browser"""
        try:
            # Equity CSV finden
            equity_csv = self._find_equity_csv(run_id)
            if not equity_csv:
                raise FileNotFoundError(f"No total_equity.csv found for run {run_id}")

            # Equity-Kurve laden
            equity_df = pd.read_csv(equity_csv, usecols=["timestamp", "value"])
            equity = pd.Series(
                equity_df["value"].values, 
                index=pd.to_datetime(equity_df["timestamp"], unit="ns")
            )
            equity = equity[~equity.index.duplicated(keep='first')]
            
            # Fix: Resample auf Tagesbasis
            equity_daily = equity.resample("1D").last().dropna()
            returns = equity_daily.pct_change(fill_method=None).dropna()

            # Benchmark laden (falls angegeben)
            benchmark = None
            if benchmark_symbol and benchmark_symbol.strip():
                try:
                    benchmark = qs.utils.download_returns(benchmark_symbol)
                    # Benchmark auf gleiche Zeitspanne beschränken
                    benchmark = benchmark[equity_daily.index.min():equity_daily.index.max()]
                except Exception as e:
                    self._log(f"Warning: Could not load benchmark {benchmark_symbol}: {e}")
                    benchmark = None

            # Temporäre HTML-Datei erstellen
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as tmp_file:
                output_path = tmp_file.name

            # QuantStats Report generieren
            qs.reports.html(
                returns, 
                benchmark=benchmark, 
                output=output_path,
                title=f"QuantStats Report - {run_id}"
            )

            # Im Browser öffnen
            webbrowser.open(f'file://{output_path}')
            
            return True, f"QuantStats report generated and opened for {run_id}"

        except Exception as e:
            return False, f"Error generating QuantStats report: {str(e)}"

    def register_callbacks(self, app):
        if self._callbacks_registered:
            return
            
        self._callbacks_registered = True
        
        from dash import Input, Output, State
        try:
            from dash import ctx
        except ImportError:
            import dash
            ctx = dash.callback_context

        # Callback für Custom Symbol Input anzeigen/verstecken
        @app.callback(
            Output("quantstats-custom-symbol", "style"),
            Input("quantstats-benchmark-select", "value"),
            prevent_initial_call=True
        )
        def toggle_custom_input(benchmark_value):
            if (benchmark_value == 'CUSTOM'):
                return {
                    'display': 'block',
                    'minWidth': '100px',
                    'fontSize': '10px',
                    'padding': '4px 6px',
                    'border': '1px solid #d1d5db',
                    'borderRadius': '6px'
                }
            else:
                return {'display': 'none'}

        # Callback für QuantStats Report Generation
        @app.callback(
            Output("quantstats-status", "data"),  # Direkt auf den Store
            Input("generate-quantstats-btn", "n_clicks"),
            State("quantstats-run-select", "value"),
            State("quantstats-benchmark-select", "value"),
            State("quantstats-custom-symbol", "value"),
            prevent_initial_call=True
        )
        def generate_report(n_clicks, run_id, benchmark_value, custom_symbol):
            self._log(f"*** CALLBACK TRIGGERED *** n_clicks={n_clicks}")
            self._log(f"run_id={run_id}, benchmark_value={benchmark_value}")
            
            if not n_clicks or not run_id:
                return ""

            # Benchmark Symbol bestimmen
            benchmark_symbol = None
            if benchmark_value == 'CUSTOM':
                benchmark_symbol = custom_symbol if custom_symbol and custom_symbol.strip() else None
            elif benchmark_value and benchmark_value != '':
                benchmark_symbol = benchmark_value

            self._log(f"Using benchmark: {benchmark_symbol}")

            # Report generieren
            success, message = self._generate_quantstats_report(run_id, benchmark_symbol)
            
            self._log(message)
            return message  # Return message to store

    def _log(self, msg: str):
        if self.debug:
            print(f"[QUANTSTATS] {msg}")
