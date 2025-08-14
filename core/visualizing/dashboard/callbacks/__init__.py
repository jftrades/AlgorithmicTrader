from core.visualizing.dashboard.param_analysis.service import ParameterAnalysisService

from .menu import register_menu_callbacks
from .param_analyzer import register_param_analyzer_callbacks
from .run_selection import register_run_selection_callbacks
from .charts import register_chart_callbacks

def register_callbacks(app, repo, dash_data=None):
    state = {
        "selected_collector": None,
        "selected_trade_index": None,
        "collectors": {},
        "runs_cache": {},       # NEU
        "active_runs": []       # NEU
    }
    if dash_data is not None:
        state["collectors"] = dash_data.collectors or {}
        state["selected_collector"] = dash_data.selected or (next(iter(state["collectors"]), None))
        if getattr(dash_data, "run_id", None):
            rid = str(dash_data.run_id)
            state["runs_cache"][rid] = dash_data
            state["active_runs"] = [rid]

    analysis_service = ParameterAnalysisService()

    register_menu_callbacks(app, repo, state)
    register_param_analyzer_callbacks(app, repo, analysis_service)
    register_run_selection_callbacks(app, repo, state)
    register_chart_callbacks(app, repo, state)
