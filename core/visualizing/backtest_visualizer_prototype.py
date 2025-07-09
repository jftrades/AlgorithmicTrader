import pandas as pd
import os
from nautilus_trader.model.enums import OrderSide

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

class IndicatorInstance:
    def __init__(self, name, plot_number=0):
        self.name = name
        self.plot_number = plot_number  # 0 -> in (bar) chart, 1 -> metrik plot 1 etc...


class BacktestDataCollector:
    def __init__(self): 
        self.bars = []  # OHLC mit timestamp
        self.trades = []  # dicts: timestamp, tradesize, buy_inprice, tp, sl, long
        self.indicators = {}  # name -> list of dicts: timestamp, value
        self.indicator_plot_number = {}  # name -> plot_number -- 0 -> in (bar) chart, 1 -> metrik plot 1 etc...
        self.initialise_result_path()

    def initialise_result_path(self):
        import shutil
        from pathlib import Path
        # Gehe von core/visualizing/ auf AlgorithmicTrader/
        base_dir = Path(__file__).resolve().parents[2]
        self.path = base_dir / "data" / "DATA_STORAGE" / "results"
        if self.path.exists() and self.path.is_dir():
            shutil.rmtree(self.path)
        os.makedirs(self.path, exist_ok=True)
 
    def initialise_logging_indicator(self, name, plot_number): #indicator -> [indicator_name, plot_number]
        self.indicators[name] = []
        self.indicator_plot_number[name] = plot_number

    def add_bar(self, timestamp, open_, high, low, close):
        self.bars.append({
            'timestamp': timestamp,
            'open': open_,
            'high': high,
            'low': low,
            'close': close
        })

    def add_indicator(self, name, timestamp, value):
        if name not in self.indicators:
            self.indicators[name] = []
        self.indicators[name].append({
            'timestamp': timestamp,
            'value': value
        })

    def add_trade_details(self, order_filled):
        """
        Füllt die Details des Trades aus einem OrderFilled-Objekt.
        Sucht in self.trades nach passender id und ergänzt price_actual und fee.
        """

        id = order_filled.client_order_id
        price_actual = order_filled.last_px
        fee = order_filled.commission

        for trade in self.trades:
            if trade.id == id:
                trade.open_price_actual = price_actual
                trade.fee = fee
                break

    def add_closed_trade(self, position_closed):
        id = position_closed.opening_order_id
        closed_timestamp = position_closed.ts_closed
        realized_pnl = position_closed.realized_pnl
        close_price_actual = position_closed.avg_px_close
        open_price_actual = position_closed.avg_px_open

        for trade in self.trades:
            if trade.id == id:
                trade.closed_timestamp = closed_timestamp
                trade.realized_pnl = realized_pnl
                trade.close_price_actual = close_price_actual
                trade.open_price_actual = open_price_actual
                break
        
    # In BacktestDataCollector:
    def add_trade(self, new_order):
        # ... Werte extrahieren ...
        trade = TradeInstance(new_order)
        self.trades.append(trade)

        # order.id                -> OrderId-Objekt (eindeutige Order-ID)
        # order.instrument_id     -> InstrumentId-Objekt (welches Instrument)
        # order.order_side        -> OrderSide (BUY oder SELL)
        # order.quantity          -> OrderQty-Objekt (ursprüngliche Ordermenge)
        # order.filled_qty        -> OrderQty-Objekt (bereits ausgeführte Menge)
        # order.avg_price         -> Decimal (durchschnittlicher Ausführungspreis)
        # order.status            -> OrderStatus (aktueller Status, z.B. FILLED)
        # order.ts_event          -> int (Zeitstempel des letzten Events in Nanosekunden)
        # order.exec_algorithm_id -> ExecAlgorithmId (falls mit Algo ausgeführt)
        # order.exec_algorithm_params -> dict (Algo-Parameter)
        # order.time_in_force     -> TimeInForce (z.B. FOK, GTC)
        # order.parent_id         -> OrderId (falls Parent-Order)
        # order.client_order_id   -> str (falls gesetzt)
        # order.price             -> Decimal (Limitpreis, falls LimitOrder)
        # order.type              -> OrderType (MARKET, LIMIT, etc.)
        
    def bars_to_csv(self):
        pd.DataFrame(self.bars).to_csv(self.path / "bars.csv", index=False)

    def indicators_to_csv(self):
        (self.path / "indicators").mkdir(exist_ok=True)
        for name, data in self.indicators.items():
            plot_number = self.indicator_plot_number.get(name, 0)
            df = pd.DataFrame(data)
            df["plot_number"] = plot_number
            df.to_csv(self.path / "indicators" / f"{name}.csv", index=False)

    def trades_to_csv(self):
        # Convert TradeInstance objects to dicts for DataFrame
        trades_dicts = []
        for trade in self.trades:
            d = vars(trade).copy()
            # Remove any non-serializable fields if needed
            trades_dicts.append(d)
        pd.DataFrame(trades_dicts).to_csv(self.path / "trades.csv", index=False)

    def save_data(self):
        logging_message = ""
        try:
            self.bars_to_csv()
            self.indicators_to_csv()
            self.trades_to_csv()
            logging_message = f"All data saved successfully to {self.path}"
        except Exception as e:
            logging_message = f"Error while saving CSV files: {e}"
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
