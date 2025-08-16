# Standard Library Importe
from decimal import Decimal
import time
from typing import Any, Dict, Optional, List

# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, TradeTick, BarType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.common.enums import LogColor

# Nautilus Strategie spezifische Importe
from tools.help_funcs.base_strategy import BaseStrategy
from tools.structure.TTTbreakout import TTTBreakout_Analyser
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from tools.help_funcs.help_funcs_strategy import create_tags
from nautilus_trader.common.enums import LogColor
from  tools.help_funcs.help_funcs_strategy import extract_interval_from_bar_type

# Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex

# -------------------------------------------------
# Multi-Instrument Konfiguration (jetzt Pflicht)
# -------------------------------------------------
class AlphaMemeStrategyConfig(StrategyConfig):
    instruments: List[dict]  # Jeder Eintrag: {"instrument_id": <InstrumentId>, "bar_types": List of <BarType>, "trade_size_usdt": <Decimal|int|float>}
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    close_positions_on_stop: bool = True


class AlphaMemeStrategy(BaseStrategy, Strategy):
    def __init__(self, config: AlphaMemeStrategyConfig):
        super().__init__(config)
        
        self.close_positions_on_stop = config.close_positions_on_stop
        self.stopped = False
        self.realized_pnl = 0

        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        self._initialize_instrument_contexts()
        # Entfernt: primäre Instrument-Ableitungen (self.instrument_id, self.bar_type, etc.)
        self.risk_manager = None
        self.order_types = None

    def _initialize_instrument_contexts(self):
        if not self.config.instruments or len(self.config.instruments) == 0:
            raise ValueError("RSISimpleStrategyConfig.instruments muss mindestens ein Instrument enthalten.")
        for spec in self.config.instruments:
            inst_id = spec["instrument_id"]
            bar_types = spec["bar_types"]
            #test = spec["test"]
            trade_size_usdt = Decimal(str(spec["trade_size_usdt"]))
            rsi_period = spec.get("rsi_period", self.config.rsi_period)
            rsi_overbought = spec.get("rsi_overbought", self.config.rsi_overbought)
            rsi_oversold = spec.get("rsi_oversold", self.config.rsi_oversold)

            # Sichere, neue Liste (keine Mutation der YAML-Liste)
            converted_bar_types = []
            for bt in bar_types:
                if isinstance(bt, BarType):
                    converted_bar_types.append(bt)
                else:
                    converted_bar_types.append(BarType.from_str(bt))
                    
            if not converted_bar_types:
                raise ValueError(f"{inst_id}: Keine gültigen bar_types nach Konvertierung.")
            
            inst_id = InstrumentId.from_str(inst_id)
            current_instrument = {
                "instrument_id": inst_id,
                "bar_types": converted_bar_types,  # eigene Liste pro Instrument
                "trade_size_usdt": trade_size_usdt,
                "rsi": RelativeStrengthIndex(period=rsi_period),
                "rsi_period": rsi_period,
                "rsi_overbought": rsi_overbought,
                "rsi_oversold": rsi_oversold,
                "last_rsi_cross": None,
                "realized_pnl": 0.0,
                "collector": BacktestDataCollector(str(inst_id)),
            }
            current_instrument["collector"].initialise_logging_indicator("RSI", 1)
            current_instrument["collector"].initialise_logging_indicator("position", 2)
            current_instrument["collector"].initialise_logging_indicator("realized_pnl", 3)
            current_instrument["collector"].initialise_logging_indicator("unrealized_pnl", 4)
            current_instrument["collector"].initialise_logging_indicator("equity", 5)
            self.instrument_dict[inst_id] = current_instrument

    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                #if isinstance(bar_type, BarType):
                self.log.info(str(bar_type), color=LogColor.GREEN)
                self.subscribe_bars(bar_type)
                #else:
                    #raise ValueError(f"BarType (String) muss vorher in BarType konvertiert werden: {bar_type}")
        self.log.info(f"Strategy started. Instruments: {', '.join(str(i) for i in self.instrument_ids())}")
        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)

    # -------------------------------------------------
    # Hilfsfunktionen
    # -------------------------------------------------


    # -------------------------------------------------
    # Ereignis Routing
    # -------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return
        rsi = current_instrument["rsi"]
        rsi.handle_bar(bar)
        if not rsi.initialized:
            return
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
        self.entry_logic(bar, current_instrument)
        self.collect_bar_data(bar, current_instrument)

    def collect_bar_data(self, bar: Bar, current_instrument: Dict[str, Any]):
        current_instrument["collector"].add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close, bar_type = bar.bar_type)
        self.update_visualizer_data(bar, current_instrument)
        self._update_general_metrics(bar.ts_event)

    # -------------------------------------------------
    # Entry Logic pro Instrument
    # -------------------------------------------------
    def entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = trade_size_usdt / float(bar.close)
        rsi_value = current_instrument["rsi"].value
        if rsi_value is None:
            return
        last_cross = current_instrument["last_rsi_cross"]
        overbought = current_instrument["rsi_overbought"]
        oversold = current_instrument["rsi_oversold"]

        if rsi_value > overbought:
            if last_cross != "rsi_overbought":
                self.close_position(instrument_id)
                self.submit_short_market_order(instrument_id, qty)
            current_instrument["last_rsi_cross"] = "rsi_overbought"
        elif rsi_value < oversold:
            if last_cross != "rsi_oversold":
                self.close_position(instrument_id)
                self.submit_long_market_order(instrument_id, qty)
            current_instrument["last_rsi_cross"] = "rsi_oversold"

    # -------------------------------------------------
    # Order Submission Wrapper (Instrument-Aware, intern noch Single)
    # -------------------------------------------------
    def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_long_market_order(instrument_id, qty)

    def submit_short_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    # -------------------------------------------------
    # Visualizer / Logging pro Instrument
    # -------------------------------------------------
    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        #net_position = self.portfolio.net_position(inst_id)
        net_exp = self.portfolio.net_exposure(inst_id).as_double()
        if self.portfolio.is_net_short(inst_id):
            net_exp = -net_exp
        #self.log.info(str(net_exp), color=LogColor.CYAN)
        unrealized_pnl = self.portfolio.unrealized_pnl(inst_id)
        realized_pnl = self.portfolio.total_pnl(inst_id)
        venue = inst_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total()
        equity = usdt_balance.as_double() + (float(unrealized_pnl) if unrealized_pnl else 0)
        rsi_value = float(current_instrument["rsi"].value) if current_instrument["rsi"].value is not None else None
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="position", value=net_exp)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="realized_pnl", value=float(current_instrument["realized_pnl"]))
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="equity", value=equity)
        # Nach Einzel-Instrument Update -> Aggregierte Kennzahlen
        
    # -------------------------------------------------
    # Stop / Abschluss Handling
    # -------------------------------------------------
    def on_stop(self) -> None:
        self.base_on_stop()
        self.stopped = True
        # Aggregiere pro Instrument
        for inst_id, current_instrument in self.instrument_dict.items():
            net_position = self.portfolio.net_exposure(inst_id).as_double()
            unrealized_pnl = self.portfolio.unrealized_pnl(inst_id)
            realized_pnl_component = float(self.portfolio.realized_pnl(inst_id))
            current_instrument["realized_pnl"] += (float(unrealized_pnl) if unrealized_pnl else 0) + realized_pnl_component
            unrealized_pnl = 0
            venue = inst_id.venue
            account = self.portfolio.account(venue)
            usdt_balance = account.balance_total()
            equity = usdt_balance.as_double() + unrealized_pnl
            #ts_now = self.clock.timestamp_ns()
            # timeframe ist z. B. "1m" oder "5m"

            bar_types = current_instrument["bar_types"]

            last_timestamp = max(current_instrument["collector"].bars[extract_interval_from_bar_type(str(bt), str(bt.instrument_id))][-1]["timestamp"] for bt in bar_types)
            #current_instrument["collector"].add_indicator(timestamp=last_timestamp, name="equity", value=equity)
            current_instrument["collector"].add_indicator(timestamp=last_timestamp, name="position", value=net_position if net_position is not None else None)
            current_instrument["collector"].add_indicator(timestamp=last_timestamp, name="unrealized_pnl", value=0.0)
            current_instrument["collector"].add_indicator(timestamp=last_timestamp, name="realized_pnl", value=float(current_instrument["realized_pnl"]))
            logging_message = f"{inst_id}: " + current_instrument["collector"].save_data()
            self.log.info(logging_message, color=LogColor.GREEN)
            # Legacy aggregat
            self.realized_pnl += current_instrument["realized_pnl"]
        # Nach Instrument-Aggregation finaler General-Snapshot
        ts_now = self.clock.timestamp_ns()
        self._update_general_metrics(ts_now)
        general_msg = self.general_collector.save_data()
        self.log.info(f"GENERAL: {general_msg}", color=LogColor.GREEN)



    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: Optional[InstrumentId] = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId erforderlich (kein globales primäres Instrument mehr).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)

