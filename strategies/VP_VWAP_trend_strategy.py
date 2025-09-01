# in here will be the code for the VP_VWAP_trend_strategy
# the VP will be used if broken to indicate trend day and VWAP will be used for entry

from decimal import Decimal
from typing import Any, Dict, List

from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.common.enums import LogColor

from tools.help_funcs.base_strategy import BaseStrategy
from tools.order_management.order_types import OrderTypes
from tools.order_management.risk_manager import RiskManager

from tools.indicators.VWAP_ZScore_intraday import VWAPZScoreIntraday


class VPVWAPTrendStrategyConfig(StrategyConfig):
    instruments: List[dict]  # Each entry: {"instrument_id": <InstrumentId>, "bar_types": List of <BarType>, "trade_size_usdt": <Decimal|int|float>}
    risk_percent: float
    max_leverage: float
    min_account_balance: float
    run_id: str
    close_positions_on_stop: bool = True

class VPVWAPTrendStrategy(BaseStrategy, Strategy):
    def __init__(self, config: VPVWAPTrendStrategyConfig):
        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        super().__init__(config)
    
        # Remove: primary instrument derivations (self.instrument_id, self.bar_type, etc.)
        self.risk_manager = None
        self.order_types = None
        self.add_instrument_context()

    def add_instrument_context(self):
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
        for current_instrument in self.instrument_dict.values():
            # Initialize standard indicators
            current_instrument["collector"].initialise_logging_indicator("position", 1)
            current_instrument["collector"].initialise_logging_indicator("realized_pnl", 2)
            current_instrument["collector"].initialise_logging_indicator("unrealized_pnl", 3)
            current_instrument["collector"].initialise_logging_indicator("balance", 4)
            
            # Add strategy-specific context here
            # current_instrument["my_indicator"] = MyIndicator(period=20)
            current_instrument["bar_counter"] = 0

    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                self.log.info(f"Subscribing to bars: {str(bar_type)}", color=LogColor.GREEN)
                self.subscribe_bars(bar_type)
        
        self.log.info(f"Strategy started. Instruments: {', '.join(str(i) for i in self.instrument_ids())}")
        
        # Initialize risk and order management
        self.risk_manager = RiskManager(
            self,
            Decimal(str(self.config.risk_percent)),
            Decimal(str(self.config.max_leverage)),
            Decimal(str(self.config.min_account_balance)),
        )
        self.order_types = OrderTypes(self)

    # -------------------------------------------------
    # Event Routing
    # -------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.bar_type.instrument_id
        current_instrument = self.instrument_dict.get(instrument_id)
        if current_instrument is None:
            return

        current_instrument["bar_counter"] += 1
        
        # Update indicators with bar data
        # current_instrument['my_indicator'].handle_bar(bar)
        # if not current_instrument['my_indicator'].initialized:
        #     return
        
        # Check for pending orders to avoid endless order loops
        open_orders = self.cache.orders_open(instrument_id=instrument_id)
        if open_orders:
            return
            
        self.entry_logic(bar, current_instrument)
        self.base_collect_bar_data(bar, current_instrument)
        self.update_visualizer_data(bar, current_instrument)

    # -------------------------------------------------
    # Entry Logic per Instrument
    # -------------------------------------------------
    def entry_logic(self, bar: Bar, current_instrument: Dict[str, Any]):
        instrument_id = bar.bar_type.instrument_id
        trade_size_usdt = float(current_instrument["trade_size_usdt"])
        qty = max(1, int(trade_size_usdt / float(bar.close)))
        
        # Example trading logic (replace with your own):
        # indicator_value = current_instrument["my_indicator"].value
        # if indicator_value is None:
        #     return
        #
        # if some_condition:
        #     self.submit_long_market_order(instrument_id, qty)
        # elif some_other_condition:
        #     self.submit_short_market_order(instrument_id, qty)
        pass

    # -------------------------------------------------
    # Order Submission Wrappers
    # -------------------------------------------------
    def submit_long_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_long_market_order(instrument_id, qty)

    def submit_short_market_order(self, instrument_id: InstrumentId, qty: int):
        self.order_types.submit_short_market_order(instrument_id, qty)

    # -------------------------------------------------
    # Visualizer / Logging per Instrument
    # -------------------------------------------------
    def update_visualizer_data(self, bar: Bar, current_instrument: Dict[str, Any]) -> None:
        inst_id = bar.bar_type.instrument_id
        self.base_update_standard_indicators(bar.ts_event, current_instrument, inst_id)
        
        # Add custom indicators here:
        # indicator_value = float(current_instrument["my_indicator"].value) if current_instrument["my_indicator"].value is not None else None
        # current_instrument["collector"].add_indicator(timestamp=bar.ts_event, name="my_indicator", value=indicator_value)
        
    def on_order_filled(self, order_filled) -> None:
        return self.base_on_order_filled(order_filled)

    def on_position_closed(self, position_closed) -> None:
        return self.base_on_position_closed(position_closed)

    def on_error(self, error: Exception) -> None:
        return self.base_on_error(error)
    
    def close_position(self, instrument_id: InstrumentId = None) -> None:
        if instrument_id is None:
            raise ValueError("InstrumentId required (no global primary instrument anymore).")
        position = self.base_get_position(instrument_id)
        return self.base_close_position(position)