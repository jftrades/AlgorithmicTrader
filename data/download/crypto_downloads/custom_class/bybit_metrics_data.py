import msgspec
import pyarrow as pa
from nautilus_trader.core import Data
from nautilus_trader.model import InstrumentId
from nautilus_trader.serialization.base import register_serializable_type
from nautilus_trader.serialization.arrow.serializer import register_arrow
from nautilus_trader.core.datetime import unix_nanos_to_iso8601


class BybitMetricsData(Data):
    def __init__(
        self,
        instrument_id: InstrumentId,
        ts_event: int,
        ts_init: int,
        open_interest: float,
        funding_rate: float,
        long_short_ratio: float = 0.0,  # Long/short account ratio
    ):
        self.instrument_id = instrument_id
        self._ts_event = ts_event
        self._ts_init = ts_init
        self.open_interest = open_interest
        self.funding_rate = funding_rate
        self.long_short_ratio = long_short_ratio

    def __repr__(self):
        return (
            f"BybitMetricsData(ts={unix_nanos_to_iso8601(self._ts_event)}, "
            f"instrument={self.instrument_id}, "
            f"oi={self.open_interest:.2f}, "
            f"fr={self.funding_rate:.6f}, "
            f"lsr={self.long_short_ratio:.4f})"
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
            "open_interest": self.open_interest,
            "funding_rate": self.funding_rate,
            "long_short_ratio": self.long_short_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return BybitMetricsData(
            InstrumentId.from_str(data["instrument_id"]),
            data["ts_event"],
            data["ts_init"],
            data["open_interest"],
            data["funding_rate"],
            data.get("long_short_ratio", 0.0),
        )

    def to_bytes(self):
        return msgspec.msgpack.encode(self.to_dict())

    @classmethod
    def from_bytes(cls, data: bytes):
        return cls.from_dict(msgspec.msgpack.decode(data))

    def to_catalog(self):
        return pa.RecordBatch.from_pylist([self.to_dict()], schema=BybitMetricsData.schema())

    @classmethod
    def from_catalog(cls, table: pa.Table):
        return [BybitMetricsData.from_dict(d) for d in table.to_pylist()]

    @classmethod
    def schema(cls):
        return pa.schema(
            {
                "instrument_id": pa.string(),
                "ts_event": pa.int64(),
                "ts_init": pa.int64(),
                "open_interest": pa.float64(),
                "funding_rate": pa.float64(),
                "long_short_ratio": pa.float64(),
            }
        )


# Register with NautilusTrader serialization system
register_serializable_type(
    BybitMetricsData, 
    BybitMetricsData.to_dict, 
    BybitMetricsData.from_dict
)
register_arrow(
    BybitMetricsData, 
    BybitMetricsData.schema(), 
    BybitMetricsData.to_catalog, 
    BybitMetricsData.from_catalog
)
