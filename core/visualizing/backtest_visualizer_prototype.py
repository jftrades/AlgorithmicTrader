import pandas as pd
import os
from nautilus_trader.model.enums import OrderSide
from  tools.help_funcs.help_funcs_strategy import extract_interval_from_bar_type

class TradeInstance:
    def __init__(self, order):
        # SL/TP, type, action aus Tags extrahieren
        sl = None
        tp = None
        tag_type = None
        tag_action = None
        if hasattr(order, 'tags') and order.tags:
            for tag in order.tags:
                if tag.startswith("SL:"):
                    try:
                        sl = float(tag.split(":", 1)[1])
                    except Exception:
                        sl = None
                if tag.startswith("TP:"):
                    try:
                        tp = float(tag.split(":", 1)[1])
                    except Exception:
                        tp = None
                if tag.startswith("TYPE:"):
                    tag_type = tag.split(":", 1)[1]
                if tag.startswith("ACTION:"):
                    tag_action = tag.split(":", 1)[1]
        self.timestamp = order.ts_last
        self.tradesize = float(order.quantity)
        self.open_price_actual = None
        self.close_price_actual = None
        self.id = order.client_order_id 
        self.parent_id = order.parent_order_id if order.parent_order_id else None
        self.type = tag_type # "OPEN", "CLOSE"!!
        #self.action = tag_action # "BUY", "SHORT"!!
        self.sl = sl
        self.tp = tp
        self.realized_pnl = 0.0  # Wird später gesetzt, wenn der Trade geschlossen wird
        self.closed_timestamp = None  # Wird später gesetzt, wenn der Trade geschlossen wird
        if order.side == OrderSide.BUY:
            self.action = "BUY"
        elif order.side == OrderSide.SELL:
            self.action = "SHORT"
        else:
            self.action = None
            raise ValueError(f"Unbekannte OrderSide: {order.side}")


        self.price_desired = None
        self.fee = None
        self.bar_index = None

class IndicatorInstance:
    def __init__(self, name, plot_number=0):
        self.name = name
        self.plot_number = plot_number  # 0 -> in (bar) chart, 1 -> metrik plot 1 etc...


