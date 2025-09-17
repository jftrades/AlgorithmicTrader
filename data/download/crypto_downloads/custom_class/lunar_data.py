# lunar_data.py
import msgspec
import pyarrow as pa
from nautilus_trader.core import Data
from nautilus_trader.model import InstrumentId
from nautilus_trader.serialization.base import register_serializable_type
from nautilus_trader.serialization.arrow.serializer import register_arrow
from nautilus_trader.core.datetime import unix_nanos_to_iso8601


class LunarData(Data):
    def __init__(
        self,
        instrument_id: InstrumentId,
        ts_event: int,
        ts_init: int,
        contributors_active: float,
        contributors_created: float,
        interactions: float,
        posts_active: float,
        posts_created: float,
        sentiment: float,
        spam: float,
        alt_rank: float,
        circulating_supply: float,
        close: float,
        galaxy_score: float,
        high: float,
        low: float,
        market_cap: float,
        market_dominance: float,
        open: float,
        social_dominance: float,
        volume_24h: float,
    ):
        self.instrument_id = instrument_id
        self._ts_event = ts_event
        self._ts_init = ts_init

        # Social / Sentiment
        self.contributors_active = contributors_active
        self.contributors_created = contributors_created
        self.interactions = interactions
        self.posts_active = posts_active
        self.posts_created = posts_created
        self.sentiment = sentiment
        self.spam = spam

        # Market / Financial
        self.alt_rank = alt_rank
        self.circulating_supply = circulating_supply
        self.close = close
        self.galaxy_score = galaxy_score
        self.high = high
        self.low = low
        self.market_cap = market_cap
        self.market_dominance = market_dominance
        self.open = open  # ⚠️ jetzt konsistent mit CSV
        self.social_dominance = social_dominance
        self.volume_24h = volume_24h

    def __repr__(self):
        return (
            f"LunarData(ts={unix_nanos_to_iso8601(self._ts_event)}, "
            f"instrument_id={self.instrument_id}, "
            f"close={self.close}, vol={self.volume_24h}, "
            f"sentiment={self.sentiment}, galaxy={self.galaxy_score})"
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
            "contributors_active": self.contributors_active,
            "contributors_created": self.contributors_created,
            "interactions": self.interactions,
            "posts_active": self.posts_active,
            "posts_created": self.posts_created,
            "sentiment": self.sentiment,
            "spam": self.spam,
            "alt_rank": self.alt_rank,
            "circulating_supply": self.circulating_supply,
            "close": self.close,
            "galaxy_score": self.galaxy_score,
            "high": self.high,
            "low": self.low,
            "market_cap": self.market_cap,
            "market_dominance": self.market_dominance,
            "open": self.open,
            "social_dominance": self.social_dominance,
            "volume_24h": self.volume_24h,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return LunarData(
            InstrumentId.from_str(data["instrument_id"]),
            data["ts_event"],
            data["ts_init"],
            data["contributors_active"],
            data["contributors_created"],
            data["interactions"],
            data["posts_active"],
            data["posts_created"],
            data["sentiment"],
            data["spam"],
            data["alt_rank"],
            data["circulating_supply"],
            data["close"],
            data["galaxy_score"],
            data["high"],
            data["low"],
            data["market_cap"],
            data["market_dominance"],
            data["open"],   # ⚠️ muss vorhanden sein
            data["social_dominance"],
            data["volume_24h"],
        )

    def to_bytes(self):
        return msgspec.msgpack.encode(self.to_dict())

    @classmethod
    def from_bytes(cls, data: bytes):
        return cls.from_dict(msgspec.msgpack.decode(data))

    def to_catalog(self):
        return pa.RecordBatch.from_pylist([self.to_dict()], schema=LunarData.schema())

    @classmethod
    def from_catalog(cls, table: pa.Table):
        return [LunarData.from_dict(d) for d in table.to_pylist()]

    @classmethod
    def schema(cls):
        return pa.schema(
            {
                "instrument_id": pa.string(),
                "ts_event": pa.int64(),
                "ts_init": pa.int64(),
                "contributors_active": pa.float64(),
                "contributors_created": pa.float64(),
                "interactions": pa.float64(),
                "posts_active": pa.float64(),
                "posts_created": pa.float64(),
                "sentiment": pa.float64(),
                "spam": pa.float64(),
                "alt_rank": pa.float64(),
                "circulating_supply": pa.float64(),
                "close": pa.float64(),
                "galaxy_score": pa.float64(),
                "high": pa.float64(),
                "low": pa.float64(),
                "market_cap": pa.float64(),
                "market_dominance": pa.float64(),
                "open": pa.float64(),  # ⚠️ Schema passt jetzt zur CSV
                "social_dominance": pa.float64(),
                "volume_24h": pa.float64(),
            }
        )


register_serializable_type(LunarData, LunarData.to_dict, LunarData.from_dict)
register_arrow(LunarData, LunarData.schema(), LunarData.to_catalog, LunarData.from_catalog)
