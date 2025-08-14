from dash import Input, Output, State
from dash.exceptions import PreventUpdate

def register_run_selection_callbacks(app, repo, state):
    @app.callback(
        [
            Output("collector-dropdown", "options"),
            Output("collector-dropdown", "value"),
            Output("selected-run-store", "data")
        ],
        Input("runs-table", "selected_rows"),
        State("runs-table", "data"),
        prevent_initial_call=True
    )
    def select_run_from_table(selected_rows, table_data):
        if not selected_rows or not table_data:
            raise PreventUpdate
        selected_row = table_data[selected_rows[0]]
        run_id = selected_row.get('run_id')
        if not run_id:
            print("[ERROR] run_id missing in selected row")
            raise PreventUpdate
        try:
            run_data = repo.load_specific_run(run_id)
        except Exception as e:
            print(f"[ERROR] load run {run_id}: {e}")
            raise PreventUpdate
        state["collectors"] = run_data.collectors or {}
        state["selected_collector"] = run_data.selected or (next(iter(state["collectors"]), None))
        state["selected_trade_index"] = None
        options = [{'label': k, 'value': k} for k in state["collectors"]]
        value = [state["selected_collector"]] if state["selected_collector"] else []
        return options, value, run_id
