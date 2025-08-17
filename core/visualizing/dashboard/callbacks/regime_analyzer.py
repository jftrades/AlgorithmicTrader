from dash import Input, Output, State, callback_context, html
from dash.exceptions import PreventUpdate
from pathlib import Path

# NEU: rich placeholder layout importieren
from core.visualizing.dashboard.regime_analyzer.ui import build_regime_layout

def register_regime_analyzer_callbacks(app, repo):
    """
    Register open/close callbacks for the Regime Analyzer fullscreen panel.
    Uses build_regime_layout(...) to render the richer placeholder UI.
    """
    @app.callback(
        Output("regime-analyzer-panel", "style"),
        Output("regime-analyzer-content", "children"),
        Input("regime-analyzer-open-btn", "n_clicks"),
        Input("regime-analyzer-close-btn", "n_clicks"),
        State("regime-analyzer-panel", "style"),
        State("selected-run-store", "data"),        # NEU: aktuell selektierter run_id aus Layout
        prevent_initial_call=True
    )
    def toggle_regime_panel(open_clicks, close_clicks, current_style, selected_run_id):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        style = dict(current_style or {})
        if trigger == "regime-analyzer-close-btn":
            style.update({'display': 'none'})
            return style, None

        if trigger == "regime-analyzer-open-btn":
            try:
                runs_df = repo.load_validated_runs()
            except Exception as e:
                runs_df = None
                # continue; UI will show error below if needed

            # Best-effort: determine results root from repo attributes or fallback to project layout
            results_root = None
            for attr in ('results_dir', 'results_root', 'base_dir', 'root', 'results_path', 'path'):
                if hasattr(repo, attr):
                    try:
                        results_root = Path(getattr(repo, attr))
                        break
                    except Exception:
                        continue
            if results_root is None:
                # fallback (same logic as layout.py)
                results_root = Path(__file__).resolve().parents[3] / "data" / "DATA_STORAGE" / "results"

            # Determine run_id to inspect: prefer selected_run_id store, otherwise first validated run
            run_id_to_use = None
            if selected_run_id:
                # selected_run_id may come as list/tuple (e.g. ['run0']) or single value — pick first element if iterable
                try:
                    if isinstance(selected_run_id, (list, tuple)) and len(selected_run_id) > 0:
                        run_id_to_use = str(selected_run_id[0])
                    else:
                        run_id_to_use = str(selected_run_id)
                except Exception:
                    run_id_to_use = str(selected_run_id)
            elif runs_df is not None and not runs_df.empty:
                # prefer explicit run_id column if available, else use run_index
                candidate = runs_df.iloc[0]
                run_id_to_use = str(candidate.get('run_id') or candidate.get('run_index') or "")

            # DEBUG: print context to console so we know what is passed in
            try:
                print(f"[regime_callback] selected_run_id={selected_run_id!s}, run_id_to_use={run_id_to_use!s}, results_root={results_root!s}")
                if runs_df is not None:
                    print(f"[regime_callback] runs_df.head():\n{runs_df.head(6).to_string()}")
            except Exception:
                pass

            # Pass results_root + preferred run to layout so it can resolve indicators paths correctly
            try:
                layout = build_regime_layout(runs_df, results_root=results_root, preferred_run=run_id_to_use)
                # DEBUG: confirm layout created
                try:
                    print("[regime_callback] build_regime_layout returned layout OK")
                except Exception:
                    pass
            except Exception as e:
                layout = html.Div(f"Failed to build layout: {e}", style={'color': '#f87171'})

            style.update({'display': 'block'})
            return style, layout

        raise PreventUpdate
