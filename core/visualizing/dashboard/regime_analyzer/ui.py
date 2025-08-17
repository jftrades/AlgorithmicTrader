from __future__ import annotations

"""
Regime Analyzer UI (Dash)
- Two analysis modes: "bins" (quantile slicing) and "continuous" (smoothed trend)
- Works with CSVs in current directory via service.RegimeService
- Fancy dark UI with cards and responsive layout

Usage (in your Dash app):
    from ui import build_regime_layout, register_regime_callbacks
    app.layout = build_regime_layout()
    register_regime_callbacks(app)

Assumptions:
- A companion `service.py` lives next to this file providing RegimeService
"""

from pathlib import Path
from typing import List, Optional, Dict

from dash import html, dcc, dash_table, Input, Output, State, callback, no_update
import plotly.graph_objects as go

import pandas as pd

# Local service
from . import service

CARD_STYLE = {
    "background": "linear-gradient(135deg,#0b1628,#0e2236)",
    "borderRadius": "14px",
    "padding": "16px",
    "boxShadow": "0 6px 20px rgba(0,0,0,.35)",
    "border": "1px solid rgba(255,255,255,.06)",
}

HEADER_STYLE = {"color": "#e6eef6", "margin": 0}
SUB_STYLE = {"color": "#9fb0c8"}

# Replace single shared service with a small cache keyed by base_dir
_services: Dict[str, service.RegimeService] = {}

def _get_service(base_dir: Optional[Path] = None) -> service.RegimeService:
    """Return (and cache) a RegimeService for given base_dir. If None -> Path('.')."""
    bd = (Path(base_dir) if base_dir is not None else Path(".")).resolve()
    key = str(bd)
    if key not in _services:
        _services[key] = service.RegimeService(base_dir=bd)
    return _services[key]


