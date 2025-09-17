# metrics_data.py
import msgspec
import pyarrow as pa
from nautilus_trader.core import Data
from nautilus_trader.model import InstrumentId
from nautilus_trader.serialization.base import register_serializable_type
from nautilus_trader.serialization.arrow.serializer import register_arrow
from nautilus_trader.core.datetime import unix_nanos_to_iso8601


class MetricsData(Data):
    def __init__(
        self,
        instrument_id: InstrumentId,
        ts_event: int,
        ts_init: int,
        sum_open_interest: float,
        sum_open_interest_value: float,
        count_toptrader_long_short_ratio: float,
        sum_toptrader_long_short_ratio: float,
        count_long_short_ratio: float,
        sum_taker_long_short_vol_ratio: float,
    ):
        self.instrument_id = instrument_id
        self._ts_event = ts_event
        self._ts_init = ts_init
        self.sum_open_interest = sum_open_interest
        self.sum_open_interest_value = sum_open_interest_value
        self.count_toptrader_long_short_ratio = count_toptrader_long_short_ratio
        self.sum_toptrader_long_short_ratio = sum_toptrader_long_short_ratio
        self.count_long_short_ratio = count_long_short_ratio
        self.sum_taker_long_short_vol_ratio = sum_taker_long_short_vol_ratio

    def __repr__(self):
        return (
            f"MetricsData(ts={unix_nanos_to_iso8601(self._ts_event)}, "
            f"instrument_id={self.instrument_id}, "
            f"oi={self.sum_open_interest}, "
            f"oi_val={self.sum_open_interest_value}, "
            f"ctr={self.count_toptrader_long_short_ratio}, "
            f"str={self.sum_toptrader_long_short_ratio}, "
            f"clr={self.count_long_short_ratio}, "
            f"tvr={self.sum_taker_long_short_vol_ratio})"
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
            "sum_open_interest": self.sum_open_interest,
            "sum_open_interest_value": self.sum_open_interest_value,
            "count_toptrader_long_short_ratio": self.count_toptrader_long_short_ratio,
            "sum_toptrader_long_short_ratio": self.sum_toptrader_long_short_ratio,
            "count_long_short_ratio": self.count_long_short_ratio,
            "sum_taker_long_short_vol_ratio": self.sum_taker_long_short_vol_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return MetricsData(
            InstrumentId.from_str(data["instrument_id"]),
            data["ts_event"],
            data["ts_init"],
            data["sum_open_interest"],
            data["sum_open_interest_value"],
            data["count_toptrader_long_short_ratio"],
            data["sum_toptrader_long_short_ratio"],
            data["count_long_short_ratio"],
            data["sum_taker_long_short_vol_ratio"],
        )

    def to_bytes(self):
        return msgspec.msgpack.encode(self.to_dict())

    @classmethod
    def from_bytes(cls, data: bytes):
        return cls.from_dict(msgspec.msgpack.decode(data))

    def to_catalog(self):
        return pa.RecordBatch.from_pylist([self.to_dict()], schema=MetricsData.schema())

    @classmethod
    def from_catalog(cls, table: pa.Table):
        return [MetricsData.from_dict(d) for d in table.to_pylist()]

    @classmethod
    def schema(cls):
        return pa.schema(
            {
                "instrument_id": pa.string(),
                "ts_event": pa.int64(),
                "ts_init": pa.int64(),
                "sum_open_interest": pa.float64(),
                "sum_open_interest_value": pa.float64(),
                "count_toptrader_long_short_ratio": pa.float64(),
                "sum_toptrader_long_short_ratio": pa.float64(),
                "count_long_short_ratio": pa.float64(),
                "sum_taker_long_short_vol_ratio": pa.float64(),
            }
        )

register_serializable_type(MetricsData, MetricsData.to_dict, MetricsData.from_dict)
register_arrow(MetricsData, MetricsData.schema(), MetricsData.to_catalog, MetricsData.from_catalog)