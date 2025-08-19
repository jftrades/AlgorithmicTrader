from pathlib import Path
from typing import List, Tuple, Dict, Optional
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

class RegimeService:
    """Advanced regime analysis service for equity performance vs indicators."""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.results_root = self.base_dir / "data" / "DATA_STORAGE" / "results"
        self.equity_data = None
        self.indicators = {}
        self.merged_data = None
        self.available_runs = []
        self.current_run = None

    def get_available_runs(self) -> List[str]:
        """Get list of available run directories."""
        if not self.results_root.exists():
            return []
        
        runs = []
        for item in self.results_root.iterdir():
            if item.is_dir() and item.name.startswith('run'):
                runs.append(item.name)
        return sorted(runs)

    def load_data(self, run_id: str = "run0") -> bool:
        """Load equity data and all indicators for specified run."""
        print(f"[SERVICE] Loading data for run: {run_id}")
        try:
            self.current_run = run_id
            run_path = self.results_root / run_id / "general" / "indicators"
            print(f"[SERVICE] Run path: {run_path}")
            print(f"[SERVICE] Path exists: {run_path.exists()}")
            
            if not run_path.exists():
                print(f"[SERVICE] Run path does not exist!")
                return False

            # Load equity data
            equity_file = run_path / "total_equity.csv"
            print(f"[SERVICE] Equity file: {equity_file}")
            print(f"[SERVICE] Equity file exists: {equity_file.exists()}")
            
            if equity_file.exists():
                equity_df = pd.read_csv(equity_file)
                print(f"[SERVICE] Raw equity data shape: {equity_df.shape}")
                print(f"[SERVICE] Raw equity columns: {equity_df.columns.tolist()}")
                print(f"[SERVICE] First few equity rows:\n{equity_df.head()}")
                
                equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'], unit='ns')
                equity_df = equity_df.sort_values('timestamp')
                self.equity_data = equity_df[['timestamp', 'value']].rename(columns={'value': 'equity'})
                print(f"[SERVICE] Processed equity data shape: {self.equity_data.shape}")
                print(f"[SERVICE] Equity data date range: {self.equity_data['timestamp'].min()} to {self.equity_data['timestamp'].max()}")
            else:
                print(f"[SERVICE] Equity file not found!")
                return False

            # Load all indicator files
            self.indicators = {}
            csv_files = list(run_path.glob("*.csv"))
            print(f"[SERVICE] Found {len(csv_files)} CSV files in directory")
            
            for csv_file in csv_files:
                if not csv_file.name.startswith('total'):
                    indicator_name = csv_file.stem
                    print(f"[SERVICE] Loading indicator: {indicator_name} from {csv_file.name}")
                    try:
                        df = pd.read_csv(csv_file)
                        print(f"[SERVICE] Raw {indicator_name} shape: {df.shape}")
                        print(f"[SERVICE] Raw {indicator_name} columns: {df.columns.tolist()}")
                        
                        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
                        df = df.sort_values('timestamp')
                        self.indicators[indicator_name] = df[['timestamp', 'value']].rename(
                            columns={'value': indicator_name}
                        )
                        print(f"[SERVICE] Processed {indicator_name} shape: {self.indicators[indicator_name].shape}")
                        print(f"[SERVICE] {indicator_name} date range: {self.indicators[indicator_name]['timestamp'].min()} to {self.indicators[indicator_name]['timestamp'].max()}")
                    except Exception as e:
                        print(f"[SERVICE] Error loading {indicator_name}: {e}")
                        continue

            print(f"[SERVICE] Total indicators loaded: {len(self.indicators)}")
            print(f"[SERVICE] Indicator names: {list(self.indicators.keys())}")
            
            self.create_merged_data()
            return True

        except Exception as e:
            print(f"[SERVICE] Error in load_data: {e}")
            import traceback
            print(f"[SERVICE] Traceback: {traceback.format_exc()}")
            return False

    def create_merged_data(self):
        """Merge equity data with indicators and calculate returns."""
        print(f"[SERVICE] Creating merged data...")
        if self.equity_data is None or not self.indicators:
            print(f"[SERVICE] Cannot merge - equity_data: {self.equity_data is not None}, indicators: {len(self.indicators) if self.indicators else 0}")
            return

        # Start with equity data
        merged = self.equity_data.copy()
        print(f"[SERVICE] Starting with equity data shape: {merged.shape}")
        
        # Calculate returns
        merged['equity_return'] = merged['equity'].pct_change()
        merged['forward_return_1'] = merged['equity'].pct_change().shift(-1)  # Next period return
        merged['forward_return_5'] = merged['equity'].pct_change(5).shift(-5)  # 5-period forward return
        merged['cumulative_return'] = (merged['equity'] / merged['equity'].iloc[0]) - 1
        print(f"[SERVICE] After adding returns, shape: {merged.shape}")

        # Merge each indicator using nearest timestamp matching
        for indicator_name, indicator_df in self.indicators.items():
            print(f"[SERVICE] Merging indicator: {indicator_name}")
            print(f"[SERVICE] Before merge - merged shape: {merged.shape}")
            print(f"[SERVICE] Indicator {indicator_name} shape: {indicator_df.shape}")
            
            merged = pd.merge_asof(
                merged.sort_values('timestamp'),
                indicator_df.sort_values('timestamp'),
                on='timestamp',
                direction='nearest'
            )
            print(f"[SERVICE] After merging {indicator_name}, shape: {merged.shape}")

        print(f"[SERVICE] Before dropna, merged shape: {merged.shape}")
        self.merged_data = merged.dropna()
        print(f"[SERVICE] Final merged data shape: {self.merged_data.shape}")
        print(f"[SERVICE] Final merged data columns: {list(self.merged_data.columns)}")
        print(f"[SERVICE] Sample of merged data:\n{self.merged_data.head()}")

    def get_feature_names(self) -> List[str]:
        """Get list of available indicators."""
        return list(self.indicators.keys()) if self.indicators else []

    def analyze_regime_bins(self, feature: str, n_bins: int = 10, return_type: str = 'forward_return_1') -> Dict:
        """Analyze performance across binned indicator ranges."""
        if self.merged_data is None or feature not in self.merged_data.columns:
            return {}

        data = self.merged_data.dropna(subset=[feature, return_type])
        
        # Create bins with explicit bin edges
        feature_values = data[feature]
        min_val = feature_values.min()
        max_val = feature_values.max()
        
        # Create equally spaced bin edges
        bin_edges = np.linspace(min_val, max_val, n_bins + 1)
        
        # Create bins and get bin labels
        data['feature_bin'] = pd.cut(data[feature], bins=bin_edges, labels=False, include_lowest=True)
        
        # Calculate statistics per bin
        bin_stats = data.groupby('feature_bin').agg({
            return_type: ['mean', 'std', 'count'],
            feature: ['min', 'max', 'mean']
        }).round(4)
        
        bin_stats.columns = ['return_mean', 'return_std', 'count', 'feature_min', 'feature_max', 'feature_mean']
        bin_stats['sharpe'] = (bin_stats['return_mean'] / bin_stats['return_std']).fillna(0)
        bin_stats['win_rate'] = data.groupby('feature_bin')[return_type].apply(lambda x: (x > 0).mean()).round(4)
        
        # Add bin range information
        bin_ranges = []
        for i in range(n_bins):
            if i < len(bin_edges) - 1:
                bin_ranges.append({
                    'bin_id': i,
                    'range_start': bin_edges[i],
                    'range_end': bin_edges[i + 1],
                    'range_label': f"[{bin_edges[i]:.4f}, {bin_edges[i + 1]:.4f}]"
                })
        
        return {
            'bin_stats': bin_stats,
            'raw_data': data,
            'feature_range': (min_val, max_val),
            'bin_edges': bin_edges,
            'bin_ranges': bin_ranges,
            'n_bins': n_bins
        }

    def plot_regime_analysis(self, feature: str, analysis_mode: str = 'bins', 
                           n_bins: int = 10, return_type: str = 'forward_return_1') -> Tuple[go.Figure, go.Figure]:
        """Create regime analysis plots."""
        
        if analysis_mode == 'bins':
            return self._plot_bins_analysis(feature, n_bins, return_type)
        else:
            return self._plot_continuous_analysis(feature, return_type)

    def _plot_bins_analysis(self, feature: str, n_bins: int, return_type: str) -> Tuple[go.Figure, go.Figure]:
        """Create binned regime analysis plots."""
        analysis = self.analyze_regime_bins(feature, n_bins, return_type)
        
        if not analysis:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="No data available", xref="paper", yref="paper", 
                                   x=0.5, y=0.5, showarrow=False)
            return empty_fig, empty_fig

        bin_stats = analysis['bin_stats']
        bin_ranges = analysis['bin_ranges']
        
        # Create clean hover templates with range information
        def create_hover_info(bin_id, value_type):
            if bin_id < len(bin_ranges):
                range_info = bin_ranges[bin_id]
                range_text = range_info['range_label']
                return f'<b>Bin {bin_id}</b><br>Range: {range_text}<br>{value_type}: %{{y}}<extra></extra>'
            else:
                return f'<b>Bin {bin_id}</b><br>{value_type}: %{{y}}<extra></extra>'
        
        # Performance by bins chart
        fig1 = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                f'Average Returns by {feature} Bins',
                f'Win Rate by {feature} Bins', 
                f'Sharpe Ratio by {feature} Bins',
                f'Sample Count by {feature} Bins'
            ),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )

        # Color coding for better visual appeal
        colors = {
            'return': ['#ef4444' if val < 0 else '#10b981' for val in bin_stats['return_mean']],  # Red for negative, green for positive
            'win_rate': '#3b82f6',  # Blue
            'sharpe': ['#ef4444' if val < 0 else '#f59e0b' for val in bin_stats['sharpe']],  # Red for negative, amber for positive
            'count': '#8b5cf6'  # Purple
        }

        # Average Returns - clean bars with color coding
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['return_mean'], 
                name='Avg Return', 
                marker_color=colors['return'],
                hovertemplate='<br>'.join([
                    '<b>Bin %{x}</b>',
                    'Range: ' + (bin_ranges[i]['range_label'] if i < len(bin_ranges) else 'N/A' for i in bin_stats.index).__next__(),
                    'Avg Return: %{y:.6f}',
                    '<extra></extra>'
                ]),
                showlegend=False
            ),
            row=1, col=1
        )

        # Win Rate - clean bars
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['win_rate'], 
                name='Win Rate', 
                marker_color=colors['win_rate'],
                hovertemplate='<br>'.join([
                    '<b>Bin %{x}</b>',
                    'Range: ' + (bin_ranges[i]['range_label'] if i < len(bin_ranges) else 'N/A' for i in bin_stats.index).__next__(),
                    'Win Rate: %{y:.2%}',
                    '<extra></extra>'
                ]),
                showlegend=False
            ),
            row=1, col=2
        )

        # Sharpe Ratio - clean bars with color coding
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['sharpe'], 
                name='Sharpe', 
                marker_color=colors['sharpe'],
                hovertemplate='<br>'.join([
                    '<b>Bin %{x}</b>',
                    'Range: ' + (bin_ranges[i]['range_label'] if i < len(bin_ranges) else 'N/A' for i in bin_stats.index).__next__(),
                    'Sharpe: %{y:.4f}',
                    '<extra></extra>'
                ]),
                showlegend=False
            ),
            row=2, col=1
        )

        # Sample Count - clean bars
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['count'], 
                name='Count', 
                marker_color=colors['count'],
                hovertemplate='<br>'.join([
                    '<b>Bin %{x}</b>',
                    'Range: ' + (bin_ranges[i]['range_label'] if i < len(bin_ranges) else 'N/A' for i in bin_stats.index).__next__(),
                    'Sample Count: %{y}',
                    '<extra></extra>'
                ]),
                showlegend=False
            ),
            row=2, col=2
        )

        # Update layout with cleaner styling
        fig1.update_layout(
            height=600,
            showlegend=False,
            title_text=f"Regime Analysis: {feature} vs {return_type}<br><sub>Feature range: [{analysis['feature_range'][0]:.4f}, {analysis['feature_range'][1]:.4f}], {n_bins} bins</sub>",
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(size=12)
        )

        # Update x-axes to show clean bin labels
        for i in range(1, 3):  # rows
            for j in range(1, 3):  # cols
                fig1.update_xaxes(
                    title_text="Bin",
                    ticktext=[f"{k}" for k in bin_stats.index],
                    tickvals=list(bin_stats.index),
                    row=i, col=j
                )
                fig1.update_yaxes(
                    gridcolor='rgba(128,128,128,0.2)',
                    row=i, col=j
                )

        # Enhanced scatter plot with bin boundaries
        fig2 = go.Figure()
        
        raw_data = analysis['raw_data']
        
        # Add scatter plot with better colors
        fig2.add_trace(go.Scatter(
            x=raw_data[feature],
            y=raw_data[return_type],
            mode='markers',
            marker=dict(
                color=raw_data['feature_bin'],
                colorscale='viridis',  # Better colorscale
                showscale=True,
                colorbar=dict(
                    title="Bin ID",
                    ticktext=[f"Bin {i}" for i in range(n_bins)],
                    tickvals=list(range(n_bins)),
                    x=1.02
                ),
                size=5,
                opacity=0.7,
                line=dict(width=0.5, color='white')
            ),
            name='Data Points',
            hovertemplate='<br>'.join([
                f'<b>{feature}</b>: %{{x:.4f}}',
                f'<b>{return_type}</b>: %{{y:.6f}}',
                'Bin: %{marker.color}',
                '<extra></extra>'
            ])
        ))
        
        # Add vertical lines for bin boundaries with better styling
        bin_edges = analysis['bin_edges']
        for i, edge in enumerate(bin_edges[1:-1], 1):  # Skip first and last edge
            fig2.add_vline(
                x=edge,
                line=dict(color="rgba(128,128,128,0.6)", width=1, dash="dash"),
                annotation=dict(
                    text=f"{edge:.3f}",
                    textangle=90,
                    font=dict(size=10, color="rgba(128,128,128,0.8)"),
                    showarrow=False,
                    xshift=10,
                    yshift=10
                )
            )

        # Add horizontal line at y=0 for returns
        if 'return' in return_type.lower():
            fig2.add_hline(
                y=0,
                line=dict(color="rgba(255,0,0,0.3)", width=1, dash="dot"),
                annotation_text="Break-even",
                annotation_position="bottom right"
            )

        fig2.update_layout(
            title=f'Scatter Plot: {feature} vs {return_type}<br><sub>Dashed lines show bin boundaries</sub>',
            xaxis_title=feature,
            yaxis_title=return_type,
            height=500,
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
            yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
            font=dict(size=12)
        )

        return fig1, fig2

    def _plot_continuous_analysis(self, feature: str, return_type: str) -> Tuple[go.Figure, go.Figure]:
        """Create continuous regime analysis plots."""
        if self.merged_data is None or feature not in self.merged_data.columns:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="No data available", xref="paper", yref="paper", 
                                   x=0.5, y=0.5, showarrow=False)
            return empty_fig, empty_fig

        data = self.merged_data.dropna(subset=[feature, return_type])
        
        # Rolling correlation and performance
        window = min(50, len(data) // 10)  # Adaptive window size
        data = data.sort_values('timestamp')
        data['rolling_corr'] = data[feature].rolling(window).corr(data[return_type])
        
        # Smooth trend analysis
        fig1 = make_subplots(
            rows=3, cols=1,
            subplot_titles=(
                f'{feature} Over Time',
                f'{return_type} Over Time',
                f'Rolling Correlation ({window} periods)'
            ),
            shared_xaxes=True
        )

        # Feature over time
        fig1.add_trace(
            go.Scatter(x=data['timestamp'], y=data[feature], 
                      name=feature, line=dict(color='blue')),
            row=1, col=1
        )

        # Returns over time
        fig1.add_trace(
            go.Scatter(x=data['timestamp'], y=data[return_type], 
                      name={return_type}, line=dict(color='green')),
            row=2, col=1
        )

        # Rolling correlation
        fig1.add_trace(
            go.Scatter(x=data['timestamp'], y=data['rolling_corr'], 
                      name='Rolling Correlation', line=dict(color='red')),
            row=3, col=1
        )

        fig1.update_layout(
            height=700,
            title_text=f"Continuous Analysis: {feature} vs {return_type}",
            paper_bgcolor='white',
            plot_bgcolor='white'
        )

        # Heatmap-style analysis
        fig2 = px.density_heatmap(
            data, x=feature, y=return_type,
            title=f'Density Heatmap: {feature} vs {return_type}',
            color_continuous_scale='RdYlBu_r'
        )
        
        fig2.update_layout(
            height=500,
            paper_bgcolor='white',
            plot_bgcolor='white'
        )

        return fig1, fig2

    def get_performance_summary(self, feature: str, return_type: str = 'forward_return_1') -> Dict:
        """Get overall performance summary for the feature."""
        if self.merged_data is None or feature not in self.merged_data.columns:
            return {}

        data = self.merged_data.dropna(subset=[feature, return_type])
        
        correlation = data[feature].corr(data[return_type])
        
        # Quartile analysis
        quartiles = data[feature].quantile([0.25, 0.5, 0.75])
        q1_returns = data[data[feature] <= quartiles[0.25]][return_type].mean()
        q2_returns = data[(data[feature] > quartiles[0.25]) & (data[feature] <= quartiles[0.5])][return_type].mean()
        q3_returns = data[(data[feature] > quartiles[0.5]) & (data[feature] <= quartiles[0.75])][return_type].mean()
        q4_returns = data[data[feature] > quartiles[0.75]][return_type].mean()

        return {
            'correlation': correlation,
            'total_observations': len(data),
            'feature_range': (data[feature].min(), data[feature].max()),
            'quartile_performance': {
                'Q1 (Low)': q1_returns,
                'Q2': q2_returns, 
                'Q3': q3_returns,
                'Q4 (High)': q4_returns
            }
        }
