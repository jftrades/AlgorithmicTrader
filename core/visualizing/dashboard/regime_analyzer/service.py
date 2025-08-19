from pathlib import Path
from typing import List, Tuple
import plotly.graph_objects as go

class RegimeService:
    """Placeholder skeleton for fresh implementation."""
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.equity_data = None
        self.indicators = {}
        self.merged_data = None

    def load_data(self) -> bool:
        """No loading logic yet."""
        return False

    def create_merged_data(self):
        """Stub."""
        pass

    def get_feature_names(self) -> List[str]:
        return []

    def plot_regime_analysis(self, feature: str) -> Tuple[go.Figure, go.Figure]:
        raise NotImplementedError("Regime analysis not implemented yet")

    def plot_scatter(self, feature: str) -> go.Figure:
        raise NotImplementedError("Scatter plot not implemented yet")
