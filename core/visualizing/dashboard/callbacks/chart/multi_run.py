from dash import dcc
from dash import html
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path  # <-- hinzugefügt

from core.visualizing.dashboard.charts import build_price_chart, add_trade_visualization
from core.visualizing.dashboard.components import (
    get_default_trade_details,
    create_trade_details_content,
    create_metrics_table
)
from core.visualizing.dashboard.multi_run_manager import (
    gather_multi_run_data,
    short_run_label,
    run_color_for_index
)
from .constants import (
    MULTI_RUN_MARKER_OFFSET_FACTOR,
    MIN_OFFSET_EPS,
    ACTION_LOCAL_OFFSET_RATIO,
    ACTION_LOCAL_OFFSET_RATIO_MULTI_INST
)

try:
    from core.visualizing.dashboard import colors as dash_colors  # colors.py
except ImportError:
    dash_colors = None

# Toggle if the price chart should display a legend at all
SHOW_PRICE_LEGEND = True

def _resolve_palette():
    # Try darker / explicit palettes first
    candidates = [
        "DARK_COLORS", "DARK_PALETTE", "DARK_COLOR_PALETTE",
        "COLOR_PALETTE_DARK", "COLOR_PALETTE"
    ]
    if dash_colors:
        for name in candidates:
            pal = getattr(dash_colors, name, None)
            if isinstance(pal, (list, tuple)) and pal:
                return list(pal)
    # Fallback internal
    return [
        "#1b2838","#b34700","#1f5c1f","#8b1a1a","#5e3a87",
        "#574338","#b23a70","#555555","#8a8f22","#148ea1",
        "#2c3559","#3d5a3d","#66522a","#6b2d32","#5a2f59",
        "#1f4f74","#1f6a4f","#9c4a58","#574d8f","#444444"
    ]

def _base_offset(bars_df):
    span = 0.0
    if isinstance(bars_df, pd.DataFrame) and not bars_df.empty:
        try:
            span = (bars_df["high"].max() - bars_df["low"].min()) or 0.0
        except Exception:
            span = 0.0
    if span > 0:
        return max(span * MULTI_RUN_MARKER_OFFSET_FACTOR, MIN_OFFSET_EPS)
    try:
        avg_price = float(bars_df["close"].mean())
    except Exception:
        avg_price = 1.0
    return max(avg_price * (MULTI_RUN_MARKER_OFFSET_FACTOR * 0.5), MIN_OFFSET_EPS)

def _indicator_overlay_single(active_runs, indicators_per_run, x_range):
    # optional: shared_x passed in by caller later (monkey via closure variable)
    out = []
    groups = {}
    import pandas as pd
    for ridx, rid in enumerate(active_runs):
        imap = indicators_per_run.get(rid, {}) or {}
        for name, df in imap.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                pid = int(df["plot_id"].iloc[0]) if "plot_id" in df.columns and len(df["plot_id"]) > 0 else 0
                if pid > 0:
                    groups.setdefault(pid, []).append((ridx, rid, name, df))
    for pid, lst in sorted(groups.items()):
        fig = go.Figure()
        shared_normalized_x = None
        for ridx, rid, name, df in lst:
            _, _, color = run_color_for_index(ridx)
            nx = _normalize_timestamps(df["timestamp"]) if "timestamp" in df.columns else df.index
            if shared_normalized_x is None:
                shared_normalized_x = nx
            else:
                # enforce identical reference length & values if lengths match
                if len(nx) == len(shared_normalized_x):
                    nx = shared_normalized_x
            fig.add_trace(go.Scatter(
                x=nx,
                y=df["value"],
                mode="lines",
                name=f"{short_run_label(rid)}:{name}",
                line=dict(color=color, width=2),
                hovertemplate=f"<b>{short_run_label(rid)}:{name}</b><br>%{{x}}<br>%{{y:.4f}}<extra></extra>"
            ))
        fig.update_layout(
            template="plotly_white",
            margin=dict(t=30, b=30, l=60, r=40),
            title=dict(text=f"Run Overlay: Plot {pid}", x=0.01, y=0.99,
                       xanchor="left", yanchor="top",
                       font=dict(size=14, color="#4a5568")),
            hovermode="x unified",
            legend=dict(
                orientation="h",
                x=0.01,
                y=0.99,
                xanchor="left",
                yanchor="top",
                bgcolor="rgba(255,255,255,0.55)",
                bordercolor="rgba(0,0,0,0.15)",
                borderwidth=1,
                font=dict(size=10),
                itemsizing="trace"
            )
        )
        if x_range is not None:
            fig.update_xaxes(range=x_range, autorange=False,
                             constrain="domain", rangebreaks=[])
        fig.update_layout(uirevision="linked-range")
        out.append(dcc.Graph(
            id=f"multi-run-indicators-plot-{pid}",
            figure=fig,
            style={"height": "300px", "marginBottom": "10px"}
        ))
    return out

