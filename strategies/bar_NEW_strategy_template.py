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


# Strategiespezifische Importe
from nautilus_trader.indicators.rsi import RelativeStrengthIndex

# -------------------------------------------------
# Multi-Instrument Konfiguration (jetzt Pflicht)
# -------------------------------------------------
class RSISimpleStrategyConfig(StrategyConfig):
    instruments: List[dict]  
    param_aus_yaml1: float
    param_aus_yaml2: int
    min_account_balance: float

    #params that should always be included
    run_id: str
    close_positions_on_stop: bool = True


class RSISimpleStrategy(BaseStrategy, Strategy):
    def __init__(self, config: RSISimpleStrategyConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config)
    
        self.risk_manager = None
        self.order_types = None
        self.add_instrument_context()


    def add_instrument_context(self):
        #the self.instrument_dict is automatically filled by the BaseStrategy
        """
        Struktur von self.instrument_dict (gefüllt in BaseStrategy.__init__ / deren Helper):

        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]]

        Beispiel (konzeptionell):
        {
          InstrumentId("BTCUSDT-PERP","BINANCE"): {
            "instrument_id": InstrumentId("BTCUSDT-PERP","BINANCE"),
            "bar_types": [BarType(...15-MINUTE...), BarType(...5-MINUTE...)],
            # Alle YAML-Schlüssel des Instruments (dynamisch übernommen):
            "instrument param XY": Decimal('100'),
            # Basis-Keys, die BaseStrategy immer hinzufügt:
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "collector": BacktestDataCollector(...),
          },
          InstrumentId("ETHUSDT-PERP","BINANCE"): {
            ... gleiche Struktur ...
          }
        }

        """
        
        # hier fügtr man eigene Kontexte pro Instrument hinzu
        # Strategy-spezifische / nachträglich ergänzte Keys (hier in add_instrument_context):
        """
            "rsi_period": 10,
            "rsi_overbought": 0.75,
            "rsi_oversold": 0.25,
            "rsi": RelativeStrengthIndex(...),
            "last_rsi_cross": None,
            # Weitere mögliche spätere Ergänzungen:
            # "param_aus_yaml1": <Wert>,
            # "indicator_XY": <Wert>,
        """
        for current_instrument in self.instrument_dict.values():
            param_aus_yaml1 = current_instrument.get("param_aus_yaml1", getattr(self.config, "param_aus_yaml1"))
            current_instrument["collector"].initialise_logging_indicator("indicator_XY", 1)
            current_instrument["param_aus_yaml1"] = param_aus_yaml1


    def on_start(self) -> None:
        #subscribe to all bars of all instruments
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                #if isinstance(bar_type, BarType):
                self.log.info(str(bar_type), color=LogColor.GREEN)
                self.subscribe_bars(bar_type) 
        self.log.info(f"Strategy started. Instruments: {', '.join(str(i) for i in self.instrument_ids())}")
        self.risk_manager = RiskManager(self, Decimal(str(self.config.risk_percent)), Decimal(str(self.config.max_leverage)), Decimal(str(self.config.min_account_balance)),)
        self.order_types = OrderTypes(self)

    # -------------------------------------------------
    # Ereignis Routing
    # -------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)

        self.entry_logic(bar, current_instrument)
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

    # -------------------------------------------------
    # Entry Logic pro Instrument
    # -------------------------------------------------
    def entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        qty = 1 # has to be calcualted
        #example on how to palce orders:
        self.submit_short_market_order(instrument_id, qty)
        self.submit_long_market_order(instrument_id, qty)
        self.close_position(instrument_id)

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
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id) #logs all relevant basic data
        #custom indicators -> add indicatos for visualiser (such as RSI, ..)
        indicatorXY_value = float(current_instrument["indicatorXY"])
        current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="indicatorXY", value=indicatorXY_value)
        

    # -------------------------------------------------
    # Help Functions
    # -------------------------------------------------

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

