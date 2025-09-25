import pandas as pd
import itertools
from dash import html, dcc
import plotly.express as px
import plotly.graph_objects as go
from dash import dash_table
from plotly.subplots import make_subplots

PERF_COLS = {
    "Sharpe","Total Return","USDT_PnL% (total)","Max Drawdown","USDT_Win Rate","USDT_Expectancy",
    "Returns Volatility (252 days)","Average (Return)","Average Win (Return)","Average Loss (Return)",
    "Sortino Ratio (252 days)","Profit Factor","Risk Return Ratio","Trades"
}
META_COLS = {"run_id","run_index","run_started","run_finished","backtest_start","backtest_end","elapsed_time"}

class ParameterAnalysisService:
    def detect_parameter_columns(self, df: pd.DataFrame) -> list:
        cols = []
        for c in df.columns:
            if c in PERF_COLS or c in META_COLS:
                continue
            if df[c].nunique() > 1 and df[c].dtype != object:
                cols.append(c)
        return cols

    def available_metrics(self, df: pd.DataFrame) -> list:
        candidates = [c for c in PERF_COLS if c in df.columns]
        # numeric only
        out = []
        for c in candidates:
            try:
                if pd.api.types.is_numeric_dtype(df[c]):
                    out.append(c)
            except Exception:
                pass
        return out

    def run_param_columns(self, df: pd.DataFrame) -> list:
        """
        Liefert nur echte Run-Parameter:
        - Alle Spalten vor 'run_id' in Original-Reihenfolge
        - Numerisch
        - Mit mehr als einem eindeutigen Wert
        """
        if 'run_id' not in df.columns:
            return []
        cols = list(df.columns)
        cutoff = cols.index('run_id')
        candidates = cols[:cutoff]
        out = []
        for c in candidates:
            try:
                if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 1:
                    out.append(c)
            except Exception:
                pass
        return out

    def _pivot_metric(self, df: pd.DataFrame, metric: str, x: str, y: str, agg: str):
        subset = df[[x,y,metric]].dropna()
        # ensure numeric
        subset = subset.copy()
        subset[metric] = pd.to_numeric(subset[metric], errors='coerce')
        subset = subset.dropna(subset=[metric])
        if subset.empty:
            return pd.DataFrame()
        aggfunc = getattr(pd.core.groupby.generic.SeriesGroupBy, agg, None)
        if aggfunc is None and agg not in ['mean','median','max','min','std','sum']:
            raise ValueError(f"Unsupported agg: {agg}")
        pivot = subset.groupby([y,x])[metric].agg(agg).unstack()
        return pivot

    def _heatmap(self, pivot: pd.DataFrame, metric: str, x: str, y: str):
        if pivot.empty or pivot.shape[0] == 0 or pivot.shape[1] == 0:
            return html.Div("No data to plot", style={'color': '#f87171', 'textAlign': 'center'})
        
        try:
            fig = px.imshow(
                pivot.values,
                x=[str(col) for col in pivot.columns],  # string conversion
                y=[str(idx) for idx in pivot.index],     # string conversion
                color_continuous_scale="Viridis",
                aspect="auto",  # wichtig für volle Breite
                origin="lower",
                labels=dict(color=metric),
                text_auto=True  # show values in cells
            )
            fig.update_layout(
                title=f"{metric} Heatmap ({y} vs {x})",
                xaxis_title=x,
                yaxis_title=y,
                coloraxis_colorbar=dict(title=metric),
                template="plotly_white",
                margin=dict(t=60, l=80, r=40, b=60),
                height=400,  # etwas höher
                width=600,   # explizite Breite
                autosize=True,  # auto-resize
                xaxis=dict(constrain='domain'),
                yaxis=dict(scaleanchor='x', scaleratio=1)  # entfernt für bessere Skalierung
            )
            
            # Return als Graph-Komponente mit expliziter Konfiguration
            return dcc.Graph(
                figure=fig,
                config={'displayModeBar': False},
                style={'height': '420px', 'width': '100%', 'minWidth': '500px'}  # volle Container-Breite
            )
        except Exception as e:
            print(f"[Heatmap Error] {e}")
            return html.Div(f"Plot error: {e}", style={'color': '#f87171'})

    def _surface(self, pivot: pd.DataFrame, metric: str, x: str, y: str):
        if pivot.empty:
            return html.Div("No data for surface", style={'color': '#f87171'})
            
        try:
            z = pivot.values
            fig = go.Figure(data=[go.Surface(
                z=z,
                x=list(pivot.columns),  # direct list conversion
                y=list(pivot.index),    # direct list conversion
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title=metric)
            )])
            fig.update_layout(
                title=f"{metric} 3D Surface ({y} vs {x})",
                scene=dict(
                    xaxis_title=x,
                    yaxis_title=y,
                    zaxis_title=metric
                ),
                height=400,
                template="plotly_white",
                margin=dict(t=60, l=0, r=0, b=0)
            )
            return dcc.Graph(
                figure=fig, 
                config={'displayModeBar': True},
                style={'height': '420px', 'width': '100%'}
            )
        except Exception as e:
            print(f"[Surface Error] {e}")
            return html.Div(f"3D plot error: {e}", style={'color': '#f87171'})

    def _scatter_3d(self, df: pd.DataFrame, metric: str, x: str, y: str, z: str, agg: str = 'mean'):
        """
        Interaktiver 3D Scatter:
          - Aggregiert mehrfach vorkommende Param-Kombinationen
          - Versucht robuste Numerik-Konvertierung
          - Färbt nach Metric (continuous)
        """
        if any(p not in df.columns for p in [x, y, z, metric]):
            return html.Div("Missing columns for 3D plot", style={'color': '#f87171'})
        work = df[[x, y, z, metric]].copy()
        # Soft cast strings like "0.75", remove commas, strip
        for col in [x, y, z, metric]:
            work[col] = work[col].astype(str).str.replace(',', '.').str.strip()
            work[col] = pd.to_numeric(work[col], errors='coerce')
        work = work.dropna(subset=[x, y, z, metric])
        if work.empty:
            return html.Div("No numeric data (after conversion) for 3D plot", style={'color': '#f87171'})

        # Aggregation
        agg_func_map = {
            'mean': 'mean',
            'median': 'median',
            'max': 'max',
            'min': 'min',
            'std': 'std'
        }
        func = agg_func_map.get(agg, 'mean')
        grouped = getattr(work.groupby([x, y, z])[metric], func)().reset_index()
        grouped = grouped.sort_values(metric, ascending=False)

        if grouped.empty:
            return html.Div("Empty grouped data for 3D plot", style={'color': '#f87171'})

        fig = px.scatter_3d(
            grouped,
            x=x, y=y, z=z,
            color=metric,
            color_continuous_scale="Viridis",
            size_max=10,
            opacity=0.85,
            title=None
        )
        fig.update_traces(marker=dict(line=dict(width=0)))
        fig.update_layout(
            scene=dict(
                xaxis_title=x,
                yaxis_title=y,
                zaxis_title=z,
            ),
            margin=dict(t=10, l=0, r=0, b=0),
            height=520,
            template="plotly_white",
            coloraxis_colorbar=dict(title=metric)
        )
        return dcc.Graph(
            figure=fig,
            config={'displayModeBar': False},
            style={'height': '540px', 'width': '100%'}
        )

    def _best_table(self, pivot: pd.DataFrame, metric: str, x: str, y: str, z: str | None = None, top_n: int = 5):
        """
        Erzeugt eine symmetrische Top-N Tabelle der besten Kombinationen.
        Bei 2D: traversiert Pivot
        Bei 3D: erwartet bereits gefilterten DataFrame (separat aufgerufen)
        """
        try:
            records = []
            if z is None:
                # 2D: pivot (index=y, columns=x)
                for yi in pivot.index:
                    for xi in pivot.columns:
                        val = pivot.loc[yi, xi]
                        if pd.notna(val):
                            records.append({x: xi, y: yi, metric: val})
            else:
                # 3D: z als zusätzlicher Layer (hier nicht pivoted)
                # erwartet: pivot ist ein normaler DF mit den Spalten x,y,z,metric
                for _, row in pivot.iterrows():
                    records.append({x: row[x], y: row[y], z: row[z], metric: row[metric]})
            if not records:
                return html.Div("No combinations found", style={'color': '#f87171', 'fontFamily': 'Inter'})
            df = pd.DataFrame(records)
            df = df.sort_values(metric, ascending=False).head(top_n).reset_index(drop=True)
            # Formatierung
            df[metric] = pd.to_numeric(df[metric], errors='coerce')
            df[metric] = df[metric].map(lambda v: f"{v:.4f}" if pd.notna(v) else "N/A")

            columns = [{'name': col, 'id': col} for col in df.columns]
            return html.Div([
                html.H4("Best Combination(s)", style={
                    'margin': '0 0 10px 0', 'color': '#e2e8f0', 'fontFamily': 'Inter',
                    'fontSize': '16px', 'fontWeight': '600'
                }),
                dash_table.DataTable(
                    data=df.to_dict('records'),
                    columns=columns,
                    style_table={
                        'overflowX': 'auto',
                        'border': '1px solid #334155',
                        'borderRadius': '10px',
                        'background': '#0f172a'
                    },
                    style_header={
                        'background': '#1e293b',
                        'color': '#f1f5f9',
                        'fontWeight': '600',
                        'fontFamily': 'Inter',
                        'border': 'none',
                        'fontSize': '12px'
                    },
                    style_cell={
                        'background': '#0f172a',
                        'color': '#cbd5e1',
                        'fontFamily': 'Inter',
                        'fontSize': '12px',
                        'textAlign': 'center',
                        'padding': '6px 4px',
                        'border': 'none'
                    },
                    style_data_conditional=[
                        {'if': {'row_index': 0},
                         'backgroundColor': '#1e3a8a',
                         'color': '#ffffff',
                         'fontWeight': '600'}
                    ]
                )
            ], style={
                'marginTop': '18px',
                'background': 'linear-gradient(135deg,#0f172a,#1e293b)',
                'padding': '16px 18px',
                'borderRadius': '14px',
                'border': '1px solid #334155'
            })
        except Exception as e:
            return html.Div(f"Best table error: {e}", style={'color': '#f87171'})

    def generate_metric_views(self, df: pd.DataFrame, metric: str, x: str, y: str, agg: str):
        pivot = self._pivot_metric(df, metric, x, y, agg)
        if pivot.empty:
            return [html.Div("No data for selection", style={'color':'#f87171'})]
        
        heatmap = self._heatmap(pivot, metric, x, y)
        surface = self._surface(pivot, metric, x, y)
        best = self._best_table(pivot, metric, x, y, z=None, top_n=5)
        
        return [
            html.Div([
                html.Div([
                    html.H3(f"{metric} – {y} vs {x}", style={
                        'margin':'0 0 4px 0','color':'#e2e8f0','fontFamily':'Inter','fontWeight':'600','fontSize':'20px'
                    }),
                    html.P(f"Aggregation: {agg}", style={'margin':'0','color':'#94a3b8','fontSize':'13px'})
                ], style={'marginBottom':'14px'}),
                html.Div([
                    html.Div(heatmap, style={'flex':'1 1 50%','minWidth':'500px'}),  # größere minWidth
                    html.Div(surface, style={'flex':'1 1 50%','minWidth':'500px'}),   # größere minWidth
                ], style={'display':'flex','flexWrap':'wrap','gap':'24px','justifyContent':'center'}),  # zentriert
                html.Div(best, style={'marginTop':'24px'})
            ], style={
                'background':'linear-gradient(135deg,#1e293b,#0f172a)',
                'padding':'28px 30px',
                'borderRadius':'18px',
                'border':'1px solid #334155',
                'boxShadow':'0 6px 24px -4px rgba(0,0,0,0.55)',
                'width': '100%',  # volle Container-Breite
                'boxSizing': 'border-box'
            })
        ]

    def generate_3d_analysis(self, df: pd.DataFrame, metric: str, x: str, y: str, z: str, agg: str = 'mean'):
        if any(col not in df.columns for col in [metric, x, y, z]):
            return [html.Div("Selected columns not in dataset", style={'color': '#f87171'})]

        # Build scatter (handles aggregation + conversion)
        scatter_3d = self._scatter_3d(df, metric, x, y, z, agg)

        # Prepare best point (reuse aggregation logic)
        work = df[[x, y, z, metric]].copy()
        for col in [x, y, z, metric]:
            work[col] = work[col].astype(str).str.replace(',', '.').str.strip()
            work[col] = pd.to_numeric(work[col], errors='coerce')
        work = work.dropna()
        if work.empty:
            best_stats = html.Div("No data for best point", style={'color': '#f87171'})
        else:
            grouped = getattr(work.groupby([x, y, z])[metric], {'mean':'mean','median':'median',
                                                                 'max':'max','min':'min','std':'std'}.get(agg,'mean'))().reset_index()
            if grouped.empty:
                best_stats = html.Div("No aggregated data", style={'color': '#f87171'})
            else:
                best_row = grouped.sort_values(metric, ascending=False).iloc[0]
                best_stats = html.Div([
                    html.H4("Best 3D Combination", style={
                        'color':'#f1f5f9','margin':'0 0 10px 0','fontFamily':'Inter',
                        'fontWeight':'600','fontSize':'16px'
                    }),
                    html.Table([
                        html.Tr([html.Td(x), html.Td(f"{best_row[x]:.4f}")]),
                        html.Tr([html.Td(y), html.Td(f"{best_row[y]:.4f}")]),
                        html.Tr([html.Td(z), html.Td(f"{best_row[z]:.4f}")]),
                        html.Tr([html.Td(metric), html.Td(f"{best_row[metric]:.6f}", style={'color':'#10b981','fontWeight':'600'})])
                    ], style={
                        'width':'100%','color':'#e2e8f0','fontFamily':'Inter','fontSize':'12px',
                        'borderSpacing':'6px'
                    })
                ], style={
                    'background':'linear-gradient(135deg,#0f172a,#1e293b)',
                    'padding':'16px 18px',
                    'borderRadius':'14px',
                    'border':'1px solid #334155',
                    'marginTop':'22px'
                })

        return [
            html.Div([
                html.Div([
                    html.H3(f"{metric} – 3D Analysis", style={
                        'margin':'0 0 4px 0','color':'#e2e8f0','fontFamily':'Inter',
                        'fontWeight':'600','fontSize':'20px'
                    }),
                    html.P(f"{x}, {y}, {z} (aggregation: {agg})", style={
                        'margin':'0 0 14px 0','color':'#94a3b8','fontSize':'12px'
                    })
                ]),
                scatter_3d,
                best_stats
            ], style={
                'background':'linear-gradient(135deg,#1e293b,#0f172a)',
                'padding':'26px 30px',
                'borderRadius':'18px',
                'border':'1px solid #334155',
                'boxShadow':'0 6px 24px -4px rgba(0,0,0,0.55)'
            })
        ]

    # NEU: Interaktiver Pairplot (ersetzt statisches seaborn PNG)
    def _pairplot_matrix(self, df: pd.DataFrame, params: list[str], metric: str):
        n = len(params)
        if n < 2:
            return html.Div("Need >=2 parameters", style={'color': '#f87171'})

        data = df[params + [metric]].dropna().copy()
        data[metric] = pd.to_numeric(data[metric], errors='coerce')
        data = data.dropna(subset=[metric])
        if data.empty:
            return html.Div("No valid data for pairplot", style={'color': '#f87171'})

        fig = make_subplots(
            rows=n, cols=n,
            shared_xaxes=False, shared_yaxes=False,
            horizontal_spacing=0.01,
            vertical_spacing=0.01
        )

        color_added = False
        mvals = data[metric]

        for r, py in enumerate(params, start=1):
            for c, px_ in enumerate(params, start=1):
                if r == c:
                    col_data = pd.to_numeric(data[px_], errors='coerce').dropna()
                    bins = min(30, max(5, col_data.nunique()))
                    fig.add_trace(
                        go.Histogram(
                            x=col_data,
                            nbinsx=bins,
                            marker=dict(color='#6366f1'),
                            hovertemplate=f"{px_}: %{{x}}<br>Count: %{{y}}<extra></extra>",
                            showlegend=False
                        ),
                        row=r, col=c
                    )
                else:
                    x_vals = pd.to_numeric(data[px_], errors='coerce')
                    y_vals = pd.to_numeric(data[py], errors='coerce')
                    hover_tmpl = (
                        f"{px_}=%{{x}}<br>"
                        f"{py}=%{{y}}<br>"
                        f"{metric}=%{{marker.color:.4f}}<extra></extra>"
                    )
                    fig.add_trace(
                        go.Scattergl(
                            x=x_vals,
                            y=y_vals,
                            mode='markers',
                            marker=dict(
                                color=mvals,
                                colorscale='Viridis',
                                showscale=not color_added,
                                colorbar=dict(title=metric) if not color_added else None,
                                size=6,
                                line=dict(width=0),
                                opacity=0.85
                            ),
                            hovertemplate=hover_tmpl,
                            showlegend=False
                        ),
                        row=r, col=c
                    )
                    if not color_added:
                        color_added = True

        # Achsentitel nur außen + Ticklabels ausdünnen
        for r in range(1, n + 1):
            for c in range(1, n + 1):
                show_x = (r == n)
                show_y = (c == 1)
                fig.update_xaxes(
                    row=r, col=c,
                    showticklabels=show_x,
                    ticks='outside',
                    tickfont=dict(size=9),
                    title=dict(
                        text=f"<b>{params[c - 1]}</b>" if show_x else '',
                        font=dict(size=11)
                    )
                )
                fig.update_yaxes(
                    row=r, col=c,
                    showticklabels=show_y,
                    ticks='outside',
                    tickfont=dict(size=9),
                    title=dict(
                        text=f"<b>{params[r - 1]}</b>" if show_y else '',
                        font=dict(size=11)
                    )
                )

        # Layout: quadratisch + mittig
        grid_side = min(1100, 210 * len(params) + 60)  # gemeinsame Seitenlänge
        fig.update_layout(
            template='plotly_white',
            margin=dict(t=48, l=48, r=48, b=46),
            height=grid_side,
            width=grid_side,
            autosize=False,
            title=dict(
                text="Parameter Pair Plot",
                x=0.5,
                font=dict(size=17)
            ),
            bargap=0.04,
            plot_bgcolor='rgba(255,255,255,0.92)',
            paper_bgcolor='rgba(255,255,255,1)'
        )
        fig.update_traces(
            selector=dict(type='histogram'),
            marker_line_width=0,
            opacity=0.85
        )
        return dcc.Graph(
            figure=fig,
            config={'displayModeBar': False, 'responsive': False},
            style={
                'width': f'{grid_side}px',
                'height': f'{grid_side}px',
                'margin': '0 auto',
                'maxWidth': '100%'
            }
        )

    # ERSETZT: generate_full_pair_matrix mit seaborn -> jetzt interaktiv
    def generate_full_pair_matrix(self, df: pd.DataFrame, metric: str):
        params = self.run_param_columns(df)
        numeric_params = []
        for p in params:
            try:
                if pd.api.types.is_numeric_dtype(df[p]) and df[p].nunique() > 1:
                    numeric_params.append(p)
            except Exception:
                pass
        if len(numeric_params) < 2:
            return [html.Div("Not enough numeric varying parameters", style={'color': '#f87171'})]

        truncated = False
        if len(numeric_params) > 8:
            numeric_params = numeric_params[:8]
            truncated = True

        if metric not in df.columns:
            return [html.Div(f"Metric '{metric}' not in dataset", style={'color': '#f87171'})]

        df = df.copy()
        df[metric] = pd.to_numeric(df[metric], errors='coerce')
        if df[metric].isna().all():
            return [html.Div(f"Metric '{metric}' has no numeric values", style={'color': '#f87171'})]

        graph = self._pairplot_matrix(df, numeric_params, metric)

        header = html.Div([
            html.H4(f"Interactive Pairplot ({len(numeric_params)} parameters)", style={
                'color': '#f1f5f9', 'margin': '0 0 6px 0', 'fontFamily': 'Inter',
                'fontSize': '18px', 'fontWeight': '600'
            }),
            html.P(
                ("Showing first 8 parameters (truncated). " if truncated else "") +
                f"Diagonal: distributions, off-diagonals: scatter (colored by {metric}). Both triangles filled.",
                style={'color': '#94a3b8', 'margin': '0 0 14px 0', 'fontSize': '13px', 'fontFamily': 'Inter'}
            )
        ])

        return [
            html.Div([
                header,
                graph
            ], style={
                'background': 'linear-gradient(135deg,#1e293b,#0f172a)',
                'padding': '26px 28px',
                'borderRadius': '18px',
                'border': '1px solid #334155',
                'boxShadow': '0 6px 18px -4px rgba(0,0,0,0.55)'
            })
        ]
