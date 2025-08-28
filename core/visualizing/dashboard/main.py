from dash import Dash, dcc
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.visualizing.dashboard.layout import build_layout
from core.visualizing.dashboard.callbacks import register_callbacks
from core.visualizing.dashboard.data_repository import ResultsRepository

RESULTS_DIR = ROOT / "data" / "DATA_STORAGE" / "results"

def launch_dashbaord():
    # CSS für Dash App konfigurieren
    external_stylesheets = [
        'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap'
    ]
    
    app = Dash(
        __name__,
        suppress_callback_exceptions=True,
        external_stylesheets=external_stylesheets,
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1, maximum-scale=1"}],
        title="Algorithmic Trading Dashboard"
    )
    app.title = "Algorithmic Trading Dashboard"
    
    # Custom CSS als String hinzufügen
    app.index_string = '''
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <style>
              body { margin:0; font-family: 'Inter', system-ui, sans-serif; }
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    '''
    
    repo = ResultsRepository(RESULTS_DIR)

    try:
        # Runs validieren und laden (mit strikter Prüfung)
        runs_df = repo.load_validated_runs()
        print(f"[INFO] Loaded {len(runs_df)} validated runs")
        
        # Neu: besten Run über run_id statt run_index
        best_run_row = runs_df.iloc[0]
        best_run_id = str(best_run_row['run_id'])
        print(f"[INFO] Auto-loading best run by run_id: {best_run_id}")
        
        dash_data = repo.load_specific_run(best_run_id)
        
        # Layout mit Slide-Menu erstellen
        app.layout = build_layout(
            collectors=list(dash_data.collectors.keys()),
            selected=dash_data.selected,
            runs_df=runs_df,
            menu_open=False,
            run_id=best_run_id  # ensure layout knows which run folder to use for metrics
        )
        
        # Add dcc.Store for price-chart-mode
        app.layout.children.append(dcc.Store(id="price-chart-mode", data="OHLC"))
        
    except Exception as e:
        # Harter Abbruch bei Validierungsfehlern
        print(f"[CRITICAL ERROR] {e}")
        raise SystemExit(f"Dashboard startup failed: {e}")

    register_callbacks(app, repo, dash_data)
    return app

if __name__ == "__main__":
    app = launch_dashbaord()
    app.run(debug=True, host="127.0.0.1", port=8050, use_reloader=False)
