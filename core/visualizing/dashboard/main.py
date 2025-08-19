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
                
                /* FIX: Regime Analyzer Dropdown Styling */
                .regime-dropdown .Select-control {
                    background-color: #374151 !important;
                    border: 1px solid #4b5563 !important;
                    color: #f9fafb !important;
                }
                
                .regime-dropdown .Select-placeholder {
                    color: #9ca3af !important;
                }
                
                .regime-dropdown .Select-value-label,
                .regime-dropdown .Select-single-value {
                    color: #f9fafb !important;
                }
                
                .regime-dropdown .Select-input > input {
                    color: #f9fafb !important;
                }
                
                .regime-dropdown .Select-menu-outer {
                    background: #1f2937 !important;
                    border: 1px solid #4b5563 !important;
                    border-radius: 6px !important;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.35) !important;
                    z-index: 9999 !important;
                }
                
                .regime-dropdown .Select-option {
                    background: #1f2937 !important;
                    color: #f9fafb !important;
                    padding: 10px 14px !important;
                    border-bottom: 1px solid #374151 !important;
                }
                
                .regime-dropdown .Select-option:last-child {
                    border-bottom: none !important;
                }
                
                .regime-dropdown .Select-option.is-focused,
                .regime-dropdown .Select-option:hover {
                    background: #374151 !important;
                }
                
                .regime-dropdown .Select-option.is-selected {
                    background: #4f46e5 !important;
                    color: #fff !important;
                }
                
                .regime-dropdown .Select-control.is-focused {
                    box-shadow: 0 0 0 1px #4f46e5 !important;
                    border: 1px solid #4f46e5 !important;
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

                .run-tools-toolbar {
                    position: relative;
                    z-index: 20000;
                }
                .run-tools-toolbar .Select, 
                .run-tools-toolbar .Select-control {
                    min-height: 30px !important;
                    height: 30px !important;
                    border-radius: 7px !important;
                }
                .run-tools-toolbar .Select-value-label {
                    line-height: 28px !important;
                    font-size: 10.5px !important;
                }
                .run-tools-toolbar .Select-menu-outer,
                .run-tools-toolbar .Select-menu,
                .run-tools-toolbar .SelectMenu,
                .run-tools-toolbar .Select-menu-list {
                    z-index: 21000 !important;
                }
                .run-tools-toolbar .Select-menu-outer {
                    box-shadow: 0 6px 18px -4px rgba(0,0,0,0.18);
                    border: 1px solid #e2e8f0;
                }
                .dash-table-container {
                    position: relative;
                    z-index: 2;
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
            menu_open=False,
            run_id=best_run_id  # ensure layout knows which run folder to use for metrics
        )
        
        # Add dcc.Store for price-chart-mode
        app.layout.children.append(dcc.Store(id="price-chart-mode", data="OHLC"))
        
    except Exception as e:
        # Harter Abbruch bei Validierungsfehlern
        print(f"[CRITICAL ERROR] {e}")
        raise SystemExit(f"Dashboard startup failed: {e}")

    # --- Entferne explizite YAML-Callback-Registrierung ---
    # slide_menu_component = getattr(app.layout, "slide_menu_component", None)
    # if slide_menu_component is not None:
    #     slide_menu_component.viewer.register_callbacks(app)
    # else:
    #     print("[WARN] SlideMenuComponent instance not found for YAML callback registration.")

    register_callbacks(app, repo, dash_data)
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="127.0.0.1", port=8050, use_reloader=False)
