from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from decimal import Decimal
from nautilus_trader.common.enums import LogColor
from core.visualizing.backtest_visualizer_prototype import BacktestDataCollector


class BaseStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.general_collector = BacktestDataCollector("general", config.run_id)
        self.general_collector.initialise_logging_indicator("total_position", 1)
        self.general_collector.initialise_logging_indicator("total_unrealized_pnl", 2)
        self.general_collector.initialise_logging_indicator("total_realized_pnl", 3)
        self.general_collector.initialise_logging_indicator("total_equity", 4)

    def instrument_ids(self):
        """Gibt eine Liste aller InstrumentIds zurück."""
        return list(self.instrument_dict.keys())
    
    def get_instrument_context(self, instrument_id):
        return self.instrument_dict[instrument_id]
    
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
        self.log.info(
            f"Order filled: {order_filled.commission}", color=LogColor.GREEN)

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
                    total_balances += account.balance_total().as_double()
        total_equity = total_balances + total_unrealized
        self.general_collector.add_indicator(timestamp=ts, name="total_position", value=total_position)
        self.general_collector.add_indicator(timestamp=ts, name="total_unrealized_pnl", value=total_unrealized)
        self.general_collector.add_indicator(timestamp=ts, name="total_realized_pnl", value=total_realized)
        self.general_collector.add_indicator(timestamp=ts, name="total_equity", value=total_equity)