def _normalize_timestamps(series):
    try:
        ts = pd.to_datetime(series, errors="coerce")
        # Remove timezone (so all charts align)
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_convert(None)
        return ts
    except Exception:
        return pd.to_datetime([], errors="coerce")

def _build_single_instrument_multi_run(state, repo, instrument, active_runs, clickData,
                                       chart_mode, x_range, timeframe=None, show_trades=True, x_window=None):
    # Use timeframe-aware multi-run data
    bars_df, indicators_per_run, trades_per_run = gather_multi_run_data(
        state["runs_cache"], active_runs, instrument, timeframe=timeframe
    )
    # NEW: window filtering
    if x_window and isinstance(bars_df, pd.DataFrame):
        s, e = x_window
        bars_df = bars_df[(bars_df["timestamp"] >= s) & (bars_df["timestamp"] <= e)]
    if x_window:
        s, e = x_window
        for rid in list(trades_per_run.keys()):
            tdf = trades_per_run[rid]
            if isinstance(tdf, pd.DataFrame) and "timestamp" in tdf.columns:
                trades_per_run[rid] = tdf[(tdf["timestamp"] >= s) & (tdf["timestamp"] <= e)]
        for rid in list(indicators_per_run.keys()):
            imap = indicators_per_run[rid]
            if isinstance(imap, dict):
                filt_map = {}
                for name, df in imap.items():
                    if isinstance(df, pd.DataFrame) and "timestamp" in df.columns:
                        filt_map[name] = df[(df["timestamp"] >= s) & (df["timestamp"] <= e)]
                indicators_per_run[rid] = filt_map

    # Build indicators_df for price overlay: collect pid==0 indicators across runs and prefix names
    indicators_for_price = {}
    try:
        for ridx, rid in enumerate(active_runs):
            imap = indicators_per_run.get(rid, {}) or {}
            for name, df in imap.items():
                if not isinstance(df, pd.DataFrame) or df.empty:
                    continue
                pid = int(df["plot_id"].iloc[0]) if "plot_id" in df.columns and len(df["plot_id"]) > 0 else 0
                if pid == 0:
                    key = f"{short_run_label(rid)}:{name}"
                    indicators_for_price[key] = df.copy()
    except Exception:
        # ignore indicator collection errors
        pass

    # Neu: globale Range bestimmen falls keine externe Range (x_range) gesetzt
    norm_ts = _normalize_timestamps(bars_df["timestamp"]) if isinstance(bars_df, pd.DataFrame) and "timestamp" in bars_df.columns else pd.Series([], dtype="datetime64[ns]")
    if x_range is None and not norm_ts.empty:
        computed_range = [norm_ts.min(), norm_ts.max()]
    else:
        computed_range = None

    base_offset_unit = _base_offset(bars_df)

    try:
        # pass collected pid==0 indicators to the price builder so overlays appear on the main chart
        price_fig = build_price_chart(bars_df, indicators_for_price, None, None, display_mode=(chart_mode or "OHLC"))
        # Normalisiere X für alle Traces (Candles + evtl. Line) zur exakten Deckungsgleichheit
        if isinstance(bars_df, pd.DataFrame) and "timestamp" in bars_df.columns:
            norm_price_x = _normalize_timestamps(bars_df["timestamp"])
            for tr in price_fig.data:
                if hasattr(tr, "x") and len(getattr(tr, "x", [])) == len(norm_price_x):
                    tr.x = norm_price_x
        price_fig.update_layout(
            uirevision="linked-range",
            showlegend=SHOW_PRICE_LEGEND,
            legend=dict(
                orientation="h",
                x=0.01,
                y=0.99,
                xanchor="left",
                yanchor="top",
                bgcolor="rgba(255,255,255,0.55)",
                bordercolor="rgba(0,0,0,0.15)",
                borderwidth=1,
                font=dict(size=10),
                itemsizing="trace"
            ),
            margin=dict(t=30, b=30, l=60, r=40)
        )
        eff_range = x_range or computed_range
        if eff_range:
            price_fig.update_xaxes(
                range=eff_range,
                autorange=False,
                constrain="domain",
                rangebreaks=[]
            )
    except Exception as e:
        price_fig = go.Figure().update_layout(title=f"Chart error: {e}")

    selected_tuple = state.get("selected_trade_index") if isinstance(state.get("selected_trade_index"), tuple) else None
    run_count = len(active_runs)

    if show_trades:
        for ridx, rid in enumerate(active_runs):
            trades_df = trades_per_run.get(rid)
            if not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
                continue
            buy_color, short_color, _ = run_color_for_index(ridx)
            layer_offset = base_offset_unit * (ridx - (run_count - 1) / 2.0)

            def add_group(action, symbol, color):
                sub = trades_df[trades_df["action"] == action]
                if sub.empty:
                    return
                first_idx = sub.index[0]
                for idx in sub.index:
                    row = sub.loc[idx]
                    local = ACTION_LOCAL_OFFSET_RATIO * base_offset_unit * (1 if action == "BUY" else -1)
                    y_val = row.get("open_price_actual", row.get("price_actual", 0)) + layer_offset + local
                    is_sel = selected_tuple == (rid, idx)
                    price_fig.add_trace(go.Scatter(
                        x=[row["timestamp"]],
                        y=[y_val],
                        mode="markers",
                        name=f"{short_run_label(rid)} {action}" if idx == first_idx else None,
                        marker=dict(
                            symbol=symbol,
                            size=18 if is_sel else 12,
                            color=color,
                            line=dict(color="#ffffff", width=2 if is_sel else 1)
                        ),
                        customdata=[[rid, idx]],
                        hovertemplate=(
                            f"<b>{short_run_label(rid)} {action}"
                            f"{' (Selected)' if is_sel else ''}</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>"
                        ),
                        showlegend=bool(idx == first_idx)
                    ))
            add_group("BUY", "triangle-up", buy_color)
            add_group("SHORT", "triangle-down", short_color)
    else:
        state["selected_trade_index"] = None

    trade_details = get_default_trade_details()
    if show_trades and clickData:
        pt = next((p for p in clickData.get("points", []) if "customdata" in p), None)
        if pt:
            cd = pt.get("customdata")
            run_id_clicked = trade_idx_clicked = None
            if isinstance(cd, (list, tuple)):
                if len(cd) == 2 and not isinstance(cd[0], (list, tuple)):
                    run_id_clicked, trade_idx_clicked = cd
                elif len(cd) == 1 and isinstance(cd[0], (list, tuple)) and len(cd[0]) == 2:
                    run_id_clicked, trade_idx_clicked = cd[0]
            if run_id_clicked is not None and trade_idx_clicked is not None:
                tdf = trades_per_run.get(run_id_clicked)
                if isinstance(tdf, pd.DataFrame) and trade_idx_clicked in tdf.index:
                    state["selected_trade_index"] = (run_id_clicked, trade_idx_clicked)
                    trade_details = create_trade_details_content(tdf.loc[trade_idx_clicked])
                    try:
                        add_trade_visualization(price_fig, tdf, bars_df, trade_idx_clicked)
                    except Exception as e:
                        print(f"[WARN] add_trade_visualization multi-run failed: {e}")

    if selected_tuple and not clickData:
        rid_sel, idx_sel = selected_tuple
        tdf_sel = trades_per_run.get(rid_sel)
        if isinstance(tdf_sel, pd.DataFrame) and idx_sel in tdf_sel.index:
            try:
                add_trade_visualization(price_fig, tdf_sel, bars_df, idx_sel)
            except Exception as e:
                print(f"[WARN] add_trade_visualization persist failed: {e}")

    # Metrics: build nested mapping run_id -> { instrument -> metrics_dict } for this single instrument
    metrics_children = html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'})
    if active_runs:
        nested_metrics = {}
        for rid in active_runs:
            per_inst = {}
            metrics = None
            # disk-first lookup
            try:
                results_root = getattr(repo, "results_root", None)
                if results_root is None:
                    results_root = Path(__file__).resolve().parents[5] / "data" / "DATA_STORAGE" / "results"
                run_dir = Path(results_root) / str(rid)
                trade_metrics_path = run_dir / str(instrument) / "trade_metrics.csv"
                if trade_metrics_path.exists() and trade_metrics_path.is_file():
                    try:
                        dfm = pd.read_csv(trade_metrics_path)
                        if not dfm.empty:
                            metrics = dfm.iloc[0].to_dict()
                    except Exception:
                        pass
            except Exception:
                pass
            # fallback to repo.load_metrics(run, instrument) or repo.load_metrics(instrument)
            if metrics is None and hasattr(repo, "load_metrics"):
                try:
                    loaded = None
                    try:
                        loaded = repo.load_metrics(rid, instrument)
                    except TypeError:
                        try:
                            loaded = repo.load_metrics(instrument)
                        except Exception:
                            loaded = None
                    if loaded:
                        if isinstance(loaded, tuple) and isinstance(loaded[0], dict):
                            metrics, _ = loaded
                        elif isinstance(loaded, dict):
                            metrics = loaded
                        elif hasattr(loaded, "iloc"):
                            df2 = loaded
                            if not df2.empty:
                                metrics = df2.iloc[0].to_dict()
                except Exception:
                    pass
            if metrics:
                per_inst[str(instrument)] = metrics
            if per_inst:
                nested_metrics[str(rid)] = per_inst
        if nested_metrics:
            try:
                metrics_children = create_metrics_table(nested_metrics, [])
            except Exception:
                metrics_children = html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'})

    # Indicator Overlay jetzt mit konsistenter Range
    effective_range = x_range or computed_range
    indicators_children = _indicator_overlay_single(active_runs, indicators_per_run, effective_range)
    return price_fig, indicators_children, metrics_children, trade_details

