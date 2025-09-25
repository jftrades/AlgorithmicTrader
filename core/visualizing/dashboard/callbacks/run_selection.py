from dash import Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

def register_run_selection_callbacks(app, repo, state):
    state.setdefault("runs_cache", {})
    state.setdefault("active_runs", [])

    @app.callback(
        [
            Output("collector-dropdown", "options"),
            Output("collector-dropdown", "value"),
            Output("selected-run-store", "data", allow_duplicate=True),  # duplicate writer ok
        ],
        [
            Input("runs-table", "selected_rows"),
            Input("runs-table", "active_cell"),    # NEW: detect real user interaction
        ],
        [
            State("runs-table", "data"),
            State("collector-dropdown", "value"),
            State("selected-run-store", "data"),    # current authoritative selection
        ],
        prevent_initial_call=True,
    )
    def select_runs(selected_rows, active_cell, runs_table_data, current_selection_instruments, current_run_store):
        # Guard: Ignore table rebuilds (active_cell None) to avoid overwriting checkbox selections
        if active_cell is None:
            raise PreventUpdate
        if not selected_rows or not runs_table_data:
            raise PreventUpdate

        # Build run_ids from selected rows
        run_ids = []
        for r in selected_rows:
            if isinstance(r, int) and 0 <= r < len(runs_table_data):
                rid = runs_table_data[r].get("run_id")
                if rid:
                    run_ids.append(str(rid))
        if not run_ids:
            raise PreventUpdate

        # Load / cache first run for collectors
        first_collectors = {}
        for i, rid in enumerate(run_ids):
            if rid not in state["runs_cache"]:
                try:
                    state["runs_cache"][rid] = repo.load_specific_run(rid)
                except Exception:
                    continue
            rd = state["runs_cache"][rid]
            if i == 0:
                first_collectors = rd.collectors or {}
                state["collectors"] = first_collectors
                state["selected_collector"] = rd.selected or (next(iter(first_collectors), None))
        state["active_runs"] = run_ids
        state["selected_trade_index"] = None

        options = [{'label': k, 'value': k} for k in state["collectors"]]

        # Preserve existing instrument multi-selection if still valid
        cur = current_selection_instruments
        if isinstance(cur, str):
            cur = [cur]
        if not isinstance(cur, list):
            cur = []
        valid = {o['value'] for o in options}
        preserved = [v for v in cur if v in valid]
        value = preserved if preserved else ([state.get("selected_collector")] if state.get("selected_collector") else [])

        return options, value, run_ids
