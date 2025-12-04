from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from decimal import Decimal
from nautilus_trader.common.enums import LogColor
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector
from typing import Any, Dict, Optional
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.currencies import USDT
from  tools.help_funcs.help_funcs_strategy import extract_interval_from_bar_type


class BaseStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.stopped = False
        self.realized_pnl = 0
        self.close_positions_on_stop = config.close_positions_on_stop
        self.run_id = config.run_id

        self.instrument_dict: Dict[InstrumentId, Dict[str, Any]] = {}
        self._base_initialize_instrument_contexts()
        self.general_collector = BacktestDataCollector("general", config.run_id)
        self.general_collector.initialise_logging_indicator("total_position", 1)
        self.general_collector.initialise_logging_indicator("total_unrealized_pnl", 2)
        self.general_collector.initialise_logging_indicator("total_realized_pnl", 3)
        self.general_collector.initialise_logging_indicator("total_equity", 4)

    def _base_initialize_instrument_contexts(self):
        """
        Build self.instrument_dict dynamically:
        - Copies all per-instrument YAML keys (except instrument_id, bar_types) into current_instrument.
        - Converts bar_types to BarType objects.
        - Attempts Decimal conversion for numeric-looking string values.
        - Adds mandatory runtime keys (realized/unrealized pnl, collector, RSI components, etc.).
        """
        if not getattr(self.config, "instruments", None):
            raise ValueError("RSISimpleStrategyConfig.instruments muss mindestens ein Instrument enthalten.")

        self.instrument_dict = {}

        def _maybe_decimal(val):
            if isinstance(val, str):
                try:
                    # accept plain int/float strings
                    Decimal(val)
                    return Decimal(val)
                except Exception:
                    return val
            return val

        for spec in self.config.instruments:
            if "instrument_id" not in spec or "bar_types" not in spec:
                raise ValueError("Jedes Instrument benötigt 'instrument_id' und 'bar_types'.")

            inst_id_str = spec["instrument_id"]
            bar_types_raw = spec["bar_types"]

            # Convert bar types
            converted_bar_types = []
            for bt in bar_types_raw:
                if isinstance(bt, BarType):
                    converted_bar_types.append(bt)
                else:
                    converted_bar_types.append(BarType.from_str(bt))
            if not converted_bar_types:
                raise ValueError(f"{inst_id_str}: Keine gültigen bar_types nach Konvertierung.")

            inst_id = InstrumentId.from_str(inst_id_str)

            # Start with dynamic copy of all extra keys
            current_instrument = {}
            for k, v in spec.items():
                if k in ("instrument_id", "bar_types"):
                    continue
                current_instrument[k] = _maybe_decimal(v)

            # Mandatory baseline keys (override if collisions)
            current_instrument["instrument_id"] = inst_id
            current_instrument["bar_types"] = converted_bar_types
            current_instrument.setdefault("realized_pnl", 0.0)
            current_instrument.setdefault("unrealized_pnl", 0.0)

            # Collector
            collector = BacktestDataCollector(str(inst_id), self.run_id)
            collector.initialise_logging_indicator("position", -1)
            collector.initialise_logging_indicator("realized_pnl", -1)
            collector.initialise_logging_indicator("unrealized_pnl", -1)
            collector.initialise_logging_indicator("equity", -1)
            current_instrument["collector"] = collector

            self.instrument_dict[inst_id] = current_instrument

    def instrument_ids(self):
        return list(self.instrument_dict.keys())
    
    def get_instrument_context(self, instrument_id):
        return self.instrument_dict[instrument_id]
    
    def calculate_risk_based_position_size(self, instrument_id: InstrumentId, entry_price: float, stop_loss_price: float) -> int:
        entry_price_decimal = Decimal(str(entry_price))
        stop_loss_price_decimal = Decimal(str(stop_loss_price))
        
        # Handle FieldInfo objects - convert to dict if needed
        exp_growth_config = self.config.exp_growth_atr_risk if isinstance(self.config.exp_growth_atr_risk, dict) else {}
        log_growth_config = self.config.log_growth_atr_risk if isinstance(self.config.log_growth_atr_risk, dict) else {}
        
        if exp_growth_config.get("enabled", False):
            risk_percent = Decimal(str(exp_growth_config["risk_percent"]))
            exact_contracts = self.risk_manager.exp_growth_atr_risk(entry_price_decimal, stop_loss_price_decimal, risk_percent)
            return round(float(exact_contracts))
        
        if log_growth_config.get("enabled", False):
            risk_percent = Decimal(str(log_growth_config["risk_percent"]))
            exact_contracts = self.risk_manager.log_growth_atr_risk(entry_price_decimal, stop_loss_price_decimal, risk_percent)
            return round(float(exact_contracts))
        
        return self.calculate_fixed_position_size(instrument_id, entry_price)

    def calculate_fixed_position_size(self, instrument_id: InstrumentId, entry_price: float) -> int:
        entry_price_decimal = Decimal(str(entry_price)) 
        
        # Handle FieldInfo objects - convert to dict if needed
        exp_fixed_config = self.config.exp_fixed_trade_risk if isinstance(self.config.exp_fixed_trade_risk, dict) else {}
        log_fixed_config = self.config.log_fixed_trade_risk if isinstance(self.config.log_fixed_trade_risk, dict) else {}
        
        if exp_fixed_config.get("enabled", False):
            invest_percent = Decimal(str(exp_fixed_config["invest_percent"]))
            qty = self.risk_manager.exp_fixed_trade_risk(entry_price_decimal, invest_percent)
            return round(float(qty))
        
        if log_fixed_config.get("enabled", False):
            investment_size = Decimal(str(log_fixed_config["investment_size"]))
            qty = self.risk_manager.log_fixed_trade_risk(entry_price_decimal, investment_size)
            return round(float(qty))
        
        return 0
    
    def on_start(self) -> None:
        for inst_id, ctx in self.instrument_dict.items():
            for bar_type in ctx["bar_types"]:
                self.log.info(f"BaseStrategy: Subscribing to {bar_type}", color=LogColor.CYAN)
                self.subscribe_bars(bar_type)
                
    def base_get_position(self, instrument_id):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=instrument_id)
            if positions:
                return positions[0]
        return None

    def base_close_position(self, position) -> None:
        if position is not None and position.is_open:
            super().close_position(position)
        
    def base_on_stop(self) -> None:
        for id in self.instrument_ids():
            position = self.base_get_position(id)
            if self.close_positions_on_stop:
                self.base_close_position(position)
            self.log.info("Strategy stopped!")

    def base_on_order_filled(self, order_filled) -> None:
        id = order_filled.instrument_id 
        id_ctx = self.get_instrument_context(id)
        position = self.cache.position(order_filled.position_id)
        parent_id = position.opening_order_id
        id_ctx["collector"].add_trade_details(order_filled, parent_id)

    def base_on_position_closed(self, position_closed) -> None:
        pos_id = position_closed.position_id 
        pos = self.cache.position(pos_id)
        fees = pos.commissions()
        total_fee = 0
        for fee in fees:
            total_fee += fee.as_double()
        id  = position_closed.instrument_id
        id_ctx = self.get_instrument_context(id)
        realized_pnl = position_closed.realized_pnl.as_double()  # Realized PnL
        id_ctx["realized_pnl"] += float(realized_pnl) if realized_pnl else 0
        #id_ctx["commissions"] += float(position_closed.commission) if position_closed.commission else 0
        id_ctx["collector"].add_closed_trade(position_closed, total_fee)

    def base_on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        self.base_on_stop()
        self.stop()

    def base_collect_bar_data(self, bar: Bar, current_instrument: Dict[str, Any]):
        current_instrument["collector"].add_bar(timestamp=bar.ts_event, open_=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, bar_type = bar.bar_type)
        self._update_general_metrics(bar.ts_event)

    def _update_general_metrics(self, ts):
        # Aggregation über alle Instrumente
        total_position = 0.0
        total_unrealized = 0.0
        total_realized = 0.0
        seen_venues = set()
        total_balances = 0.0
        for inst_id, data in self.instrument_dict.items():
            net_pos = self.portfolio.net_exposure(inst_id)    
            if net_pos is not None:
                if self.portfolio.is_net_short(inst_id):
                    net_pos = -net_pos
                total_position += float(net_pos)
            unreal = self.portfolio.unrealized_pnl(inst_id)
            if unreal:
                total_unrealized += float(unreal)
            total_realized += float(data["realized_pnl"])
            venue = inst_id.venue
            if venue not in seen_venues:
                seen_venues.add(venue)
                account = self.portfolio.account(venue)
                if account:
                    total_balances += account.balance_total(USDT).as_double()
        total_equity = total_balances + total_unrealized
        self.general_collector.add_indicator(timestamp=ts, name="total_position", value=total_position)
        self.general_collector.add_indicator(timestamp=ts, name="total_unrealized_pnl", value=total_unrealized)
        self.general_collector.add_indicator(timestamp=ts, name="total_realized_pnl", value=total_realized)
        self.general_collector.add_indicator(timestamp=ts, name="total_equity", value=total_equity)

    def base_update_standard_indicators(self, timestamp, instrument_ctx, inst_id):
        collector = instrument_ctx["collector"]
        net_exp = self.portfolio.net_exposure(inst_id).as_double()
        #net_position = self.portfolio.net_position(inst_id)
        if self.portfolio.is_net_short(inst_id):
            net_exp = -net_exp
        #self.log.info(str(net_exp), color=LogColor.CYAN)
        unrealized_pnl = self.portfolio.unrealized_pnl(inst_id)
        realized_pnl = self.portfolio.total_pnl(inst_id)
        venue = inst_id.venue
        account = self.portfolio.account(venue)
        usdt_balance = account.balance_total(USDT)
        equity = usdt_balance.as_double() + (float(unrealized_pnl) if unrealized_pnl else 0)
        collector.add_indicator(timestamp=timestamp, name="position", value=net_exp)
        collector.add_indicator(timestamp=timestamp, name="unrealized_pnl", value=float(unrealized_pnl) if unrealized_pnl else None)
        collector.add_indicator(timestamp=timestamp, name="realized_pnl", value=float(instrument_ctx["realized_pnl"]))
        collector.add_indicator(timestamp=timestamp, name="equity", value=equity)

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
            # Robust Ermittlung des letzten Timestamps über alle vorhandenen Bar-Listen
            bars_dict = getattr(current_instrument["collector"], "bars", {}) or {}
            last_timestamp = None
            for bar_list in bars_dict.values():
                if bar_list:
                    ts = bar_list[-1].get("timestamp")
                    if ts is not None and (last_timestamp is None or ts > last_timestamp):
                        last_timestamp = ts
            if last_timestamp is not None:
                # Fallback falls keine Bars gesammelt wurden
                
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