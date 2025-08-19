from pathlib import Path
from typing import Optional
import pandas as pd
from dash import html, dcc
from .service import RegimeService

_service: Optional[RegimeService] = None

def build_regime_layout(runs_df: Optional[pd.DataFrame] = None,
                        results_root: Optional[Path] = None,
                        preferred_run: Optional[str] = None,
                        **kwargs):
    global _service
    base_dir = Path(".")
    _service = RegimeService(base_dir)
    _service.load_data()
    return html.Div([
        html.H1("Regime Analyzer (Placeholder)", style={
            'color': '#ffffff',
            'fontSize': '26px',
            'fontWeight': '600',
            'margin': '10px 18px 4px'
        }),
        html.P("No analysis logic present. Implement service + UI.", style={
            'color': '#94a3b8',
            'margin': '0 18px 10px',
            'fontSize': '14px'
        }),
        dcc.Markdown(
            "- Load equity & indicators\n- Merge & compute returns\n- Add regime analysis plots",
            style={
                'color': '#64748b',
                'margin': '0 18px',
                'whiteSpace': 'pre-line',
                'fontSize': '13px'
            }
        )
    ], style={
        'margin': '0',
        'padding': '0',
        'background': 'transparent'
    })

def register_regime_callbacks(app):
    return
