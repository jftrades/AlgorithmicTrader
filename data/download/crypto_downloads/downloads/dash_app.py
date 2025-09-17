
import json
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from dash import Dash, dcc, html, Input, Output, State, dash_table

# Projekt-Imports
from main_download import CryptoDataOrchestrator
from new_future_list_download import BinancePerpetualFuturesDiscovery

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE"
FUTURES_CSV = BASE_DATA_DIR / "project_future_scraper" / "new_binance_perpetual_futures.csv"

app = Dash(__name__)
app.title = "Crypto Data Downloader"

def _safe_json(obj) -> str:
    try:
        return json.dumps(obj, indent=2)
    except Exception:
        return str(obj)

def discover_futures(start: str, end: str, only_usdt: bool) -> List[Dict[str, str]]:
    d = BinancePerpetualFuturesDiscovery(
        start_date=start,
        end_date=end,
        only_usdt=only_usdt,
    )
    return d.run()

def load_futures_csv() -> List[Dict[str, str]]:
    if not FUTURES_CSV.exists():
        return []
    import csv
    with open(FUTURES_CSV, "r", newline="") as f:
        return list(csv.DictReader(f))

def iterate_futures(
    discovery_start: str,
    discovery_end: str,
    only_usdt: bool,
    do_discovery: bool,
    range_days: int,
    max_symbols: int | None,
    run_lunar: bool,
    run_venue: bool,
    run_binance: bool,
    bucket: str,
    binance_datatype: str,
    binance_interval: str,
    save_as_csv: bool,
    save_in_catalog: bool,
    download_if_missing: bool,
) -> Dict[str, Any]:
    logs = []
    def log(msg: str):
        logs.append(msg)

    if do_discovery:
        log(f"[DISCOVERY] {discovery_start} .. {discovery_end} (only_usdt={only_usdt})")
        discover_futures(discovery_start, discovery_end, only_usdt)
        log("[DISCOVERY] fertig.")

    rows = load_futures_csv()
    if not rows:
        return {"error": "Keine Futures CSV gefunden / leer.", "logs": logs}

    # Filter auf Fenster (falls CSV mehr enthält)
    start_dt = datetime.strptime(discovery_start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(discovery_end, "%Y-%m-%d").date()
    filtered = []
    for r in rows:
        try:
            onboard_dt = datetime.strptime(r["onboardDate"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if start_dt <= onboard_dt.date() <= end_dt:
            filtered.append(r)
    if max_symbols:
        filtered = filtered[:max_symbols]

    summaries = []
    log(f"[ITERATION] Symbole: {len(filtered)} (range_days={range_days})")

    for idx, r in enumerate(filtered, 1):
        sym = r["symbol"]
        log(f"[{idx}/{len(filtered)}] Starte {sym}")
        onboard_dt = datetime.strptime(r["onboardDate"], "%Y-%m-%d %H:%M:%S")
        start_day = onboard_dt.date()
        end_day = start_day + timedelta(days=range_days - 1)

        orch = CryptoDataOrchestrator(
            symbol=sym,
            start=start_day.isoformat(),
            end=end_day.isoformat(),
            base_data_dir=str(BASE_DATA_DIR),
            run_lunar=run_lunar,
            run_venue=run_venue,
            run_binance=run_binance,
            lunar_bucket=bucket,
            binance_datatype=binance_datatype,
            binance_interval=binance_interval,
            save_as_csv=save_as_csv,
            save_in_catalog=save_in_catalog,
            download_if_missing=download_if_missing,
        )
        try:
            summary = orch.run()
            summaries.append(summary)
            log(f"[OK] {sym}")
        except Exception as e:
            log(f"[ERROR] {sym}: {e}")

    # Zwischenergebnis speichern
    out_json = BASE_DATA_DIR / "iteration_results.json"
    try:
        with open(out_json, "w", encoding="utf-8") as jf:
            json.dump(summaries, jf, indent=2)
        log(f"[WRITE] iteration_results.json aktualisiert.")
    except Exception as e:
        log(f"[WARN] Konnte iteration_results.json nicht schreiben: {e}")

    return {"summaries": summaries, "logs": logs}

app.layout = html.Div(
    style={"fontFamily": "Arial", "margin": "10px"},
    children=[
        html.H2("Crypto Data Dashboard"),
        html.Hr(),
        html.Div([
            html.H3("Single Orchestrator Run"),
            html.Div([
                html.Label("Symbol (z.B. ETHUSDT-PERP)"),
                dcc.Input(id="single-symbol", type="text", value="ETHUSDT-PERP", style={"width": "200px"}),
                html.Label("Start"),
                dcc.Input(id="single-start", type="text", value=date.today().isoformat(), style={"width": "130px"}),
                html.Label("End"),
                dcc.Input(id="single-end", type="text", value=date.today().isoformat(), style={"width": "130px"}),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
            html.Div([
                dcc.Checklist(
                    id="single-flags",
                    options=[
                        {"label": "Lunar", "value": "lunar"},
                        {"label": "Venue", "value": "venue"},
                        {"label": "Binance", "value": "binance"},
                        {"label": "Save CSV", "value": "csv"},
                        {"label": "Save Catalog", "value": "catalog"},
                    ],
                    value=["lunar", "venue", "binance", "csv", "catalog"],
                    inline=True,
                ),
            ], style={"marginTop": "6px"}),
            html.Div([
                html.Label("Lunar Bucket"),
                dcc.Input(id="single-bucket", type="text", value="hour", style={"width": "80px"}),
                html.Label("Binance Datatype"),
                dcc.Dropdown(
                    id="single-datatype",
                    options=[{"label": "bar", "value": "bar"}, {"label": "tick", "value": "tick"}],
                    value="bar",
                    style={"width": "120px"}
                ),
                html.Label("Interval"),
                dcc.Input(id="single-interval", type="text", value="1h", style={"width": "70px"}),
            ], style={"display": "flex", "gap": "10px", "alignItems": "center", "marginTop": "6px"}),
            html.Button("Run Orchestrator", id="btn-single-run", n_clicks=0, style={"marginTop": "10px"}),
            html.Pre(id="single-output", style={"whiteSpace": "pre-wrap", "background": "#111", "color": "#0f0", "padding": "8px", "minHeight": "140px"}),
        ], style={"border": "1px solid #ccc", "padding": "10px", "borderRadius": "6px"}),

        html.Hr(),

        html.Div([
            html.H3("Iteration (Discovery + Batch Run)"),
            html.Div([
                html.Label("Discovery Start"),
                dcc.Input(id="iter-disc-start", type="text", value=date.today().replace(day=1).isoformat(), style={"width": "130px"}),
                html.Label("Discovery End"),
                dcc.Input(id="iter-disc-end", type="text", value=date.today().isoformat(), style={"width": "130px"}),
                html.Label("Range Days"),
                dcc.Input(id="iter-range-days", type="number", value=1, style={"width": "80px"}),
                html.Label("Max Symbols (leer = alle)"),
                dcc.Input(id="iter-max-symbols", type="number", value=5, style={"width": "100px"}),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
            dcc.Checklist(
                id="iter-options",
                options=[
                    {"label": "Discovery ausführen", "value": "discovery"},
                    {"label": "Nur USDT", "value": "usdt"},
                    {"label": "Lunar", "value": "lunar"},
                    {"label": "Venue", "value": "venue"},
                    {"label": "Binance", "value": "binance"},
                    {"label": "Save CSV", "value": "csv"},
                    {"label": "Save Catalog", "value": "catalog"},
                ],
                value=["discovery", "usdt", "lunar", "venue", "binance", "csv", "catalog"],
                inline=True,
                style={"marginTop": "6px"}
            ),
            html.Div([
                html.Label("Lunar Bucket"),
                dcc.Input(id="iter-bucket", type="text", value="hour", style={"width": "80px"}),
                html.Label("Binance Datatype"),
                dcc.Dropdown(
                    id="iter-datatype",
                    options=[{"label": "bar", "value": "bar"}, {"label": "tick", "value": "tick"}],
                    value="bar",
                    style={"width": "120px"}
                ),
                html.Label("Interval"),
                dcc.Input(id="iter-interval", type="text", value="1h", style={"width": "70px"}),
            ], style={"display": "flex", "gap": "10px", "alignItems": "center", "marginTop": "6px"}),
            html.Button("Run Iteration", id="btn-iter-run", n_clicks=0, style={"marginTop": "10px"}),
            html.Div(id="iter-summary-table"),
            html.Pre(id="iter-log", style={"whiteSpace": "pre-wrap", "background": "#111", "color": "#0ff", "padding": "8px", "minHeight": "180px"}),
        ], style={"border": "1px solid #ccc", "padding": "10px", "borderRadius": "6px", "marginTop": "10px"}),
    ]
)

@app.callback(
    Output("single-output", "children"),
    Input("btn-single-run", "n_clicks"),
    State("single-symbol", "value"),
    State("single-start", "value"),
    State("single-end", "value"),
    State("single-flags", "value"),
    State("single-bucket", "value"),
    State("single-datatype", "value"),
    State("single-interval", "value"),
    prevent_initial_call=True,
)
def run_single(n, symbol, start, end, flags, bucket, datatype, interval):
    if not n:
        return ""
    run_lunar = "lunar" in flags
    run_venue = "venue" in flags
    run_binance = "binance" in flags
    save_csv = "csv" in flags
    save_catalog = "catalog" in flags
    try:
        orch = CryptoDataOrchestrator(
            symbol=symbol,
            start=start,
            end=end,
            base_data_dir=str(BASE_DATA_DIR),
            run_lunar=run_lunar,
            run_venue=run_venue,
            run_binance=run_binance,
            lunar_bucket=bucket,
            binance_datatype=datatype,
            binance_interval=interval,
            save_as_csv=save_csv,
            save_in_catalog=save_catalog,
            download_if_missing=True,
        )
        result = orch.run()
        return _safe_json(result)
    except Exception as e:
        return f"[ERROR] {e}\n{traceback.format_exc()}"

@app.callback(
    Output("iter-log", "children"),
    Output("iter-summary-table", "children"),
    Input("btn-iter-run", "n_clicks"),
    State("iter-disc-start", "value"),
    State("iter-disc-end", "value"),
    State("iter-range-days", "value"),
    State("iter-max-symbols", "value"),
    State("iter-options", "value"),
    State("iter-bucket", "value"),
    State("iter-datatype", "value"),
    State("iter-interval", "value"),
    prevent_initial_call=True,
)
def run_iteration(
    n, disc_start, disc_end, range_days, max_symbols, options,
    bucket, datatype, interval
):
    if not n:
        return "", ""
    try:
        res = iterate_futures(
            discovery_start=disc_start,
            discovery_end=disc_end,
            only_usdt=("usdt" in options),
            do_discovery=("discovery" in options),
            range_days=int(range_days),
            max_symbols=(int(max_symbols) if max_symbols else None),
            run_lunar=("lunar" in options),
            run_venue=("venue" in options),
            run_binance=("binance" in options),
            bucket=bucket,
            binance_datatype=datatype,
            binance_interval=interval,
            save_as_csv=("csv" in options),
            save_in_catalog=("catalog" in options),
            download_if_missing=True,
        )
        logs = "\n".join(res.get("logs", []))
        summaries = res.get("summaries", [])
        if not summaries:
            return logs + "\n[HINWEIS] Keine Summaries.", ""
        # Kleine Tabelle
        table_rows = []
        for s in summaries:
            inp = s.get("input", {})
            lunar_ok = "records" if s.get("results", {}).get("lunar") else "-"
            table_rows.append({
                "symbol": inp.get("symbol_input"),
                "start": inp.get("start"),
                "end": inp.get("end"),
                "lunar_records": s.get("results", {}).get("lunar", {}).get("records", 0),
                "venue_records": s.get("results", {}).get("venue_metrics", {}).get("records", 0),
                "binance_status": s.get("results", {}).get("binance_data", {}).get("status", "-"),
            })
        df_display = pd.DataFrame(table_rows)
        table = dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in df_display.columns],
            data=df_display.to_dict("records"),
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={"fontSize": 12, "padding": "4px"},
        )
        return logs, table
    except Exception as e:
        return f"[ERROR] {e}\n{traceback.format_exc()}", ""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)
