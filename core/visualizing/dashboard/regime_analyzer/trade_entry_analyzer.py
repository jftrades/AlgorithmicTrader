from pathlib import Path
from typing import List, Tuple, Dict, Optional
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

class TradeEntryAnalyzer:
    """Advanced trade entry analysis - correlates entry features with trade PnL outcomes."""
    
    def __init__(self, results_root: Path):
        self.results_root = Path(results_root)
        self.trades_data = None
        self.indicators = {}
        self.merged_trade_data = None
        self.current_run = None
        
    def load_trades_data(self, run_id: str) -> bool:
        """Load all trades data from different instruments/folders for specified run."""
        print(f"[TRADE_ENTRY] Loading trades data for run: {run_id}")
        
        try:
            self.current_run = run_id
            run_path = self.results_root / run_id
            
            if not run_path.exists():
                print(f"[TRADE_ENTRY] Run path does not exist: {run_path}")
                return False
            
            # Find all non-general directories (instruments)
            instrument_dirs = []
            for item in run_path.iterdir():
                if item.is_dir() and item.name != 'general':
                    instrument_dirs.append(item)
            
            print(f"[TRADE_ENTRY] Found {len(instrument_dirs)} instrument directories: {[d.name for d in instrument_dirs]}")
            
            # Load trades from each instrument
            all_trades = []
            for instrument_dir in instrument_dirs:
                trades_file = instrument_dir / "trades.csv"
                if trades_file.exists():
                    try:
                        trades_df = pd.read_csv(trades_file)
                        print(f"[TRADE_ENTRY] Loaded {len(trades_df)} trades from {instrument_dir.name}")
                        
                        # Add instrument info
                        trades_df['instrument'] = instrument_dir.name
                        
                        # Convert timestamps
                        trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'], unit='ns')
                        trades_df['closed_timestamp'] = pd.to_datetime(trades_df['closed_timestamp'], unit='ns')
                        
                        # Clean PnL (remove 'USDT' suffix and convert to float)
                        trades_df['realized_pnl_clean'] = trades_df['realized_pnl'].str.replace(' USDT', '').astype(float)
                        
                        # Only keep relevant columns for analysis
                        trades_clean = trades_df[['timestamp', 'realized_pnl_clean', 'instrument', 'action', 'tradesize', 'id']].copy()
                        trades_clean = trades_clean.rename(columns={'timestamp': 'entry_timestamp', 'realized_pnl_clean': 'trade_pnl'})
                        
                        all_trades.append(trades_clean)
                        print(f"[TRADE_ENTRY] Sample from {instrument_dir.name}:")
                        print(trades_clean.head(2))
                        
                    except Exception as e:
                        print(f"[TRADE_ENTRY] Error loading trades from {instrument_dir.name}: {e}")
                        continue
                else:
                    print(f"[TRADE_ENTRY] No trades.csv found in {instrument_dir.name}")
            
            if not all_trades:
                print(f"[TRADE_ENTRY] No trade data found!")
                return False
                
            # Combine all trades
            self.trades_data = pd.concat(all_trades, ignore_index=True)
            self.trades_data = self.trades_data.sort_values('entry_timestamp').reset_index(drop=True)
            
            print(f"[TRADE_ENTRY] Total trades loaded: {len(self.trades_data)}")
            print(f"[TRADE_ENTRY] PnL range: {self.trades_data['trade_pnl'].min():.2f} to {self.trades_data['trade_pnl'].max():.2f}")
            print(f"[TRADE_ENTRY] Date range: {self.trades_data['entry_timestamp'].min()} to {self.trades_data['entry_timestamp'].max()}")
            print(f"[TRADE_ENTRY] Actions: {self.trades_data['action'].value_counts().to_dict()}")
            
            return True
            
        except Exception as e:
            print(f"[TRADE_ENTRY] Error in load_trades_data: {e}")
            import traceback
            print(f"[TRADE_ENTRY] Traceback: {traceback.format_exc()}")
            return False
    
    def load_indicators_data(self, run_id: str) -> bool:
        """Load indicator data for feature matching."""
        print(f"[TRADE_ENTRY] Loading indicators data for run: {run_id}")
        
        try:
            indicators_path = self.results_root / run_id / "general" / "indicators"
            
            if not indicators_path.exists():
                print(f"[TRADE_ENTRY] Indicators path does not exist: {indicators_path}")
                return False
            
            self.indicators = {}
            csv_files = list(indicators_path.glob("*.csv"))
            print(f"[TRADE_ENTRY] Found {len(csv_files)} indicator files")
            
            for csv_file in csv_files:
                if not csv_file.name.startswith('total'):
                    indicator_name = csv_file.stem
                    try:
                        df = pd.read_csv(csv_file)
                        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
                        df = df.sort_values('timestamp')
                        self.indicators[indicator_name] = df[['timestamp', 'value']].rename(
                            columns={'value': indicator_name}
                        )
                        print(f"[TRADE_ENTRY] Loaded indicator: {indicator_name} ({len(df)} points)")
                    except Exception as e:
                        print(f"[TRADE_ENTRY] Error loading indicator {indicator_name}: {e}")
                        continue
            
            print(f"[TRADE_ENTRY] Total indicators loaded: {len(self.indicators)}")
            return True
            
        except Exception as e:
            print(f"[TRADE_ENTRY] Error loading indicators: {e}")
            return False
    
    def create_trade_feature_data(self) -> bool:
        """Merge trade entries with indicator values at entry timestamp."""
        print(f"[TRADE_ENTRY] Creating trade-feature merged data...")
        
        if self.trades_data is None or not self.indicators:
            print(f"[TRADE_ENTRY] Cannot merge - trades: {self.trades_data is not None}, indicators: {len(self.indicators)}")
            return False
        
        # Start with trades data
        merged = self.trades_data.copy()
        print(f"[TRADE_ENTRY] Starting with {len(merged)} trades")
        
        # Add some derived trade metrics
        merged['is_profitable'] = merged['trade_pnl'] > 0
        merged['pnl_abs'] = merged['trade_pnl'].abs()
        merged['pnl_category'] = pd.cut(
            merged['trade_pnl'], 
            bins=[-np.inf, -100, 0, 100, np.inf], 
            labels=['Big Loss', 'Small Loss', 'Small Win', 'Big Win']
        )
        
        # Merge each indicator using nearest timestamp matching to entry_timestamp
        for indicator_name, indicator_df in self.indicators.items():
            print(f"[TRADE_ENTRY] Merging indicator: {indicator_name}")
            print(f"[TRADE_ENTRY] Before merge - trades: {len(merged)}")
            
            merged = pd.merge_asof(
                merged.sort_values('entry_timestamp'),
                indicator_df.sort_values('timestamp'),
                left_on='entry_timestamp',
                right_on='timestamp',
                direction='nearest'
            )
            print(f"[TRADE_ENTRY] After merging {indicator_name}: {len(merged)} trades")
        
        # Remove rows with missing indicator data
        before_dropna = len(merged)
        self.merged_trade_data = merged.dropna()
        after_dropna = len(self.merged_trade_data)
        
        print(f"[TRADE_ENTRY] Dropped {before_dropna - after_dropna} trades with missing data")
        print(f"[TRADE_ENTRY] Final merged dataset: {len(self.merged_trade_data)} trades")
        print(f"[TRADE_ENTRY] Columns: {list(self.merged_trade_data.columns)}")
        
        if len(self.merged_trade_data) > 0:
            print(f"[TRADE_ENTRY] Sample merged data:")
            sample_cols = ['entry_timestamp', 'trade_pnl', 'action', 'is_profitable'] + list(self.indicators.keys())[:2]
            print(self.merged_trade_data[sample_cols].head(3))
            return True
        
        return False
    
    def get_available_features(self) -> List[str]:
        """Get list of available indicator features."""
        return list(self.indicators.keys()) if self.indicators else []
    
    def analyze_trade_entry_bins(self, feature: str, n_bins: int = 10) -> Dict:
        """Analyze trade performance across binned feature ranges at entry."""
        if self.merged_trade_data is None or feature not in self.merged_trade_data.columns:
            return {}
        
        data = self.merged_trade_data.dropna(subset=[feature, 'trade_pnl']).copy()
        
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
            'trade_pnl': ['mean', 'std', 'count', 'sum'],
            'is_profitable': ['mean', 'count'],
            feature: ['min', 'max', 'mean'],
            'pnl_abs': 'mean'
        }).round(4)
        
        # Flatten column names
        bin_stats.columns = ['avg_pnl', 'pnl_std', 'trade_count', 'total_pnl', 'win_rate', 'profitable_count', 
                            'feature_min', 'feature_max', 'feature_mean', 'avg_abs_pnl']
        
        # Calculate additional metrics
        bin_stats['sharpe'] = (bin_stats['avg_pnl'] / bin_stats['pnl_std']).fillna(0)
        
        # FIX: Simplified profit factor calculation without include_groups (for older pandas versions)
        profit_factors = []
        for bin_id in bin_stats.index:
            bin_data = data[data['feature_bin'] == bin_id]
            wins = bin_data[bin_data['trade_pnl'] > 0]['trade_pnl'].sum()
            losses = abs(bin_data[bin_data['trade_pnl'] <= 0]['trade_pnl'].sum())
            pf = wins / losses if losses != 0 else np.inf
            profit_factors.append(pf)
        
        bin_stats['profit_factor'] = profit_factors
        
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
        
        print(f"[DEBUG] Trade entry bin_stats created with columns: {list(bin_stats.columns)}")
        print(f"[DEBUG] Trade entry bin_stats sample:\n{bin_stats.head()}")
        
        return {
            'bin_stats': bin_stats,
            'raw_data': data,
            'feature_range': (min_val, max_val),
            'bin_edges': bin_edges,
            'bin_ranges': bin_ranges,
            'n_bins': n_bins
        }
    
    def plot_trade_entry_analysis(self, feature: str, analysis_mode: str = 'bins', n_bins: int = 10) -> Tuple[go.Figure, go.Figure]:
        """Create trade entry analysis plots."""
        
        if analysis_mode == 'bins':
            return self._plot_trade_bins_analysis(feature, n_bins)
        else:
            return self._plot_trade_continuous_analysis(feature)
    
    def _plot_trade_bins_analysis(self, feature: str, n_bins: int) -> Tuple[go.Figure, go.Figure]:
        """Create binned trade entry analysis plots."""
        analysis = self.analyze_trade_entry_bins(feature, n_bins)
        
        if not analysis:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="No trade data available", xref="paper", yref="paper", 
                                   x=0.5, y=0.5, showarrow=False)
            return empty_fig, empty_fig
        
        bin_stats = analysis['bin_stats']
        bin_ranges = analysis['bin_ranges']
        
        # Performance by bins chart
        fig1 = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                f'Average PnL by {feature} Entry Bins',
                f'Win Rate by {feature} Entry Bins', 
                f'Total PnL by {feature} Entry Bins',
                f'Trade Count by {feature} Entry Bins'
            ),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )
        
        # Color coding for trade performance
        colors = {
            'avg_pnl': ['#ef4444' if val < 0 else '#10b981' for val in bin_stats['avg_pnl']],
            'win_rate': '#3b82f6',
            'total_pnl': ['#ef4444' if val < 0 else '#10b981' for val in bin_stats['total_pnl']],
            'count': '#8b5cf6'
        }
        
        # Create hover templates correctly - fix the Series issue
        def create_hover_template_with_range(bin_id, metric_name, value_format):
            """Create hover template with correct range lookup."""
            if bin_id < len(bin_ranges):
                range_label = bin_ranges[bin_id]['range_label']
                return f'<b>Bin {bin_id}</b><br>Range: {range_label}<br>{metric_name}: %{{y{value_format}}}<extra></extra>'
            else:
                return f'<b>Bin {bin_id}</b><br>{metric_name}: %{{y{value_format}}}<extra></extra>'
        
        # Average PnL per trade - fixed hover
        hover_templates_avg_pnl = [create_hover_template_with_range(i, 'Avg PnL', ':.2f') for i in bin_stats.index]
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['avg_pnl'], 
                name='Avg PnL', 
                marker_color=colors['avg_pnl'],
                hovertemplate=[hover_templates_avg_pnl[i] if i < len(hover_templates_avg_pnl) else f'<b>Bin {bin_stats.index[i]}</b><br>Avg PnL: %{{y:.2f}}<extra></extra>' for i in range(len(bin_stats.index))],
                showlegend=False
            ),
            row=1, col=1
        )
        
        # Win Rate - fixed hover
        hover_templates_win_rate = [create_hover_template_with_range(i, 'Win Rate', ':.2%') for i in bin_stats.index]
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['win_rate'], 
                name='Win Rate', 
                marker_color=colors['win_rate'],
                hovertemplate=[hover_templates_win_rate[i] if i < len(hover_templates_win_rate) else f'<b>Bin {bin_stats.index[i]}</b><br>Win Rate: %{{y:.2%}}<extra></extra>' for i in range(len(bin_stats.index))],
                showlegend=False
            ),
            row=1, col=2
        )
        
        # Total PnL - fixed hover
        hover_templates_total_pnl = [create_hover_template_with_range(i, 'Total PnL', ':.2f') for i in bin_stats.index]
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['total_pnl'], 
                name='Total PnL', 
                marker_color=colors['total_pnl'],
                hovertemplate=[hover_templates_total_pnl[i] if i < len(hover_templates_total_pnl) else f'<b>Bin {bin_stats.index[i]}</b><br>Total PnL: %{{y:.2f}}<extra></extra>' for i in range(len(bin_stats.index))],
                showlegend=False
            ),
            row=2, col=1
        )
        
        # Trade Count - fixed hover
        hover_templates_count = [create_hover_template_with_range(i, 'Trade Count', '') for i in bin_stats.index]
        fig1.add_trace(
            go.Bar(
                x=bin_stats.index, 
                y=bin_stats['trade_count'], 
                name='Trade Count', 
                marker_color=colors['count'],
                hovertemplate=[hover_templates_count[i] if i < len(hover_templates_count) else f'<b>Bin {bin_stats.index[i]}</b><br>Trade Count: %{{y}}<extra></extra>' for i in range(len(bin_stats.index))],
                showlegend=False
            ),
            row=2, col=2
        )
        
        fig1.update_layout(
            height=600,
            showlegend=False,
            title_text=f"Trade Entry Analysis: {feature} Entry Values vs Trade Outcomes<br><sub>Feature range: [{analysis['feature_range'][0]:.4f}, {analysis['feature_range'][1]:.4f}], {n_bins} bins</sub>",
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(size=12)
        )
        
        # Update axes
        for i in range(1, 3):
            for j in range(1, 3):
                fig1.update_xaxes(
                    title_text="Entry Bin",
                    ticktext=[f"{k}" for k in bin_stats.index],
                    tickvals=list(bin_stats.index),
                    row=i, col=j
                )
                fig1.update_yaxes(
                    gridcolor='rgba(128,128,128,0.2)',
                    row=i, col=j
                )
        
        # Scatter plot: Entry Feature vs Trade PnL - FIX: Match bar chart colors
        fig2 = go.Figure()
        
        raw_data = analysis['raw_data']
        
        # FIX: Use consistent color mapping - green for profitable, red for losses (same as bars)
        scatter_colors = ['#10b981' if profitable else '#ef4444' for profitable in raw_data['is_profitable']]
        
        fig2.add_trace(go.Scatter(
            x=raw_data[feature],
            y=raw_data['trade_pnl'],
            mode='markers',
            marker=dict(
                color=scatter_colors,  # FIX: Use explicit colors instead of colorscale
                showscale=False,  # FIX: Remove colorscale since we use explicit colors
                size=6,
                opacity=0.7,
                line=dict(width=0.5, color='white')
            ),
            name='Trades',
            text=raw_data['action'],
            customdata=raw_data['is_profitable'],  # Store for hover
            hovertemplate='<br>'.join([
                f'<b>Entry {feature}</b>: %{{x:.4f}}',
                f'<b>Trade PnL</b>: %{{y:.2f}} USDT',
                '<b>Action</b>: %{text}',
                '<b>Result</b>: %{customdata}',  # Show profitable/loss
                '<extra></extra>'
            ])
        ))
        
        # Add custom legend for colors
        fig2.add_trace(go.Scatter(
            x=[None], y=[None],
            mode='markers',
            marker=dict(color='#10b981', size=8),
            name='Profitable Trades',
            showlegend=True
        ))
        
        fig2.add_trace(go.Scatter(
            x=[None], y=[None],
            mode='markers',
            marker=dict(color='#ef4444', size=8),
            name='Loss Trades',
            showlegend=True
        ))
        
        # Add bin boundary lines
        bin_edges = analysis['bin_edges']
        for i, edge in enumerate(bin_edges[1:-1], 1):
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
        
        # Add horizontal line at PnL=0
        fig2.add_hline(
            y=0,
            line=dict(color="rgba(255,0,0,0.3)", width=2, dash="dot"),
            annotation_text="Break-even",
            annotation_position="bottom right"
        )
        
        fig2.update_layout(
            title=f'Trade Scatter: Entry {feature} vs Trade PnL<br><sub>Each dot = one trade. Dashed lines = bin boundaries</sub>',
            xaxis_title=f'Entry {feature}',
            yaxis_title='Trade PnL (USDT)',
            height=500,
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
            yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
            font=dict(size=12)
        )
        
        return fig1, fig2
    
    def _plot_trade_continuous_analysis(self, feature: str) -> Tuple[go.Figure, go.Figure]:
        """Create continuous trade entry analysis plots."""
        if self.merged_trade_data is None or feature not in self.merged_trade_data.columns:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="No trade data available", xref="paper", yref="paper", 
                                   x=0.5, y=0.5, showarrow=False)
            return empty_fig, empty_fig
        
        data = self.merged_trade_data.dropna(subset=[feature, 'trade_pnl']).copy()
        data = data.sort_values('entry_timestamp')
        
        # Rolling metrics
        window = min(50, len(data) // 10)
        data['rolling_avg_pnl'] = data['trade_pnl'].rolling(window, min_periods=1).mean()
        data['rolling_win_rate'] = data['is_profitable'].rolling(window, min_periods=1).mean()
        data['rolling_feature_corr'] = data[feature].rolling(window).corr(data['trade_pnl'])
        
        # Time series analysis
        fig1 = make_subplots(
            rows=4, cols=1,
            subplot_titles=(
                f'{feature} at Entry Over Time',
                f'Trade PnL Over Time',
                f'Rolling Average PnL ({window} trades)',
                f'Rolling Feature-PnL Correlation ({window} trades)'
            ),
            shared_xaxes=True
        )
        
        # Feature values over time
        fig1.add_trace(
            go.Scatter(x=data['entry_timestamp'], y=data[feature], 
                      name=f'Entry {feature}', line=dict(color='blue'), mode='markers+lines', marker=dict(size=3)),
            row=1, col=1
        )
        
        # Individual trade PnLs
        colors = ['green' if pnl > 0 else 'red' for pnl in data['trade_pnl']]
        fig1.add_trace(
            go.Scatter(x=data['entry_timestamp'], y=data['trade_pnl'], 
                      name='Trade PnL', mode='markers', 
                      marker=dict(color=colors, size=5, opacity=0.6)),
            row=2, col=1
        )
        
        # Rolling average PnL
        fig1.add_trace(
            go.Scatter(x=data['entry_timestamp'], y=data['rolling_avg_pnl'], 
                      name=f'Rolling Avg PnL', line=dict(color='purple', width=2)),
            row=3, col=1
        )
        
        # Rolling correlation
        fig1.add_trace(
            go.Scatter(x=data['entry_timestamp'], y=data['rolling_feature_corr'], 
                      name='Feature-PnL Correlation', line=dict(color='orange', width=2)),
            row=4, col=1
        )
        
        # Add zero lines
        for row in [2, 3, 4]:
            fig1.add_hline(y=0, line=dict(color="rgba(128,128,128,0.3)", width=1, dash="dash"), row=row, col=1)
        
        fig1.update_layout(
            height=800,
            title_text=f"Continuous Trade Analysis: {feature} Entry Values vs Trade Outcomes Over Time",
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(size=12)
        )
        
        # Update y-axes
        for i in range(1, 5):
            fig1.update_yaxes(gridcolor='rgba(128,128,128,0.2)', row=i, col=1)
        fig1.update_xaxes(gridcolor='rgba(128,128,128,0.2)', row=4, col=1)
        
        # 2D density heatmap of feature vs PnL
        fig2 = px.density_heatmap(
            data, x=feature, y='trade_pnl',
            title=f'Entry {feature} vs Trade PnL Density',
            color_continuous_scale='RdYlBu_r',
            labels={feature: f'Entry {feature}', 'trade_pnl': 'Trade PnL (USDT)'}
        )
        
        fig2.update_layout(
            height=500,
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(size=12)
        )
        
        return fig1, fig2
    
    def get_trade_performance_summary(self, feature: str) -> Dict:
        """Get overall trade performance summary for the feature."""
        if self.merged_trade_data is None or feature not in self.merged_trade_data.columns:
            return {}
        
        data = self.merged_trade_data.dropna(subset=[feature, 'trade_pnl'])
        
        correlation = data[feature].corr(data['trade_pnl'])
        
        # Quartile analysis for entry features
        quartiles = data[feature].quantile([0.25, 0.5, 0.75])
        q1_pnl = data[data[feature] <= quartiles[0.25]]['trade_pnl'].mean()
        q2_pnl = data[(data[feature] > quartiles[0.25]) & (data[feature] <= quartiles[0.5])]['trade_pnl'].mean()
        q3_pnl = data[(data[feature] > quartiles[0.5]) & (data[feature] <= quartiles[0.75])]['trade_pnl'].mean()
        q4_pnl = data[data[feature] > quartiles[0.75]]['trade_pnl'].mean()
        
        # Quartile win rates
        q1_wr = data[data[feature] <= quartiles[0.25]]['is_profitable'].mean()
        q2_wr = data[(data[feature] > quartiles[0.25]) & (data[feature] <= quartiles[0.5])]['is_profitable'].mean()
        q3_wr = data[(data[feature] > quartiles[0.5]) & (data[feature] <= quartiles[0.75])]['is_profitable'].mean()
        q4_wr = data[data[feature] > quartiles[0.75]]['is_profitable'].mean()
        
        return {
            'correlation': correlation,
            'total_trades': len(data),
            'total_pnl': data['trade_pnl'].sum(),
            'overall_win_rate': data['is_profitable'].mean(),
            'feature_range': (data[feature].min(), data[feature].max()),
            'quartile_performance': {
                'Q1 (Low)': q1_pnl,
                'Q2': q2_pnl, 
                'Q3': q3_pnl,
                'Q4 (High)': q4_pnl
            }
        }