def build_regime_layout(runs_df: Optional[pd.DataFrame] = None, results_root: Optional[Path] = None, preferred_run: Optional[str] = None, **kwargs) -> html.Div:
    """
    Build the Regime Analyzer layout.

    Optional:
      - runs_df: DataFrame of runs (used to populate run selector options)
      - results_root: optional base folder to resolve relative run paths (e.g. .../data/DATA_STORAGE/results)
      - preferred_run: optional run id to prefer when resolving indicators folder (e.g. "run0")
    NOTE: features are always determined by the RegimeService probing the chosen base_dir.
    """
    # Build run options from runs_df (if provided), else leave empty for manual entry
    run_options = []
    default_run = None
    inferred_base_dir: Optional[Path] = None

    # Normalize results_root to Path if provided
    if results_root is not None:
        try:
            results_root = Path(results_root).resolve()
        except Exception:
            results_root = None

    if runs_df is not None:
        # Helper to produce an indicators-dir path from provided candidate
        def _to_indicators_path(raw: str) -> Optional[Path]:
            if not raw:
                return None
            p = Path(raw)
            # if path already points to indicators dir -> use it
            if p.name.lower() == "indicators" and p.exists():
                return p.resolve()
            # if path points to run folder (results/runX) append general/indicators
            if p.exists() and p.is_dir():
                cand = p / "general" / "indicators"
                if cand.exists():
                    return cand.resolve()
            # if relative string like "results/runX/general/indicators"
            if results_root:
                cand = results_root / raw
                if cand.exists():
                    return cand.resolve()
                # try interpreting raw as run id
                cand2 = results_root / raw / "general" / "indicators"
                if cand2.exists():
                    return cand2.resolve()
            # fallback: try raw as-is
            if p.exists():
                return p.resolve()
            return None

        if 'run_path' in runs_df.columns:
            for idx, p in runs_df['run_path'].astype(str).items():
                ind_dir = _to_indicators_path(p)
                val = str(ind_dir) if ind_dir is not None else p
                run_options.append({'label': str(idx), 'value': val})
            # prefer first resolved run_path as base_dir if found
            try:
                first_raw = str(runs_df['run_path'].astype(str).iloc[0])
                first_ind = _to_indicators_path(first_raw)
                if first_ind is not None:
                    inferred_base_dir = first_ind
            except Exception:
                inferred_base_dir = None

        elif 'indicators_path' in runs_df.columns:
            for idx, p in runs_df['indicators_path'].astype(str).items():
                ind_dir = _to_indicators_path(p)
                val = str(ind_dir) if ind_dir is not None else p
                run_options.append({'label': str(idx), 'value': val})
            try:
                first_raw = str(runs_df['indicators_path'].astype(str).iloc[0])
                first_ind = _to_indicators_path(first_raw)
                if first_ind is not None:
                    inferred_base_dir = first_ind
            except Exception:
                inferred_base_dir = None
        else:
            # Construct values as results_root / run / general / indicators when possible
            for idx in runs_df.index:
                # prefer an explicit run_id column when available (e.g. "run0"), else fall back to index
                run_key = runs_df.loc[idx].get('run_id') if 'run_id' in runs_df.columns else idx
                run_key = str(run_key)
                rel = f"results/{run_key}/general/indicators"
                if results_root:
                    # convert run_key to str before joining with Path
                    cand = results_root / run_key / "general" / "indicators"
                    val = str(cand.resolve()) if cand.exists() else rel
                    if cand.exists() and inferred_base_dir is None:
                        inferred_base_dir = cand.resolve()
                else:
                    val = rel
                run_options.append({'label': run_key, 'value': val})

        if run_options:
            default_run = run_options[0]['value']

    # Determine service base dir: prefer explicit preferred_run under results_root,
    # else inferred_base_dir, else default_run if it points to a real path, else results_root or current dir
    chosen_base = None
    # 1) If caller provided preferred_run and results_root, prefer that indicators folder directly
    try:
        if preferred_run and results_root:
            cand = Path(results_root) / str(preferred_run) / "general" / "indicators"
            if cand.exists() and cand.is_dir():
                chosen_base = cand.resolve()
    except Exception:
        chosen_base = None

    # 2) Fall back to any inferred indicators dir (from runs_df)
    if chosen_base is None and inferred_base_dir is not None:
        chosen_base = inferred_base_dir

    # 3) If default_run string points to an existing path, use it
    if chosen_base is None and default_run:
        try:
            cand = Path(default_run)
            if cand.exists():
                chosen_base = cand.resolve()
            elif results_root:
                # default_run might be a run key, try results_root/run_key/general/indicators
                cand2 = Path(results_root) / str(default_run) / "general" / "indicators"
                if cand2.exists():
                    chosen_base = cand2.resolve()
        except Exception:
            chosen_base = None

    # 4) Last resorts
    if chosen_base is None and results_root:
        chosen_base = results_root
    if chosen_base is None:
        chosen_base = Path(".")

    # DEBUG: log chosen paths so we can inspect in server console
    try:
        print(f"[REGIME_UI] chosen_base={chosen_base!s}, results_root={results_root!s}, inferred_base_dir={inferred_base_dir!s}, default_run={default_run!s}")
    except Exception:
        pass

    # NORMALIZE run_options values to absolute existing paths when possible
    if run_options:
        normalized = []
        for opt in run_options:
            v = opt.get('value')
            try:
                pv = Path(v)
                if not pv.exists() and results_root:
                    # try resolving relative value under results_root
                    cand = results_root / v
                    if cand.exists():
                        opt['value'] = str(cand.resolve())
                    else:
                        # try interpreting v as run id (results_root / run_id / general / indicators)
                        cand2 = results_root / str(v) / "general" / "indicators"
                        if cand2.exists():
                            opt['value'] = str(cand2.resolve())
                else:
                    # make absolute if it exists
                    if pv.exists():
                        opt['value'] = str(pv.resolve())
            except Exception:
                pass
            normalized.append(opt)
        run_options = normalized

    # Ensure the dropdown default uses the resolved chosen_base (so callbacks get correct absolute path)
    try:
        dropdown_default = str(chosen_base.resolve())
    except Exception:
        dropdown_default = default_run

    # ALWAYS fetch features via service for chosen base_dir
    srv = _get_service(base_dir=chosen_base)
    features: List[str] = srv.get_feature_names(silent=True)
    # DEBUG: list features found (printed to server console)
    try:
        print(f"[REGIME_UI] features found: {len(features)} -> {features}")
    except Exception:
        pass

    # QUICK DIAGNOSTICS (lightweight): check discovered files (do NOT call get_dataset here)
    features_info = []
    try:
        eq_file, ind_map, summary_files = srv._discover_files()  # light, safe
    except Exception:
        eq_file, ind_map, summary_files = (None, {}, [])

    # Build lightweight info: feature present (file) and whether equity file exists in this chosen_base
    equity_present = bool(eq_file)
    if features:
        for f in features:
            fn = ind_map.get(f) or next((p for k, p in ind_map.items() if k == f), None)
            file_name = fn.name if fn is not None else "(unknown)"
            features_info.append({"feature": f, "file": file_name})
    # console-friendly summary
    try:
        print(f"[REGIME_UI] lightweight diagnostics: equity_present={equity_present}, indicators={list(ind_map.keys())}, summaries={summary_files}")
    except Exception:
        pass

    # small helper Div to show feature file names under dropdown (insert into layout later)
    if features_info:
        features_info_div = html.Div(
            [html.Span(f"{i['feature']} ({i['file']})", style={'marginRight': '10px', 'color': '#9fb0c8', 'fontSize': '12px'}) for i in features_info],
            style={'marginTop': '8px', 'display': 'flex', 'flexWrap': 'wrap', 'gap': '6px'}
        )
    else:
        # if no features but equity missing, surface helpful hint to user
        if not features and not equity_present:
            features_info_div = html.Div("No equity CSV found in chosen folder — try selecting a run folder.", style={'color': '#fca5a5', 'marginTop': '8px', 'fontSize': '12px'})
        else:
            features_info_div = html.Div()

    # Debug banner when no features found -> help user see which path is probed and what files exist
    debug_banner = None
    if not features:
        try:
            files_here = sorted([str(p.name) for p in Path(chosen_base).glob("*.csv")])
        except Exception:
            files_here = []
        try:
            results_children = []
            if results_root:
                results_children = sorted([str(p.name) for p in Path(results_root).iterdir()][:30])
        except Exception:
            results_children = []
        runs_sample = None
        if runs_df is not None:
            try:
                runs_sample = runs_df.head(5).to_dict()
            except Exception:
                runs_sample = str(runs_df.head(5))

        debug_children = [
            html.Div("No indicators found (debug info):", style={'fontWeight': 700, 'marginBottom': '6px', 'color': '#ffd1d1'}),
            html.Div([
                html.Div(["chosen_base: ", html.Code(str(chosen_base))], style={'marginBottom': '4px'}),
                html.Div(["results_root: ", html.Code(str(results_root))], style={'marginBottom': '6px'}),
                html.Div("CSV files in chosen_base:", style={'fontWeight': 600, 'marginTop': '6px'}),
                html.Pre("\n".join(files_here) or "(none)", style={'fontSize': '12px', 'maxHeight': '140px', 'overflowY': 'auto'}),
                html.Div("Entries under results_root (first-level):", style={'fontWeight': 600, 'marginTop': '6px'}),
                html.Pre("\n".join(results_children) or "(none)", style={'fontSize': '12px', 'maxHeight': '140px', 'overflowY': 'auto'}),
                html.Div("runs_df sample (head):", style={'fontWeight': 600, 'marginTop': '6px'}),
                html.Pre(str(runs_sample) if runs_sample is not None else "(no runs_df)", style={'fontSize': '12px', 'maxHeight': '200px', 'overflowY': 'auto'})
            ], style={'padding': '10px', 'background': '#2b2630', 'borderRadius': '8px', 'color': '#fff'})
        ]
        debug_banner = html.Div(debug_children, style={'border': '1px solid #5b5560', 'padding': '10px', 'borderRadius': '10px', 'marginBottom': '12px', 'background': '#1b1318'})

    return html.Div([
        debug_banner if debug_banner is not None else html.Div(),
        html.Div([
            html.H2("Regime Analyzer", style=HEADER_STYLE),
            html.P("Explore when your strategy performs best/worst, slice by indicators or view continuous trends.", style=SUB_STYLE),
        ], style={"marginBottom": "12px"}),

        # NEW: Run selector (populated by param-analysis or manual entries)
        html.Div([
            html.Div("Run (data folder)", style=SUB_STYLE),
            dcc.Dropdown(
                id="reg-run",
                options=run_options,  # <- may be empty list if runs_df not given
                value=dropdown_default,
                placeholder="Select run folder (or leave to current dir)",
                style={"color": "#0e2236", "minWidth": "240px"},
            ),
            dcc.Store(id="reg-selected-run", data=None)
        ], style={"marginBottom": "10px", "maxWidth": "520px"}),

        # Controls row
        html.Div([
            html.Div([
                html.Div("Mode", style=SUB_STYLE),
                dcc.RadioItems(
                    id="reg-mode",
                    options=[
                        {"label": "Bins (quantiles)", "value": "bins"},
                        {"label": "Continuous", "value": "continuous"},
                    ],
                    value="bins",
                    inputStyle={"marginRight": "6px"},
                    labelStyle={"display": "inline-block", "marginRight": "14px", "color": "#cbd7e6"},
                    style=CARD_STYLE | {"padding": "12px"},
                ),
            ], style={"flex": 1}),

            html.Div([
                html.Div("Feature", style=SUB_STYLE),
                dcc.Dropdown(
                    id="reg-feature",
                    options=[{"label": f, "value": f} for f in features],
                    value=(features[0] if features else None),
                    placeholder="Select indicator",
                    style={"color": "#0e2236"},
                ),
                # insert diagnostics summary right under the feature dropdown
                features_info_div,
            ], style={"flex": 2, "marginLeft": "10px"}),

            html.Div([
                html.Div("2nd Feature (Heatmap)", style=SUB_STYLE),
                dcc.Dropdown(
                    id="reg-feature-2",
                    options=[{"label": f, "value": f} for f in features],
                    placeholder="Optional — for 2D heatmap",
                    style={"color": "#0e2236"},
                ),
            ], style={"flex": 2, "marginLeft": "10px"}),
        ], style={"display": "flex", "flexWrap": "wrap"}),

        html.Div([
            html.Div([
                html.Div("Forward Horizon & Resampling", style=SUB_STYLE),
                html.Div([
                    dcc.Input(id="reg-horizon", type="text", value="1h", debounce=True,
                              placeholder="e.g. 1h, 4h, 1d",
                              style={"width": "120px", "marginRight": "10px"}),
                    dcc.Input(id="reg-dt", type="text", value="5min", debounce=True,
                              placeholder="Δt (e.g. 1min, 5min, 1h)",
                              style={"width": "130px", "marginRight": "10px"}),
                    dcc.Input(id="reg-bins", type="number", value=8, min=3, max=30, step=1,
                              style={"width": "90px"}),
                    html.Button("Reload files", id="reg-reload", n_clicks=0,
                               style={"marginLeft": "10px"}),
                ], style={"marginTop": "6px"}),
            ], style=CARD_STYLE | {"flex": 1}),

            html.Div([
                html.Div("Quality Gates", style=SUB_STYLE),
                dcc.Checklist(
                    id="reg-guards",
                    options=[
                        {"label": " Drop stale values (no long ffill)", "value": "drop_stale"},
                        {"label": " Show support (N) badges", "value": "show_support"},
                        {"label": " Robust stats (median/MAD)", "value": "robust"},
                    ],
                    value=["show_support", "robust"],
                    inputStyle={"marginRight": "6px"},
                    labelStyle={"display": "block", "color": "#cbd7e6"},
                ),
            ], style=CARD_STYLE | {"flex": 1, "marginLeft": "10px"}),
        ], style={"display": "flex", "marginTop": "12px", "flexWrap": "wrap"}),

        # Main visuals
        html.Div([
            html.Div([
                dcc.Loading(dcc.Graph(id="reg-main-graph", figure=go.Figure(), config={"displaylogo": False}), type="circle"),
            ], style=CARD_STYLE | {"flex": 2}),

            html.Div([
                dcc.Loading(dcc.Graph(id="reg-support-graph", figure=go.Figure(), config={"displaylogo": False}), type="circle"),
                html.Div(id="reg-topzones", style={"marginTop": "12px"}),
            ], style=CARD_STYLE | {"flex": 1, "marginLeft": "12px"}),
        ], style={"display": "flex", "marginTop": "14px", "flexWrap": "wrap"}),

        html.Div([
            html.Div([
                html.H4("Bivariate Heatmap (optional)", style=HEADER_STYLE),
                dcc.Loading(dcc.Graph(id="reg-heatmap", figure=go.Figure(), config={"displaylogo": False}), type="circle"),
            ], style=CARD_STYLE),
        ], style={"marginTop": "14px"}),

        # Store to trigger reload actions
        dcc.Store(id="reg-files-version", data=0),
    ])


