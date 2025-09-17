import msgspec
import pyarrow as pa
from nautilus_trader.core import Data
from nautilus_trader.model import InstrumentId
from nautilus_trader.serialization.base import register_serializable_type
from nautilus_trader.serialization.arrow.serializer import register_arrow
from nautilus_trader.core.datetime import unix_nanos_to_iso8601


class AggTradeData(Data):
    def __init__(
        self,
        instrument_id: InstrumentId,
        ts_event: int,
        ts_init: int,
        agg_trade_id: int,
        price: float,
        quantity: float,
        first_trade_id: int,
        last_trade_id: int,
        is_buyer_maker: bool,
    ):
        self.instrument_id = instrument_id
        self._ts_event = ts_event
        self._ts_init = ts_init
        self.agg_trade_id = agg_trade_id
        self.price = price
        self.quantity = quantity
        self.first_trade_id = first_trade_id
        self.last_trade_id = last_trade_id
        self.is_buyer_maker = is_buyer_maker

    def __repr__(self):
        return (
            f"AggTradeData(ts={unix_nanos_to_iso8601(self._ts_event)}, "
            f"instrument_id={self.instrument_id}, "
            f"id={self.agg_trade_id}, "
            f"price={self.price}, qty={self.quantity}, "
            f"buyer_maker={self.is_buyer_maker})"
        )

    @property
    def ts_event(self) -> int:
        return self._ts_event

    @property
    def ts_init(self) -> int:
        return self._ts_init

    def to_dict(self):
        return {
            "instrument_id": self.instrument_id.value,
            "ts_event": self._ts_event,
            "ts_init": self._ts_init,
            "agg_trade_id": self.agg_trade_id,
            "price": self.price,
            "quantity": self.quantity,
            "first_trade_id": self.first_trade_id,
            "last_trade_id": self.last_trade_id,
            "is_buyer_maker": self.is_buyer_maker,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return AggTradeData(
            InstrumentId.from_str(data["instrument_id"]),
            data["ts_event"],
            data["ts_init"],
            data["agg_trade_id"],
            data["price"],
            data["quantity"],
            data["first_trade_id"],
            data["last_trade_id"],
            data["is_buyer_maker"],
        )

    def to_bytes(self):
        return msgspec.msgpack.encode(self.to_dict())

    @classmethod
    def from_bytes(cls, data: bytes):
        return cls.from_dict(msgspec.msgpack.decode(data))

    def to_catalog(self):
        return pa.RecordBatch.from_pylist([self.to_dict()], schema=AggTradeData.schema())

    @classmethod
    def from_catalog(cls, table: pa.Table):
        return [AggTradeData.from_dict(d) for d in table.to_pylist()]

    @classmethod
    def schema(cls):
        return pa.schema(
            {
                "instrument_id": pa.string(),
                "ts_event": pa.int64(),
                "ts_init": pa.int64(),
                "agg_trade_id": pa.int64(),
                "price": pa.float64(),
                "quantity": pa.float64(),
                "first_trade_id": pa.int64(),
                "last_trade_id": pa.int64(),
                "is_buyer_maker": pa.bool_(),
            }
        )


# Registrierung
register_serializable_type(AggTradeData, AggTradeData.to_dict, AggTradeData.from_dict)
register_arrow(AggTradeData, AggTradeData.schema(), AggTradeData.to_catalog, AggTradeData.from_catalog)