def _build_multi_instrument_multi_run(state, repo, instruments, active_runs, clickData,
                                      chart_mode, x_range, color_map, timeframe=None, show_trades=True, x_window=None):
    # Daten sammeln
    multi_data = {}
    for inst in instruments:
        multi_data[inst] = gather_multi_run_data(state["runs_cache"], active_runs, inst, timeframe=timeframe)

    # NEW: window filtering
    if x_window:
        s, e = x_window
        new_multi = {}
        for inst, tup in multi_data.items():
            bdf, inds_per_run, trades_per_run_i = tup
            if isinstance(bdf, pd.DataFrame) and "timestamp" in bdf.columns:
                bdf = bdf[(bdf["timestamp"] >= s) & (bdf["timestamp"] <= e)]
            if isinstance(trades_per_run_i, dict):
                for rid in list(trades_per_run_i.keys()):
                    tdf = trades_per_run_i[rid]
                    if isinstance(tdf, pd.DataFrame) and "timestamp" in tdf.columns:
                        trades_per_run_i[rid] = tdf[(tdf["timestamp"] >= s) & (tdf["timestamp"] <= e)]
            if isinstance(inds_per_run, dict):
                for rid in list(inds_per_run.keys()):
                    imap = inds_per_run[rid]
                    if isinstance(imap, dict):
                        fimap = {}
                        for name, df in imap.items():
                            if isinstance(df, pd.DataFrame) and "timestamp" in df.columns:
                                fimap[name] = df[(df["timestamp"] >= s) & (df["timestamp"] <= e)]
                        inds_per_run[rid] = fimap
            new_multi[inst] = (bdf, inds_per_run, trades_per_run_i)
        multi_data = new_multi

    # Globale Zeit-Range über alle Instrumente (nur wenn keine externe x_range vorliegt)
    if x_range is None:
        all_norm = []
        for inst in instruments:
            bdf = multi_data.get(inst, (None, None, None))[0]
            if isinstance(bdf, pd.DataFrame) and "timestamp" in bdf.columns and not bdf.empty:
                nts = _normalize_timestamps(bdf["timestamp"])
                if not nts.empty:
                    all_norm.append(nts.min()); all_norm.append(nts.max())
        global_x_range = [min(all_norm), max(all_norm)] if all_norm else None
    else:
        global_x_range = None

    price_fig = go.Figure()
    candle_indices = []
    line_indices = []

    for i, inst in enumerate(instruments):
        bars_df, _inds, _trades = multi_data[inst]
        if not isinstance(bars_df, pd.DataFrame) or bars_df.empty:
            continue
        axis_id = 'y' if i == 0 else f'y{i+1}'
        price_fig.add_trace(go.Candlestick(
            x=bars_df["timestamp"],
            open=bars_df["open"], high=bars_df["high"],
            low=bars_df["low"], close=bars_df["close"],
            name=f"{inst} OHLC",
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
            increasing_fillcolor='#26a69a',
            decreasing_fillcolor='#ef5350',
            opacity=1.0,
            showlegend=True,
            yaxis=axis_id,
            visible=(chart_mode == "OHLC")
        ))
        price_fig.data[-1].uid = f"candle_{inst}"
        candle_indices.append(len(price_fig.data) - 1)
        price_fig.add_trace(go.Scatter(
            x=bars_df["timestamp"],
            y=bars_df["close"],
            mode="lines",
            name=f"{inst} Close",
            line=dict(color=color_map.get(inst, "#000000"), width=2),
            visible=(chart_mode == "GRAPH"),
            yaxis=axis_id,
            hovertemplate=f"<b>{inst}</b><br>%{{x}}<br>Close: %{{y:.4f}}<extra></extra>"
        ))
        price_fig.data[-1].uid = f"line_{inst}"

        # Normalize timestamps for both traces to keep alignment
        nts_local = _normalize_timestamps(bars_df["timestamp"])
        price_fig.data[-2].x = nts_local  # candlestick
        price_fig.data[-1].x = nts_local  # line
    # --- end for instruments loop ---

    # After adding all traces, enforce normalized x reuse for each instrument pair
    for inst in instruments:
        # find indices for this instrument's candle & line via uid
        candle_uid = f"candle_{inst}"
        line_uid = f"line_{inst}"
        candle_tr = next((t for t in price_fig.data if getattr(t, "uid", None) == candle_uid), None)
        line_tr = next((t for t in price_fig.data if getattr(t, "uid", None) == line_uid), None)
        if candle_tr and isinstance(candle_tr.x, (list, tuple, pd.Series)):
            norm_ref = list(candle_tr.x)
            if line_tr and len(line_tr.x) == len(norm_ref):
                line_tr.x = norm_ref  # share reference

    selected_tuple = state.get("selected_trade_index") if isinstance(state.get("selected_trade_index"), tuple) else None
    if selected_tuple and len(selected_tuple) != 3:
        selected_tuple = None

    # Trades
    if show_trades:
        for inst_index, inst in enumerate(instruments):
            bars_df, indicators_per_run_i, trades_per_run_i = multi_data[inst]
            base_offset_unit = _base_offset(bars_df)
            axis_id = 'y' if inst_index == 0 else f'y{inst_index+1}'
            run_count = len(active_runs)
            for ridx, rid in enumerate(active_runs):
                trades_df = trades_per_run_i.get(rid)
                if not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
                    continue
                buy_color, short_color, _ = run_color_for_index(ridx)
                run_offset = base_offset_unit * (ridx - (run_count - 1) / 2.0)

                def add_group(action, symbol, color):
                    sub = trades_df[trades_df["action"] == action]
                    if sub.empty:
                        return
                    first_idx = sub.index[0]
                    for tidx in sub.index:
                        row = sub.loc[tidx]
                        act_off = ACTION_LOCAL_OFFSET_RATIO_MULTI_INST * base_offset_unit * (1 if action == "BUY" else -1)
                        y_val = row.get("open_price_actual", row.get("price_actual", 0)) + run_offset + act_off
                        is_sel = selected_tuple == (rid, inst, tidx)
                        price_fig.add_trace(go.Scatter(
                            x=[row["timestamp"]],
                            y=[y_val],
                            mode="markers",
                            name=f"{short_run_label(rid)} {inst} {action}" if tidx == first_idx else None,
                            marker=dict(
                                symbol=symbol,
                                size=20 if is_sel else 12,
                                color=color,
                                line=dict(color="#ffffff", width=2 if is_sel else 1)
                            ),
                            customdata=[[rid, inst, tidx]],
                            hovertemplate=(
                                f"<b>{short_run_label(rid)} {inst} {action}"
                                f"{' (Selected)' if is_sel else ''}</b><br>%{{x}}<br>Price: %{{y:.4f}}<extra></extra>"
                            ),
                            showlegend=bool(tidx == first_idx),
                            yaxis=axis_id
                        ))
                add_group("BUY", "triangle-up", buy_color)
                add_group("SHORT", "triangle-down", short_color)
    else:
        state["selected_trade_index"] = None

    trade_details = get_default_trade_details()
    if show_trades and clickData:
        pt = next((p for p in clickData.get("points", []) if "customdata" in p), None)
        if pt:
            cd = pt.get("customdata")
            flat = cd[0] if (isinstance(cd, (list, tuple)) and len(cd) == 1 and isinstance(cd[0], (list, tuple))) else cd
            if isinstance(flat, (list, tuple)) and len(flat) == 3:
                rid_clicked, inst_clicked, idx_clicked = flat
                if inst_clicked in multi_data:
                    _bars, _inds, trades_per_run_i = multi_data[inst_clicked]
                    tdf = trades_per_run_i.get(rid_clicked)
                    if isinstance(tdf, pd.DataFrame) and idx_clicked in tdf.index:
                        state["selected_trade_index"] = (rid_clicked, inst_clicked, idx_clicked)
                        trade_details = create_trade_details_content(tdf.loc[idx_clicked])
                        try:
                            add_trade_visualization(price_fig, tdf, multi_data[inst_clicked][0], idx_clicked)
                        except Exception as e:
                            print(f"[WARN] add_trade_visualization multi-inst failed: {e}")

    if selected_tuple and not clickData:
        rid_sel, inst_sel, idx_sel = selected_tuple
        if inst_sel in multi_data:
            _bars, _inds, trades_per_run_i = multi_data[inst_sel]
            tdf_sel = trades_per_run_i.get(rid_sel)
            if isinstance(tdf_sel, pd.DataFrame) and idx_sel in tdf_sel.index:
                try:
                    add_trade_visualization(price_fig, tdf_sel, multi_data[inst_sel][0], idx_sel)
                except Exception as e:
                    print(f"[WARN] add_trade_visualization persist multi-inst failed: {e}")

    # Metrics: prefer first active run if available
    metrics_children = html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'})
    # Build nested metrics map: { run_id: { inst: metrics_dict } }
    if active_runs:
        nested_metrics = {}
        for rid in active_runs:
            per_inst = {}
            for inst in instruments:
                metrics = None
                # disk-first lookup
                try:
                    results_root = getattr(repo, "results_root", None)
                    if results_root is None:
                        results_root = Path(__file__).resolve().parents[5] / "data" / "DATA_STORAGE" / "results"
                    run_dir = Path(results_root) / str(rid)
                    trade_metrics_path = run_dir / str(inst) / "trade_metrics.csv"
                    if trade_metrics_path.exists() and trade_metrics_path.is_file():
                        try:
                            dfm = pd.read_csv(trade_metrics_path)
                            if not dfm.empty:
                                metrics = dfm.iloc[0].to_dict()
                        except Exception:
                            pass
                except Exception:
                    pass
                # fallback to repo.load_metrics(run, inst) or repo.load_metrics(inst)
                if metrics is None and hasattr(repo, "load_metrics"):
                    try:
                        loaded = None
                        try:
                            loaded = repo.load_metrics(rid, inst)
                        except TypeError:
                            try:
                                loaded = repo.load_metrics(inst)
                            except Exception:
                                loaded = None
                        if loaded:
                            if isinstance(loaded, tuple) and isinstance(loaded[0], dict):
                                metrics, _ = loaded
                            elif isinstance(loaded, dict):
                                metrics = loaded
                            elif hasattr(loaded, "iloc"):
                                df2 = loaded
                                if not df2.empty:
                                    metrics = df2.iloc[0].to_dict()
                    except Exception:
                        pass
                if metrics:
                    per_inst[str(inst)] = metrics
            if per_inst:
                nested_metrics[str(rid)] = per_inst
        if nested_metrics:
            try:
                metrics_children = create_metrics_table(nested_metrics, [])
            except Exception:
                metrics_children = html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'})

    # Axis layout
    axis_layout = {}
    for i, inst in enumerate(instruments):
        axis_key = 'yaxis' if i == 0 else f'yaxis{i+1}'
        if i == 0:
            axis_layout[axis_key] = dict(
                title=dict(text=inst, font=dict(color=color_map.get(inst, "#000"))),
                tickfont=dict(color=color_map.get(inst, "#000")),
                showgrid=False, zeroline=False, showline=True,
                linecolor=color_map.get(inst, "#000")
            )
        else:
            # Entfernt: position=max(0.0, pos) -> führte zu rechter Leerfläche (Domain-Verkleinerung)
            axis_layout[axis_key] = dict(
                title=dict(text=inst, font=dict(color=color_map.get(inst, "#000"), size=11)),
                tickfont=dict(color=color_map.get(inst, "#000"), size=10),
                overlaying='y', side='right',
                showgrid=False, zeroline=False, showline=True,
                linecolor=color_map.get(inst, "#000")
            )
    price_fig.update_layout(**axis_layout)

    # Visibility buttons
    total = len(price_fig.data)
    candle_set = {i for i, tr in enumerate(price_fig.data) if isinstance(tr, go.Candlestick)}
    line_set = {i for i, tr in enumerate(price_fig.data) if isinstance(tr, go.Scatter) and ((getattr(tr, "uid", "") or "").startswith("line_"))}
    current_vis = [(tr.visible if tr.visible is not None else True) for tr in price_fig.data]
    vis_ohlc, vis_graph = [], []
    for i in range(total):
        if i in candle_set:
            vis_ohlc.append(True); vis_graph.append(False)
        elif i in line_set:
            vis_ohlc.append(False); vis_graph.append(True)
        else:
            vis_ohlc.append(current_vis[i]); vis_graph.append(current_vis[i])

    price_fig.update_layout(
        updatemenus=[dict(
            type='buttons',
            direction='right',
            x=1.0, xanchor='right',
            y=0.995, yanchor='top',
            pad=dict(r=2, t=2, b=2, l=2),
            bgcolor='rgba(255,255,255,0.40)',
            bordercolor='rgba(0,0,0,0.12)',
            borderwidth=1,
            font=dict(size=9),
            buttons=[
                dict(label='OHLC', method='update', args=[{'visible': vis_ohlc}]),
                dict(label='Graph', method='update', args=[{'visible': vis_graph}])
            ]
        )],
        template="plotly_white",
        hovermode="x unified",
        margin=dict(t=30, b=30, l=60, r=40),
        xaxis=dict(rangeslider=dict(visible=False)),
        legend=dict(
            orientation="h",
            x=0.01,
            y=0.99,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(255,255,255,0.55)",
            bordercolor="rgba(0,0,0,0.15)",
            borderwidth=1,
            font=dict(size=10),
            itemsizing="trace"
        )
    )
    price_fig.update_layout(uirevision="linked-range")
    eff_range = x_range or global_x_range
    if eff_range:
        price_fig.update_xaxes(
            range=eff_range,
            autorange=False,
            constrain="domain",
            rangebreaks=[]
        )

    # Indicator aggregation
    indicator_children = []
    global_groups = {}
    for inst in instruments:
        _bars_df_i, indicators_per_run_i, _tr_i = multi_data[inst]
        for ridx, rid in enumerate(active_runs):
            ind_map = indicators_per_run_i.get(rid, {}) or {}
            for name, df in ind_map.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    pid = int(df["plot_id"].iloc[0]) if "plot_id" in df.columns and len(df["plot_id"]) > 0 else 0
                    if pid > 0:
                        global_groups.setdefault(pid, []).append((inst, ridx, rid, name, df))

    PALETTE = _resolve_palette()
    unique_pairs = []
    for lst in global_groups.values():
        for inst, ridx, rid, name, df in lst:
            k = (rid, inst)
            if k not in unique_pairs:
                unique_pairs.append(k)

    color_map_ext = {}
    if unique_pairs:
        import hashlib, colorsys
        plen = len(PALETTE)
        for idx, key in enumerate(unique_pairs):
            if idx < plen:
                color_map_ext[key] = PALETTE[idx]
            else:
                hval = int(hashlib.md5(f"{key[0]}_{key[1]}".encode()).hexdigest(), 16)
                hue = (hval % 360) / 360.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.45, 0.70)
                color_map_ext[key] = f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"

    effective_range = eff_range
    multi_inst = len(instruments) > 1
    for pid, lst in sorted(global_groups.items()):
        fig_ind = go.Figure()
        shared_normalized_x = None
        for inst, ridx, rid, name, df in lst:
            nxs = _normalize_timestamps(df["timestamp"]) if "timestamp" in df.columns else df.index
            if shared_normalized_x is None:
                shared_normalized_x = nxs
            else:
                if len(nxs) == len(shared_normalized_x):
                    nxs = shared_normalized_x
            color = color_map_ext.get((rid, inst), "#000000")
            legend_name = f"{short_run_label(rid)}:{inst}:{name}"
            fig_ind.add_trace(go.Scatter(
                x=nxs,
                y=df["value"],
                mode="lines",
                name=legend_name,
                line=dict(color=color, width=2),
                hovertemplate=(
                    f"<b>{short_run_label(rid)} | {inst} | {name}</b><br>"
                    "%{x}<br>%{y:.4f}}<extra></extra>"
                )
            ))
        if effective_range:
            fig_ind.update_xaxes(
                range=effective_range,
                autorange=False,
                constrain="domain",
                rangebreaks=[]
            )
        fig_ind.update_layout(
            template="plotly_white",
            margin=dict(t=30, b=30, l=60, r=40),
            title=dict(
                text=f"Multi-Instrument Run Overlay: Plot {pid}",
                x=0.01, y=0.99, xanchor="left", yanchor="top",
                font=dict(size=14, color="#4a5568")
            ),
            hovermode="x unified",
            legend=dict(
                orientation="h",
                x=0.01,
                y=0.99,
                xanchor="left",
                yanchor="top",
                bgcolor="rgba(255,255,255,0.55)",
                bordercolor="rgba(0,0,0,0.15)",
                borderwidth=1,
                font=dict(size=10),
                itemsizing="trace"
            )
        )
        if multi_inst:
            # Dummy rechte Achse erzwingt identischen internen Plot-Bereich
            fig_ind.update_layout(
                yaxis2=dict(overlaying='y', side='right', position=0.95, showticklabels=False, showgrid=False, zeroline=False)
            )
        fig_ind.update_layout(uirevision="linked-range")
        indicator_children.append(
            dcc.Graph(
                id=f"multi-run-all-plot-{pid}",
                figure=fig_ind,
                style={"height": "300px", "marginBottom": "10px"}
            )
        )

    return price_fig, indicator_children, metrics_children, trade_details

def build_multi_run_view(state, repo, instruments, active_runs, clickData, chart_mode,
                         x_range, color_map, timeframe=None, show_trades=True, x_window=None):
    instruments = instruments or []
    active_runs = active_runs or []
    if not instruments:
        return go.Figure(), [], html.Div("No metrics available", style={'textAlign':'center','color':'#6c757d','padding':'20px'}), get_default_trade_details()
    if len(instruments) == 1:
        return _build_single_instrument_multi_run(
            state=state,
            repo=repo,
            instrument=instruments[0],
            active_runs=active_runs,
            clickData=clickData,
            chart_mode=chart_mode,
            x_range=x_range,
            timeframe=timeframe,  # NEW
            show_trades=show_trades,
            x_window=x_window  # NEW
        )
    return _build_multi_instrument_multi_run(
        state=state,
        repo=repo,
        instruments=instruments,
        active_runs=active_runs,
        clickData=clickData,
        chart_mode=chart_mode,
        x_range=x_range,
        color_map=color_map,
        timeframe=timeframe,  # NEW
        show_trades=show_trades,
        x_window=x_window  # NEW
    )

# ...existing code...