def register_regime_callbacks(app):
    # NOTE: do not create a single global service here; callbacks will instantiate via _get_service(base_dir)
    @app.callback(
        Output("reg-files-version", "data"),
        Output("reg-feature", "options"),
        Output("reg-feature-2", "options"),
        Input("reg-reload", "n_clicks"),
        Input("reg-run", "value"),
        prevent_initial_call=True,
    )
    def _reload_files(n_clicks, reg_run_value):
        # choose base dir from selection (if provided)
        base_dir = Path(reg_run_value) if reg_run_value else Path(".")
        srv = _get_service(base_dir=base_dir)
        srv.clear_cache()
        feats = srv.get_feature_names(silent=True)
        opts = [{"label": f, "value": f} for f in feats]
        return (pd.Timestamp.utcnow().value, opts, opts)

    @app.callback(
        Output("reg-main-graph", "figure"),
        Output("reg-support-graph", "figure"),
        Output("reg-heatmap", "figure"),
        Output("reg-topzones", "children"),
        Input("reg-files-version", "data"),
        Input("reg-mode", "value"),
        Input("reg-feature", "value"),
        Input("reg-feature-2", "value"),
        Input("reg-horizon", "value"),
        Input("reg-dt", "value"),
        Input("reg-bins", "value"),
        Input("reg-guards", "value"),
        Input("reg-run", "value"),  # new: use selected run for loading data
    )
    def _update_graphs(_, mode, feature, feature2, horizon, dt, n_bins, guards, reg_run_value):
        if not feature:
            return go.Figure(), go.Figure(), go.Figure(), html.Div()

        robust = ("robust" in (guards or []))
        show_support = ("show_support" in (guards or []))
        drop_stale = ("drop_stale" in (guards or []))

        # Resolve base dir for service
        base_dir = Path(reg_run_value) if reg_run_value else Path(".")
        srv = _get_service(base_dir=base_dir)

        # Load merged DF with labels
        df = srv.get_dataset(dt=dt, horizon=horizon, drop_stale=drop_stale)

        # DEBUG: print dataset summary to server console to diagnose empty plots
        try:
            print(f"[REGIME_UI][_update_graphs] srv.base_dir={getattr(srv,'base_dir',None)!s}")
            if df is None:
                print("[REGIME_UI][_update_graphs] df is None (no equity or failed load)")
            else:
                print(f"[REGIME_UI][_update_graphs] df.shape={df.shape}, columns={list(df.columns)}")
                if feature in df.columns:
                    print(f"[REGIME_UI][_update_graphs] non-na counts -> {feature}: {int(df[feature].notna().sum())}, fwd_return: {int(df['fwd_return'].notna().sum())}")
                    try:
                        sample = df[[c for c in (feature, 'fwd_return') if c in df.columns]].dropna().head(8)
                        print("[REGIME_UI][_update_graphs] sample rows:\n" + sample.to_string())
                    except Exception:
                        pass
                else:
                    print(f"[REGIME_UI][_update_graphs] feature '{feature}' not in df.columns")
        except Exception as e:
            try:
                print(f"[REGIME_UI][_update_graphs] debug print failed: {e}")
            except Exception:
                pass

        if df is None:
            # no dataset / no equity found
            diag = srv.get_last_diagnostics()
            msg = html.Div([
                html.H4("No dataset available", style=HEADER_STYLE),
                html.Pre(str(diag))
            ], style={'color': '#f8d7da', 'background': '#2b0b0d', 'padding': '12px', 'borderRadius': '8px'})
            return go.Figure(), go.Figure(), go.Figure(), msg

        if feature not in df.columns:
            diag = srv.get_last_diagnostics()
            msg = html.Div([
                html.H4(f"Feature '{feature}' not found in joined dataset", style=HEADER_STYLE),
                html.Pre(str(diag))
            ], style={'color': '#fef3c7', 'background': '#2f2a10', 'padding': '12px', 'borderRadius': '8px'})
            return go.Figure(), go.Figure(), go.Figure(), msg

        # quick check: if no rows where both feature and fwd_return are present -> diagnostic
        d = df[[feature, "fwd_return"]].dropna()
        if d.empty:
            diag = srv.get_last_diagnostics()
            note = [
                html.P("No overlapping samples between selected feature and forward-return. Possible causes:", style={'margin': 0}),
                html.Ol([
                    html.Li("Wrong 'reg-run' (base dir) — UI may point to results root instead of run indicators."),
                    html.Li("No temporal overlap between equity timestamps and indicator timestamps."),
                    html.Li("Indicators contain only NaNs or were skipped due to bad CSV format.")
                ], style={'marginTop': '6px'}),
                html.H5("Diagnostics", style={'marginTop': '8px'}),
                html.Pre(str(diag), style={'whiteSpace': 'pre-wrap', 'fontSize': '12px'})
            ]
            diag_div = html.Div(note, style={'color': '#fff', 'background': '#2b2f36', 'padding': '12px', 'borderRadius': '8px'})
            return go.Figure(), go.Figure(), go.Figure(), diag_div

        if mode == "bins":
            main_fig, support_fig, zones_df = srv.fig_bins(df, feature=feature, n_bins=int(n_bins or 8), robust=robust, show_support=show_support)
        else:
            main_fig, support_fig, zones_df = srv.fig_continuous(df, feature=feature, robust=robust, show_support=show_support)

        heatmap_fig = go.Figure()
        if feature2 and feature2 != feature and feature2 in df.columns:
            heatmap_fig = srv.fig_heatmap(df, feature_x=feature, feature_y=feature2, bins=int(n_bins or 8), robust=robust)

        # Top zones table (if available)
        top_component = html.Div()
        if zones_df is not None and not zones_df.empty:
            # Convert to nice table
            cols = [
                {"name": "zone", "id": "zone"},
                {"name": "median_return", "id": "median_return"},
                {"name": "hit_rate", "id": "hit_rate"},
                {"name": "N", "id": "N"},
            ]
            dash_tbl = dash_table.DataTable(
                zones_df.to_dict("records"),
                columns=cols,
                style_header={"backgroundColor": "#102238", "color": "#cbd7e6", "border": "0"},
                style_cell={"backgroundColor": "#0c1b2e", "color": "#e6eef6", "border": "0", "padding": "8px"},
                style_as_list_view=True,
                page_size=10,
            )
            top_component = html.Div([
                html.H4("Top Zones (draft rules)", style=HEADER_STYLE),
                dash_tbl
            ])

        return main_fig, support_fig, heatmap_fig, top_component
