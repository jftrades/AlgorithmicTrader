from dash import Dash
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.visualizing.dashboard.layout import build_layout
from core.visualizing.dashboard.callbacks import register_callbacks
from core.visualizing.dashboard.data_repository import ResultsRepository
from core.visualizing.dashboard.slide_menu import get_best_run_index

RESULTS_DIR = ROOT / "data" / "DATA_STORAGE" / "results"

def create_app():
    # CSS für Dash App konfigurieren
    external_stylesheets = [
        'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap'
    ]
    
    app = Dash(__name__, 
               suppress_callback_exceptions=True,
               external_stylesheets=external_stylesheets)
    
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
                * {
                    box-sizing: border-box;
                }
                
                body {
                    margin: 0;
                    padding: 0;
                    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
                    -webkit-font-smoothing: antialiased;
                    -moz-osx-font-smoothing: grayscale;
                }
                
                .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover {
                    transform: translateY(-2px);
                    transition: all 0.2s ease;
                }
                
                /* Scrollbar Styling */
                ::-webkit-scrollbar {
                    width: 8px;
                }
                
                ::-webkit-scrollbar-track {
                    background: rgba(0,0,0,0.05);
                    border-radius: 4px;
                }
                
                ::-webkit-scrollbar-thumb {
                    background: rgba(102, 126, 234, 0.3);
                    border-radius: 4px;
                }
                
                ::-webkit-scrollbar-thumb:hover {
                    background: rgba(102, 126, 234, 0.5);
                }
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
            menu_open=False
        )
        
    except Exception as e:
        # Harter Abbruch bei Validierungsfehlern
        print(f"[CRITICAL ERROR] {e}")
        raise SystemExit(f"Dashboard startup failed: {e}")

    register_callbacks(app, repo, dash_data)
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="127.0.0.1", port=8050, use_reloader=False)
