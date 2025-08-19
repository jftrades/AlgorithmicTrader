from pathlib import Path
from typing import List, Tuple, Dict, Optional
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from .indicators import IndicatorManager

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
        self.analysis_type = 'crypto'
        self.indicator_manager = None

    def set_analysis_type(self, analysis_type: str):
        """Set the analysis type (index or crypto) for specialized handling."""
        self.analysis_type = analysis_type
        print(f"[SERVICE] Analysis type set to: {analysis_type}")

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
            self.indicator_manager = IndicatorManager(self.results_root)
            
            run_path = self.results_root / run_id / "general" / "indicators"
            if not run_path.exists():
                print(f"[SERVICE] Run path does not exist!")
                return False

            equity_file = run_path / "total_equity.csv"
            if equity_file.exists():
                equity_df = pd.read_csv(equity_file)
                equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'], unit='ns')
                equity_df = equity_df.sort_values('timestamp')
                self.equity_data = equity_df[['timestamp', 'value']].rename(columns={'value': 'equity'})
                print(f"[SERVICE] Processed equity data shape: {self.equity_data.shape}")
            else:
                print(f"[SERVICE] Equity file not found!")
                return False

            all_indicators = self.indicator_manager.load_all_for_analysis_type(run_id, self.analysis_type)
            
            self.indicators = {}
            for indicator_name, indicator_df in all_indicators.items():
                if 'timestamp' in indicator_df.columns and len(indicator_df.columns) >= 2:
                    value_cols = [c for c in indicator_df.columns if c != 'timestamp']
                    if value_cols:
                        main_value_col = value_cols[0]
                        self.indicators[indicator_name] = indicator_df[['timestamp', main_value_col]].rename(
                            columns={main_value_col: indicator_name}
                        )
                        print(f"[SERVICE] Loaded indicator: {indicator_name} ({len(indicator_df)} points)")

            print(f"[SERVICE] Total indicators loaded: {len(self.indicators)}")
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
            return

        merged = self.equity_data.copy()
        equity_values = merged['equity'].values
        
        # Current return (standard)
        merged['equity_return'] = merged['equity'].pct_change()
        
        # Manual calculation for forward returns
        forward_return_1 = np.full(len(equity_values), np.nan)
        for i in range(len(equity_values) - 1):
            if equity_values[i] != 0 and not np.isnan(equity_values[i]) and not np.isnan(equity_values[i + 1]):
                forward_return_1[i] = (equity_values[i + 1] - equity_values[i]) / equity_values[i]
        merged['forward_return_1'] = forward_return_1
        
        forward_return_5 = np.full(len(equity_values), np.nan)
        for i in range(len(equity_values) - 5):
            if equity_values[i] != 0 and not np.isnan(equity_values[i]) and not np.isnan(equity_values[i + 5]):
                forward_return_5[i] = (equity_values[i + 5] - equity_values[i]) / equity_values[i]
        merged['forward_return_5'] = forward_return_5
        
        merged['cumulative_return'] = (merged['equity'] / merged['equity'].iloc[0]) - 1
        merged['equity_base'] = merged['equity']

        # Merge indicators
        for indicator_name, indicator_df in self.indicators.items():
            merged = pd.merge_asof(
                merged.sort_values('timestamp'),
                indicator_df.sort_values('timestamp'),
                on='timestamp',
                direction='nearest'
            )

        self.merged_data = merged.dropna()
        print(f"[SERVICE] Final merged data shape: {self.merged_data.shape}")

    def calculate_forward_return_custom(self, periods: int) -> str:
        """Calculate custom forward return for given periods."""
        if self.merged_data is None:
            return 'forward_return_1'
            
        column_name = f'forward_return_{periods}'
        
        if column_name not in self.merged_data.columns:
            if 'equity_base' in self.merged_data.columns:
                try:
                    print(f"[SERVICE] Computing {column_name} for {periods} periods...")
                    self.merged_data = self.merged_data.copy(deep=True)
                    
                    equity_values = self.merged_data['equity_base'].to_numpy()
                    forward_returns = np.full(len(equity_values), np.nan, dtype='float64')
                    limit = len(equity_values) - periods
                    if periods <= 0:
                        raise ValueError("periods must be > 0")
                    for i in range(limit):
                        cur = equity_values[i]
                        fut = equity_values[i + periods]
                        if cur and not np.isnan(cur) and not np.isnan(fut):
                            forward_returns[i] = (fut - cur) / cur
                    
                    self.merged_data.loc[:, column_name] = forward_returns
                    valid_count = np.isfinite(forward_returns).sum()
                    print(f"[SERVICE] forward_return_custom {periods} bars computed ({valid_count} values)")
                except Exception as e:
                    print(f"[SERVICE] Error calculating {column_name}: {e}")
                    self.merged_data.loc[:, column_name] = self.merged_data.get('forward_return_1', np.nan)
            else:
                return 'forward_return_1'
        
        return column_name

    def get_feature_names(self) -> List[str]:
        """Get list of available indicators."""
        return list(self.indicators.keys()) if self.indicators else []

    def analyze_regime_bins(self, feature: str, n_bins: int = 10, return_type: str = 'forward_return_1', forward_periods: int = 1) -> Dict:
        """Analyze performance across binned indicator ranges."""
        if self.merged_data is None or feature not in self.merged_data.columns:
            return {}

        if return_type == 'forward_return_custom':
            return_type = self.calculate_forward_return_custom(forward_periods)

        data = self.merged_data.dropna(subset=[feature, return_type]).copy()
        
        feature_values = data[feature]
        min_val = feature_values.min()
        max_val = feature_values.max()
        
        try:
            bin_edges = np.linspace(min_val, max_val, n_bins + 1)
            vals = feature_values.to_numpy()
            bin_assignments = np.digitize(vals, bin_edges, right=False) - 1
            bin_assignments = np.clip(bin_assignments, 0, n_bins - 1)
            data.loc[:, 'feature_bin'] = bin_assignments
        except Exception as e:
            print(f"[SERVICE] Error in binning: {e}")
            data.loc[:, 'feature_bin'] = pd.qcut(feature_values, q=min(n_bins, feature_values.nunique()),
                                                 labels=False, duplicates='drop')
            qs = np.linspace(0, 1, n_bins + 1)
            bin_edges = feature_values.quantile(qs).to_numpy()

        try:
            bin_stats = data.groupby('feature_bin').agg({
                return_type: ['mean', 'std', 'count'],
                feature: ['min', 'max', 'mean']
            }).round(4)
            
            bin_stats.columns = ['return_mean', 'return_std', 'count', 'feature_min', 'feature_max', 'feature_mean']
            bin_stats['sharpe'] = (bin_stats['return_mean'] / bin_stats['return_std']).fillna(0)
            bin_stats['win_rate'] = data.groupby('feature_bin')[return_type].apply(lambda x: (x > 0).mean()).round(4)
        except Exception as e:
            print(f"[SERVICE] Error in statistics calculation: {e}")
            return {}
        
        bin_ranges = []
        for i in range(n_bins):
            if i < len(bin_edges) - 1:
                bin_ranges.append({
                    'bin_id': i,
                    'range_start': float(bin_edges[i]),
                    'range_end': float(bin_edges[i + 1]),
                    'range_label': f"[{bin_edges[i]:.4f}, {bin_edges[i + 1]:.4f}]"
                })
        
        return {
            'bin_stats': bin_stats,
            'raw_data': data,
            'feature_range': (min_val, max_val),
            'bin_edges': bin_edges if 'bin_edges' in locals() else np.linspace(min_val, max_val, n_bins + 1),
            'bin_ranges': bin_ranges,
            'n_bins': n_bins
        }

    def plot_regime_analysis(self, feature: str, analysis_mode: str = 'bins', 
                           n_bins: int = 10, return_type: str = 'forward_return_1', 
                           forward_periods: int = 1) -> Tuple[go.Figure, go.Figure]:
        """Create regime analysis plots."""
        if return_type == 'forward_return_custom':
            return_type = self.calculate_forward_return_custom(forward_periods)
        
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
        
        needs_chart_overlay = (
            feature.startswith('chart_') or
            feature.startswith('general_') or
            feature in ['EMA', 'RSI', 'VWAP']
        )
        
        if self.analysis_type == 'index':
            theme_colors = {
                'return': ['#dc2626' if val < 0 else '#16a34a' for val in bin_stats['return_mean']],
                'win_rate': '#1d4ed8',
                'sharpe': ['#dc2626' if val < 0 else '#f59e0b' for val in bin_stats['sharpe']],
                'count': '#7c3aed'
            }
            title_prefix = "Index Analysis"
        else:
            theme_colors = {
                'return': ['#ef4444' if val < 0 else '#10b981' for val in bin_stats['return_mean']],
                'win_rate': '#3b82f6',
                'sharpe': ['#ef4444' if val < 0 else '#f59e0b' for val in bin_stats['sharpe']],
                'count': '#8b5cf6'
            }
            title_prefix = "Crypto Analysis"

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

        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['return_mean'], 
                name='Avg Return', 
                marker_color=theme_colors['return'],
                showlegend=False
            ),
            row=1, col=1
        )

        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['win_rate'], 
                name='Win Rate', 
                marker_color=theme_colors['win_rate'],
                showlegend=False
            ),
            row=1, col=2
        )

        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['sharpe'], 
                name='Sharpe', 
                marker_color=theme_colors['sharpe'],
                showlegend=False
            ),
            row=2, col=1
        )

        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['count'], 
                name='Count', 
                marker_color=theme_colors['count'],
                showlegend=False
            ),
            row=2, col=2
        )

        fig1.update_layout(
            height=600,
            showlegend=False,
            title_text=f"{title_prefix}: {feature} vs {return_type}<br><sub>Feature range: [{analysis['feature_range'][0]:.4f}, {analysis['feature_range'][1]:.4f}], {n_bins} bins</sub>",
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(size=12)
        )

        for i in range(1, 3):
            for j in range(1, 3):
                fig1.update_xaxes(title_text="Bin", row=i, col=j)
                fig1.update_yaxes(gridcolor='rgba(128,128,128,0.2)', row=i, col=j)

        if needs_chart_overlay and self.indicator_manager and self.indicator_manager.price_data is not None:
            fig2 = self._create_price_indicator_overlay(feature, analysis, title_prefix)
        else:
            fig2 = self._create_standard_scatter_plot(feature, return_type, analysis, theme_colors, title_prefix)

        return fig1, fig2

    def _create_price_indicator_overlay(self, feature: str, analysis: Dict, title_prefix: str) -> go.Figure:
        """Create price chart with indicator overlay."""
        price_data = self.indicator_manager.price_data
        raw_data = analysis['raw_data']
        
        fig = make_subplots(
            rows=1, cols=1,
            specs=[[{"secondary_y": True}]],
            subplot_titles=[f'{title_prefix}: {feature} with Price Context']
        )
        
        price_subset = price_data.copy() if price_data is not None else None
        
        if price_subset is not None and len(raw_data) > 0:
            start_time = raw_data['timestamp'].min()
            end_time = raw_data['timestamp'].max()
            
            price_subset = price_subset[
                (price_subset['timestamp'] >= start_time) & 
                (price_subset['timestamp'] <= end_time)
            ]
            
            if len(price_subset) > 0:
                if all(col in price_subset.columns for col in ['open', 'high', 'low', 'close']):
                    fig.add_trace(
                        go.Candlestick(
                            x=price_subset['timestamp'],
                            open=price_subset['open'],
                            high=price_subset['high'],
                            low=price_subset['low'],
                            close=price_subset['close'],
                            name='Price',
                            increasing_line_color='#10b981',
                            decreasing_line_color='#ef4444'
                        ),
                        secondary_y=False
                    )
                else:
                    fig.add_trace(
                        go.Scatter(
                            x=price_subset['timestamp'],
                            y=price_subset['close'],
                            mode='lines',
                            name='Price',
                            line=dict(color='#1f77b4', width=2)
                        ),
                        secondary_y=False
                    )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=raw_data['timestamp'],
                        y=[raw_data[feature].mean()] * len(raw_data),
                        mode='lines',
                        name='No Price Data',
                        line=dict(color='gray', dash='dot')
                    ),
                    secondary_y=False
                )
        else:
            # Generate synthetic price data aligned with indicator timestamps
            synthetic_prices = 50000 + np.random.normal(0, 1000, len(raw_data)).cumsum()
            fig.add_trace(
                go.Scatter(
                    x=raw_data['timestamp'],
                    y=synthetic_prices,
                    mode='lines',
                    name='Synthetic Price',
                    line=dict(color='#1f77b4', width=2, dash='dot'),
                    hovertemplate='<b>Synthetic Price</b>: $%{y:.2f}<br><b>Time</b>: %{x}<extra></extra>',
                    yaxis='y'
                ),
                secondary_y=False
            )
        
        # Add indicator overlay (secondary y-axis with normalized scale)
        indicator_color = '#ff7f0e'  # Orange for indicator
        
        # Customize indicator color and name based on type
        if feature.startswith('general_'):
            indicator_colors = {
                'general_rsi': '#9333ea',      # Purple for RSI
                'general_macd': '#f59e0b',     # Amber for MACD  
                'general_bollinger': '#06b6d4', # Cyan for Bollinger
                'general_sma': '#84cc16',       # Lime for SMA
                'general_ema': '#22c55e',       # Green for EMA
                'general_atr': '#ef4444'        # Red for ATR
            }
            indicator_color = indicator_colors.get(feature, '#ff7f0e')
        elif feature in ['RSI', 'EMA', 'VWAP']:
            csv_colors = {
                'RSI': '#9333ea',    # Purple for RSI
                'EMA': '#22c55e',    # Green for EMA  
                'VWAP': '#06b6d4'    # Cyan for VWAP
            }
            indicator_color = csv_colors.get(feature, '#ff7f0e')
        
        fig.add_trace(
            go.Scatter(
                x=raw_data['timestamp'],
                y=raw_data[feature],
                mode='lines',  # No markers for cleaner look
                name=feature,
                line=dict(color=indicator_color, width=3),
                hovertemplate=f'<b>{feature}</b>: %{{y:.4f}}<br><b>Time</b>: %{{x}}<extra></extra>',
                yaxis='y2'
            ),
            secondary_y=True
        )
        
        # Set y-axis ranges with proper scaling
        if price_subset is not None and len(price_subset) > 0:
            price_range = price_subset['close'].max() - price_subset['close'].min()
            price_margin = price_range * 0.05 if price_range > 0 else 1000
            
            fig.update_yaxes(
                title_text="Price ($)",
                range=[price_subset['close'].min() - price_margin, price_subset['close'].max() + price_margin],
                secondary_y=False,
                side="left"
            )
        else:
            # Default price range
            fig.update_yaxes(
                title_text="Price ($)",
                range=[45000, 55000],
                secondary_y=False,
                side="left"
            )
        
        # Indicator y-axis - with smart range
        indicator_range = raw_data[feature].max() - raw_data[feature].min()
        indicator_margin = indicator_range * 0.05 if indicator_range > 0 else 0.1
        
        fig.update_yaxes(
            title_text=f"{feature}",
            range=[raw_data[feature].min() - indicator_margin, raw_data[feature].max() + indicator_margin],
            secondary_y=True,
            side="right"
        )
        
        # Add bin boundary vertical lines for reference
        bin_edges = analysis.get('bin_edges', [])
        if len(bin_edges) > 2:
            indicator_range = raw_data[feature].max() - raw_data[feature].min()
            for i, edge in enumerate(bin_edges[1:-1], 1):
                # mark horizontal threshold on indicator axis (value)
                fig.add_hline(y=edge, line=dict(color="rgba(128,128,128,0.25)", width=1, dash="dot"),
                              annotation=dict(text=f"Bin {i}", font=dict(size=9), showarrow=False))
        
        fig.update_layout(
            title=f'{title_prefix}: {feature} Indicator with Price Context<br><sub>Dual-axis chart showing price movement and indicator behavior</sub>',
            height=500,
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(gridcolor='rgba(128,128,128,0.2)', title='Time'),
            font=dict(size=12),
            hovermode='x unified',
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(255,255,255,0.8)"
            )
        )
        
        return fig

    def _create_standard_scatter_plot(self, feature: str, return_type: str, analysis: Dict, theme_colors: Dict, title_prefix: str) -> go.Figure:
        """Create standard scatter plot for non-chart indicators."""
        fig = go.Figure()
        raw_data = analysis['raw_data']
        colorscale = 'RdYlGn' if self.analysis_type == 'index' else 'viridis'
        
        fig.add_trace(go.Scatter(
            x=raw_data[feature],
            y=raw_data[return_type],
            mode='markers',
            marker=dict(
                color=raw_data['feature_bin'],
                colorscale=colorscale,
                showscale=True,
                colorbar=dict(title="Bin ID"),
                size=6,
                opacity=0.75
            ),
            name='Observations'
        ))
        
        for edge in analysis['bin_edges'][1:-1]:
            fig.add_vline(x=edge, line=dict(color="rgba(120,120,120,0.5)", width=1, dash="dash"))
        
        if 'return' in return_type.lower():
            fig.add_hline(y=0, line=dict(color="rgba(255,0,0,0.35)", width=1, dash="dot"))

        fig.update_layout(
            title=f"{title_prefix}: {feature} vs {return_type}",
            xaxis_title=feature,
            yaxis_title=return_type,
            paper_bgcolor='white',
            plot_bgcolor='white',
            height=500
        )
        
        return fig

    def _plot_continuous_analysis(self, feature: str, return_type: str) -> Tuple[go.Figure, go.Figure]:
        """Create continuous regime analysis plots."""
        if self.merged_data is None or feature not in self.merged_data.columns:
            empty_fig = go.Figure()
            return empty_fig, empty_fig

        data = self.merged_data.dropna(subset=[feature, return_type]).copy()
        data = data.sort_values('timestamp')

        fig1 = make_subplots(
            rows=2, cols=1,
            subplot_titles=(f'{feature} Over Time', f'{return_type} Over Time'),
            shared_xaxes=True
        )

        fig1.add_trace(
            go.Scatter(x=data['timestamp'], y=data[feature], 
                      name=feature, line=dict(color='blue')),
            row=1, col=1
        )

        fig1.add_trace(
            go.Scatter(x=data['timestamp'], y=data[return_type], 
                      name=return_type, line=dict(color='red')),
            row=2, col=1
        )

        fig1.update_layout(
            height=600,
            title_text=f"Continuous Analysis: {feature} vs {return_type}",
            paper_bgcolor='white'
        )

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=data[feature],
            y=data[return_type],
            mode='markers',
            marker=dict(size=5, opacity=0.6)
        ))

        fig2.update_layout(
            title=f'Correlation: {feature} vs {return_type}',
            xaxis_title=feature,
            yaxis_title=return_type,
            height=500,
            paper_bgcolor='white'
        )

        return fig1, fig2

    def get_performance_summary(self, feature: str, return_type: str = 'forward_return_1', forward_periods: int = 1) -> Dict:
        """Get overall performance summary."""
        if self.merged_data is None or feature not in self.merged_data.columns:
            return {}

        if return_type == 'forward_return_custom':
            return_type = self.calculate_forward_return_custom(forward_periods)

        data = self.merged_data.dropna(subset=[feature, return_type])
        
        if len(data) == 0:
            return {}

        correlation = data[feature].corr(data[return_type])
        quartiles = data[feature].quantile([0.25, 0.5, 0.75])
        
        q1_data = data[data[feature] <= quartiles[0.25]]
        q2_data = data[(data[feature] > quartiles[0.25]) & (data[feature] <= quartiles[0.5])]
        q3_data = data[(data[feature] > quartiles[0.5]) & (data[feature] <= quartiles[0.75])]
        q4_data = data[data[feature] > quartiles[0.75]]
        
        quartile_performance = {
            'Q1 (Low)': q1_data[return_type].mean() if len(q1_data) > 0 else 0,
            'Q2': q2_data[return_type].mean() if len(q2_data) > 0 else 0,
            'Q3': q3_data[return_type].mean() if len(q3_data) > 0 else 0,
            'Q4 (High)': q4_data[return_type].mean() if len(q4_data) > 0 else 0
        }
        
        total_observations = len(data)
        mean_return = data[return_type].mean()
        std_return = data[return_type].std()
        sharpe = mean_return / std_return if std_return != 0 else 0
        win_rate = (data[return_type] > 0).mean()

        return {
            'correlation': correlation,
            'total_observations': total_observations,
            'mean_return': mean_return,
            'std_return': std_return,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate,
            'quartile_performance': quartile_performance,
            'feature_range': (data[feature].min(), data[feature].max()),
            'return_range': (data[return_type].min(), data[return_type].max())
        }
