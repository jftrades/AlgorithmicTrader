# Standard Library Importe
from decimal import Decimal
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
    run_id: str
    close_positions_on_stop: bool = True


class AlphaMemeStrategy(BaseStrategy, Strategy):
    def __init__(self, config: AlphaMemeStrategyConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config)
    
        # Entfernt: primäre Instrument-Ableitungen (self.instrument_id, self.bar_type, etc.)
        self.risk_manager = None
        self.order_types = None
        self.add_instrument_context()


    def add_instrument_context(self):
        for current_instrument in self.instrument_dict.values():
            rsi_period = current_instrument.get("rsi_period", getattr(self.config, "rsi_period"))
            rsi_overbought = current_instrument.get("rsi_overbought", getattr(self.config, "rsi_overbought"))
            rsi_oversold = current_instrument.get("rsi_oversold", getattr(self.config, "rsi_oversold"))
            current_instrument["collector"].initialise_logging_indicator("RSI", 1)
            current_instrument["rsi_period"] = rsi_period
            current_instrument["rsi_overbought"] = rsi_overbought
            current_instrument["rsi_oversold"] = rsi_oversold
            current_instrument["rsi"] = RelativeStrengthIndex(period=rsi_period)
            current_instrument["last_rsi_cross"] = None

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
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

    # -------------------------------------------------
    # Entry Logic pro Instrument
    # -------------------------------------------------
    def entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, trade_size_usdt / float(bar.close))
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
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)
        #custom indicators
        rsi_value = float(current_instrument["rsi"].value) if current_instrument["rsi"].value is not None else None
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="RSI", value=rsi_value)
        
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

