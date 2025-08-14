from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate

def register_run_selection_callbacks(app, repo, state):
    # Sicherstellen, dass Keys existieren
    state.setdefault("runs_cache", {})
    state.setdefault("active_runs", [])

    @app.callback(
        [
            Output("collector-dropdown", "options"),
            Output("collector-dropdown", "value"),
            Output("selected-run-store", "data")  # jetzt Liste von run_ids
        ],
        Input("runs-table", "selected_rows"),
        State("runs-table", "data"),
        State("collector-dropdown", "value"),  # <- added to preserve selection
        prevent_initial_call=True
    )
    def select_runs(selected_rows, table_data, current_selection):
        if not selected_rows or not table_data:
            raise PreventUpdate
        run_ids = []
        for r in selected_rows:
            if r < len(table_data):
                rid = table_data[r].get("run_id")
                if rid:
                    run_ids.append(str(rid))
        if not run_ids:
            raise PreventUpdate

        # Runs laden & cachen
        first_collectors = {}
        for i, rid in enumerate(run_ids):
            if rid not in state["runs_cache"]:
                try:
                    state["runs_cache"][rid] = repo.load_specific_run(rid)
                except Exception as e:
                    print(f"[ERROR] load run {rid}: {e}")
                    continue
            rd = state["runs_cache"][rid]
            if i == 0:
                first_collectors = rd.collectors or {}
                state["collectors"] = first_collectors
                # Primären Collector neu bestimmen nur wenn nicht gesetzt
                state["selected_collector"] = rd.selected or (next(iter(first_collectors), None))
        state["active_runs"] = run_ids
        state["selected_trade_index"] = None

        options = [{'label': k, 'value': k} for k in state["collectors"]]

        # Normalize current_selection (can be None, str, or list)
        if isinstance(current_selection, str):
            current_selection = [current_selection]
        elif not isinstance(current_selection, list):
            current_selection = []

        # Keep only still-valid selections
        valid_values = {opt['value'] for opt in options}
        preserved = [v for v in current_selection if v in valid_values]

        if preserved:
            value = preserved  # keep user multi-selection
        else:
            # fallback default
            value = [state.get("selected_collector")] if state.get("selected_collector") else []

        return options, value, run_ids
