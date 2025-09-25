import msgspec
import pyarrow as pa
from nautilus_trader.core import Data
from nautilus_trader.model import InstrumentId
from nautilus_trader.serialization.base import register_serializable_type
from nautilus_trader.serialization.arrow.serializer import register_arrow
from nautilus_trader.core.datetime import unix_nanos_to_iso8601


class FearAndGreedData(Data):
    """
    Daily Crypto Fear & Greed Index snapshot.
    Use a synthetic InstrumentId, e.g. InstrumentId.from_str("FNG-INDEX.BINANCE").
    """
    def __init__(
        self,
        instrument_id: InstrumentId,
        ts_event: int,          # nanoseconds UTC (day boundary or source time)
        ts_init: int,           # usually same as ts_event
        fear_greed: int,        # 0..100
        classification: str,    # Extreme Fear | Fear | Neutral | Greed | Extreme Greed
    ):
        self.instrument_id = instrument_id
        self._ts_event = ts_event
        self._ts_init = ts_init
        self.fear_greed = int(fear_greed)
        self.classification = classification

    def __repr__(self):
        return (
            f"FearAndGreedData(ts={unix_nanos_to_iso8601(self._ts_event)}, "
            f"instrument_id={self.instrument_id}, "
            f"fear_greed={self.fear_greed}, class={self.classification})"
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
            "fear_greed": self.fear_greed,
            "classification": self.classification,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return FearAndGreedData(
            InstrumentId.from_str(data["instrument_id"]),
            data["ts_event"],
            data["ts_init"],
            data["fear_greed"],
            data["classification"],
        )

    def to_bytes(self):
        return msgspec.msgpack.encode(self.to_dict())

    @classmethod
    def from_bytes(cls, b: bytes):
        return cls.from_dict(msgspec.msgpack.decode(b))

    def to_catalog(self):
        return pa.RecordBatch.from_pylist([self.to_dict()], schema=FearAndGreedData.schema())

    @classmethod
    def from_catalog(cls, table: pa.Table):
        return [FearAndGreedData.from_dict(d) for d in table.to_pylist()]

    @classmethod
    def schema(cls):
        return pa.schema(
            {
                "instrument_id": pa.string(),
                "ts_event": pa.int64(),
                "ts_init": pa.int64(),
                "fear_greed": pa.int32(),
                "classification": pa.string(),
            }
        )


register_serializable_type(FearAndGreedData, FearAndGreedData.to_dict, FearAndGreedData.from_dict)
register_arrow(FearAndGreedData, FearAndGreedData.schema(), FearAndGreedData.to_catalog, FearAndGreedData.from_catalog)