class BacktestDataCollector:
    def __init__(self, name, run_id, batch_size=5000): 
        self.name = name
        # Bars pro Timeframe
        self.bars = {}              # timeframe -> List[bar_dict]
        self.trades = []
        self.run_id = run_id
        self.indicators = {}
        self.indicator_plot_number = {}
        self.initialise_result_path()
        self.plots_at_minus_one = 0
        self.batch_size = batch_size
        

    def initialise_result_path(self):
        import shutil
        from pathlib import Path
        base_dir = Path(__file__).resolve().parents[2]
        self._results_root = base_dir / "data" / "DATA_STORAGE" / "results" / f"{self.run_id}"
        self.path = self._results_root / self.name  # Ordner pro Collector
        # Nur eigenen Ordner neu erstellen
        if self.path.exists() and self.path.is_dir():
            shutil.rmtree(self.path)
        (self.path / "indicators").mkdir(parents=True, exist_ok=True)
 
    def initialise_logging_indicator(self, name, plot_number): #indicator -> [indicator_name, plot_number]
        self.indicators[name] = []
        if plot_number == -1:
            plot_number = 1000 + self.plots_at_minus_one
            self.plots_at_minus_one += 1
        self.indicator_plot_number[name] = plot_number

    def add_bar(self, timestamp, open_, high, low, close, volume, bar_type):
        timeframe = extract_interval_from_bar_type(str(bar_type), str(bar_type.instrument_id))
        if timeframe not in self.bars:
            self.bars[timeframe] = []
        bar_dict = {
            'timestamp': timestamp,
            'open': open_,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
        }
        self.bars[timeframe].append(bar_dict)
        # flush when batch is full
        if len(self.bars[timeframe]) >= self.batch_size:
            self.flush_bars(timeframe)

    def add_indicator(self, name, timestamp, value):
        plot_number = self.indicator_plot_number.get(name, 0)
        if name not in self.indicators:
            self.indicators[name] = []
        self.indicators[name].append({
            'timestamp': timestamp,
            'value': value,
            'plot_id': plot_number,
        })
        # flush when batch is full
        if len(self.indicators[name]) >= self.batch_size:
            self.flush_indicators(name)

    def _append_df(self, file_path, df):
        header = not file_path.exists()
        df.to_csv(file_path, mode='a', header=header, index=False)

    def flush_bars(self, timeframe, force=False):
        """
        Schreibt einen Batch Bars für ein Timeframe in CSV.
        Bei force=True werden alle restlichen Bars geschrieben.
        """
        if timeframe not in self.bars or not self.bars[timeframe]:
            return
        entries = self.bars[timeframe]
        if not force and len(entries) < self.batch_size:
            return
        batch_size = len(entries) if force else self.batch_size
        batch = entries[:batch_size]
        # DataFrame mit konsistenter Reihenfolge
        df = pd.DataFrame(batch)
        cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols]
        file_path = self.path / f"bars-{timeframe}.csv"
        self._append_df(file_path, df)
        del entries[:batch_size]

    def flush_all_bars(self, force=False):
        for tf in list(self.bars.keys()):
            while True:
                before = len(self.bars[tf])
                self.flush_bars(tf, force=force)
                # Wenn force: nur einmal ausführen
                if force or len(self.bars[tf]) == before or len(self.bars[tf]) < self.batch_size:
                    break

    def flush_indicators(self, name, force=False):
        if name not in self.indicators or not self.indicators[name]:
            return
        entries = self.indicators[name]
        if not force and len(entries) < self.batch_size:
            return
        batch_size = len(entries) if force else self.batch_size
        batch = entries[:batch_size]
        df = pd.DataFrame(batch)
        if "plot_id" not in df.columns:
            plot_number = self.indicator_plot_number.get(name, 0)
            df["plot_id"] = int(plot_number)
        indicators_dir = self.path / "indicators"
        indicators_dir.mkdir(exist_ok=True)
        file_path = indicators_dir / f"{name}.csv"
        self._append_df(file_path, df)
        del entries[:batch_size]

    def flush_all_indicators(self, force=False):
        for name in list(self.indicators.keys()):
            while True:
                before = len(self.indicators[name])
                self.flush_indicators(name, force=force)
                if force or len(self.indicators[name]) == before or len(self.indicators[name]) < self.batch_size:
                    break

    def flush_all(self, force=False):
        """
        Flusht Bars & Indikatoren. Trades werden nicht gebatcht (wegen Metriken).
        """
        self.flush_all_bars(force=force)
        self.flush_all_indicators(force=force)

    def add_trade_details(self, order_filled, parent_id):
        """fills in price_actual and fee from OrderFilled event"""

        id = order_filled.client_order_id
        price_actual = order_filled.last_px
        #fee = order_filled.commission


        for trade in self.trades:
            if trade.id == id:
                trade.open_price_actual = price_actual
                #trade.fee = fee
                trade.parent_id = parent_id
                break

    def add_closed_trade(self, position_closed, fees):
        id = position_closed.opening_order_id
        closed_timestamp = position_closed.ts_closed
        realized_pnl = position_closed.realized_pnl
        close_price_actual = position_closed.avg_px_close
        # open_price_actual = position_closed.avg_px_open

        for trade in self.trades:
            if trade.id == id or (trade.parent_id is not None and trade.parent_id == id):
                trade.closed_timestamp = closed_timestamp
                trade.realized_pnl = realized_pnl
                trade.close_price_actual = close_price_actual
                trade.fee = fees
                #trade.open_price_actual = open_price_actual
                
        
    # In BacktestDataCollector:
    def add_trade(self, new_order):
        trade = TradeInstance(new_order)
        self.trades.append(trade)
        
    def bars_to_csv(self):
        """
        Restliche (nicht geflushte) Bars schreiben (Force-Flush).
        """
        self.flush_all_bars(force=True)
        # Dateien wurden bereits im Append-Modus erstellt -> nur Rückgabe der Dateinamen
        saved = []
        for tf in self.bars.keys():
            file_path = self.path / f"bars-{tf}.csv"
            if file_path.exists():
                saved.append(file_path.name)
        return saved

    def indicators_to_csv(self):
        self.flush_all_indicators(force=True)
        saved = []
        indicators_dir = self.path / "indicators"
        if indicators_dir.exists():
            for name in self.indicators.keys():
                file_path = indicators_dir / f"{name}.csv"
                if file_path.exists():
                    saved.append(f"indicators/{file_path.name}")
        return saved

    def analyse_trades(self):
        """
        Analysiert die Trades und gibt ein Dictionary mit Metriken zurück.
        Auch wenn keine Trades existieren, werden alle Keys mit 0 zurückgegeben
        (Placeholder), damit trade_metrics.csv immer erzeugt wird.
        """
        if not self.trades:
            return {
                "final_realized_pnl": 0.0,
                "winrate": 0.0,
                "winrate_long": 0.0,
                "winrate_short": 0.0,
                "pnl_long": 0.0,
                "pnl_short": 0.0,
                "long_short_ratio": 0.0,
                "n_trades": 0,
                "n_long_trades": 0,
                "n_short_trades": 0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "max_win": 0.0,
                "max_loss": 0.0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
                "commissions": 0.0,
            }

        def to_float(val):
            if hasattr(val, "amount"):
                return float(val.amount)
            try:
                return float(val)
            except Exception:
                return 0.0

        n_trades = len(self.trades)
        long_trades = [t for t in self.trades if t.action == "BUY"]
        short_trades = [t for t in self.trades if t.action == "SHORT"]
        n_long = len(long_trades)
        n_short = len(short_trades)

        # Aggregiertes PnL nach Richtung (neu)
        pnl_long = sum(to_float(t.realized_pnl) for t in long_trades)
        pnl_short = sum(to_float(t.realized_pnl) for t in short_trades)

        long_wins = [to_float(t.realized_pnl) for t in long_trades if to_float(t.realized_pnl) > 0]
        short_wins = [to_float(t.realized_pnl) for t in short_trades if to_float(t.realized_pnl) > 0]

        wins = [to_float(t.realized_pnl) for t in self.trades if to_float(t.realized_pnl) > 0]
        losses = [to_float(t.realized_pnl) for t in self.trades if to_float(t.realized_pnl) < 0]
        n_wins = len(wins)
        n_losses = len(losses)

        winrate = n_wins / n_trades if n_trades > 0 else 0.0
        winrate_long = len(long_wins) / n_long if n_long > 0 else 0.0
        winrate_short = len(short_wins) / n_short if n_short > 0 else 0.0
        long_short_ratio = n_long / n_short if n_short > 0 else float('inf') if n_long > 0 else 0.0
        avg_win = sum(wins) / n_wins if n_wins > 0 else 0.0
        avg_loss = sum(losses) / n_losses if n_losses > 0 else 0.0
        max_win = max(wins) if wins else 0.0
        max_loss = min(losses) if losses else 0.0
        commissions = sum([to_float(t.fee) for t in self.trades if t.fee is not None])

        # Max consecutive wins/losses
        max_consec_wins = max_consec_losses = 0
        curr_wins = curr_losses = 0
        for t in self.trades:
            pnl = to_float(t.realized_pnl)
            if pnl > 0:
                curr_wins += 1
                curr_losses = 0
            elif pnl < 0:
                curr_losses += 1
                curr_wins = 0
            else:
                curr_wins = 0
                curr_losses = 0
            max_consec_wins = max(max_consec_wins, curr_wins)
            max_consec_losses = max(max_consec_losses, curr_losses)

        final_realized_pnl = sum(to_float(t.realized_pnl) for t in self.trades)
        result = {
            "final_realized_pnl": final_realized_pnl,
            "winrate": winrate,
            "winrate_long": winrate_long,
            "winrate_short": winrate_short,
            "pnl_long": pnl_long,
            "pnl_short": pnl_short,
            "long_short_ratio": long_short_ratio,
            "n_trades": n_trades,
            "n_long_trades": n_long,
            "n_short_trades": n_short,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_win": max_win,
            "max_loss": max_loss,
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "commissions": commissions,
        }
        return result

    def trades_to_csv(self):
        # Immer erstellen, auch wenn keine Trades vorhanden sind
        trades_dicts = [vars(trade).copy() for trade in self.trades] if self.trades else []
        file_path = self.path / "trades.csv"
        if trades_dicts:
            pd.DataFrame(trades_dicts).to_csv(file_path, index=False)
        else:
            # Leere Datei mit erwarteten Spalten (Placeholder Header)
            pd.DataFrame(columns=[
                "timestamp","tradesize","open_price_actual","close_price_actual",
                "id","parent_id","type","sl","tp","realized_pnl","closed_timestamp",
                "action","price_desired","fee","bar_index"
            ]).to_csv(file_path, index=False)

        analysis = self.analyse_trades()
        metrics_path = self.path / "trade_metrics.csv"
        pd.DataFrame([analysis]).to_csv(metrics_path, index=False)
        return analysis

    def _clear_memory(self):
        """
        Leert nach Persistierung alle gesammelten In-Memory-Daten
        (Bars, Indicatorwerte, Trades). Plot-Mapping bleibt erhalten.
        """
        self.bars = {}
        # Nur Werte leeren, Mapping behalten
        for k in list(self.indicators.keys()):
            self.indicators[k].clear()
        self.indicators = {}
        self.trades = []

    def save_data(self):
        """
        Force-Flush + finale Trade- & Metrik-Dateien, danach Speicher leeren.
        """
        logging_message = ""
        try:
            # flush remaining batches
            self.flush_all(force=True)
            bars_files = self.bars_to_csv()
            ind_files = self.indicators_to_csv()
            trades_file = self.trades_to_csv()  # Trades nicht gebatcht
            # Speicher jetzt leeren
            self._clear_memory()
            parts = []
            if bars_files:
                parts.append(f"bars={bars_files}")
            if ind_files:
                parts.append(f"indicators={ind_files}")
            if trades_file:
                parts.append(f"trades={trades_file}")
            if not parts:
                parts.append("no data")
            logging_message = f"[{self.name}] saved -> {'; '.join(parts)} in {self.path}"
        except Exception as e:
            logging_message = f"[{self.name}] Error while saving CSV files: {e}"
        return logging_message
    
    #def load_data(self, path):

    def visualize(self, visualize_after_backtest=False):
        """
        Visualizes the collected data.
        This method should only be called if visualize_after_backtest=True is set.
        """
        if not visualize_after_backtest:
            raise ValueError("Visualization is disabled. Set visualize_after_backtest=True to enable it.")
        else:
            pass
