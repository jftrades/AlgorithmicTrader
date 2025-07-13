from nautilus_trader.trading import Strategy
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from decimal import Decimal
from nautilus_trader.common.enums import LogColor


class BaseStrategy(Strategy):
    def base__init__(self, config: StrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.close_positions_on_stop = config.close_positions_on_stop
        self.venue = self.instrument_id.venue
        self.risk_manager = None

    def base_get_position(self):
        if hasattr(self, "cache") and self.cache is not None:
            positions = self.cache.positions_open(instrument_id=self.instrument_id)
            if positions:
                return positions[0]
        return None

    def base_close_position(self) -> None:
        position = self.get_position()
        if position is not None and position.is_open:
            super().close_position(position)
        
    def base_on_stop(self) -> None:
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.log.info("Strategy stopped!")

        logging_message = self.collector.save_data()
        self.log.info(logging_message, color=LogColor.GREEN)

    def base_on_order_filled(self, order_filled) -> None:
        self.collector.add_trade_details(order_filled)
        self.log.info(
            f"Order filled: {order_filled.commission}", color=LogColor.GREEN)

    def base_on_position_closed(self, position_closed) -> None:
        realized_pnl = position_closed.realized_pnl  # Realized PnL
        self.realized_pnl += float(realized_pnl) if realized_pnl else 0
        self.collector.add_closed_trade(position_closed)

    def base_on_error(self, error: Exception) -> None:
        self.log.error(f"An error occurred: {error}")
        position = self.get_position()
        if self.close_positions_on_stop and position is not None and position.is_open:
            self.close_position()
        self.stop()