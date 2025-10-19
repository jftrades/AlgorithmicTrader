import datetime as dt
from datetime import datetime
from pathlib import Path
import pandas as pd
import shutil
import requests
import gzip
import sys
from decimal import Decimal
import time
from typing import Optional, Dict, Any

from nautilus_trader.core.nautilus_pyo3 import (
    Bar,
    BarSpecification,
    BarType,
    BarAggregation,
    PriceType,
    AggregationSource,
    InstrumentId,
    Symbol,
    Venue,
    Price,
    Quantity,
)
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.persistence.catalog import ParquetDataCatalog
import glob
import os


# ============================================================================
# CONFIGURATION PARAMETERS
# ============================================================================

symbol = "BTCUSDT-LINEAR"
start_date = "2022-01-01"
end_date = "2025-10-18"
base_data_dir = str(Path(__file__).resolve().parents[3] / "DATA_STORAGE")
datatype = "bar"
interval = "15m"
save_as_csv = True
save_in_catalog = True


# ============================================================================
# BYBIT API CONSTANTS
# ============================================================================

BYBIT_API_BASE = "https://api.bybit.com/v5/market"
BYBIT_BULK_BASE = "https://public.bybit.com/trading"

BYBIT_INTERVAL_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}

BYBIT_RATE_LIMIT_DELAY = 0.02

BYBIT_ENDPOINTS = {
    "kline": f"{BYBIT_API_BASE}/kline",
    "trades": f"{BYBIT_API_BASE}/recent-trade",
    "instruments": f"{BYBIT_API_BASE}/instruments-info",
    "open_interest": f"{BYBIT_API_BASE}/open-interest",
    "funding": f"{BYBIT_API_BASE}/funding/history",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def normalize_symbol_for_bybit(symbol: str) -> str:
    return symbol.replace("-LINEAR", "")


def format_symbol_for_nautilus_bybit(symbol: str) -> str:
    if not symbol.endswith("-LINEAR"):
        return f"{symbol}-LINEAR"
    return symbol


def convert_interval_to_bybit(interval: str) -> str:
    interval_lower = interval.lower().strip()
    if interval_lower not in BYBIT_INTERVAL_MAP:
        raise ValueError(f"Unsupported interval: {interval}. Supported: {list(BYBIT_INTERVAL_MAP.keys())}")
    return BYBIT_INTERVAL_MAP[interval_lower]


def bybit_timestamp_to_ms(timestamp: int) -> int:
    if timestamp > 99999999999999:
        raise ValueError(f"Timestamp looks invalid: {timestamp}")
    return timestamp


def ms_to_bybit_timestamp(ms: int) -> int:
    return ms


def make_bybit_api_request(
    url: str,
    params: dict,
    max_retries: int = 3,
    delay: float = BYBIT_RATE_LIMIT_DELAY
) -> dict:
    time.sleep(delay)
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("retCode") != 0:
                error_msg = data.get("retMsg", "Unknown error")
                raise ValueError(f"Bybit API error: {error_msg}")
                
            return data
            
        except (requests.exceptions.RequestException, ValueError) as e:
            if attempt == max_retries - 1:
                raise
            print(f"[WARN] Request failed (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(delay * (2 ** attempt))
    
    raise RuntimeError("Should never reach here")


def find_csv_file(symbol: str, processed_dir: str) -> str:
    pattern = os.path.join(processed_dir, f"{symbol}*.csv")
    csv_files = glob.glob(pattern)
    if len(csv_files) == 0:
        raise FileNotFoundError(f"No CSV for pattern {pattern}")
    return csv_files[0]


# ============================================================================
# MAIN DOWNLOADER CLASS
# ============================================================================

class CombinedCryptoDataDownloader:
    def __init__(
        self,
        symbol,
        start_date,
        end_date,
        base_data_dir,
        datatype="tick",
        interval="1h",
        csv_output_subdir: str | None = None,
    ):
        self.is_linear = symbol.endswith("-LINEAR")
        self.symbol_for_bybit = normalize_symbol_for_bybit(symbol)
        self.symbol_for_nt = format_symbol_for_nautilus_bybit(symbol)
        self.symbol = symbol
        
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if isinstance(start_date, str) else start_date
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if isinstance(end_date, str) else end_date
        self.base_data_dir = base_data_dir
        self.datatype = datatype
        self.interval = interval
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.csv_output_subdir = csv_output_subdir

    def run(self):
        if self.datatype == "tick":
            print("Mode: tick")
            tick_downloader = TickDownloader(
                symbol=self.symbol_for_bybit,
                start_date=self.start_date,
                end_date=self.end_date,
                base_data_dir=self.base_data_dir
            )
            tick_downloader.run()
            
            processed_dir = str(Path(self.base_data_dir) / "cache" / f"processed_tick_data_{self.start_date}_to_{self.end_date}" / "csv")
            csv_path = find_csv_file(self.symbol_for_bybit, processed_dir)
            catalog_root_path = f"{self.base_data_dir}/data_catalog_wrangled"
            
            tick_transformer = TickTransformer(
                csv_path=csv_path,
                catalog_root_path=catalog_root_path,
                symbol=self.symbol_for_bybit,
                is_linear=self.is_linear,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                base_data_dir=self.base_data_dir,
                csv_output_subdir=self.csv_output_subdir,
            )
            tick_transformer.run()
            
            try:
                shutil.rmtree(Path(self.base_data_dir) / "cache" / f"processed_tick_data_{self.start_date}_to_{self.end_date}")
                print(f"[INFO] Tick-Ordner gelöscht: {Path(self.base_data_dir) / 'cache' / f'processed_tick_data_{self.start_date}_to_{self.end_date}'}")
            except Exception:
                print(f"[WARN] Tick-Ordner konnte nicht gelöscht werden")
            print("Tick pipeline completed.")
            
        elif self.datatype == "bar":
            print("Mode: bar")
            bar_downloader = BarDownloader(
                symbol=self.symbol_for_bybit,
                interval=self.interval,
                start_date=self.start_date,
                end_date=self.end_date,
                base_data_dir=self.base_data_dir
            )
            bar_downloader.run()
            
            # Fix: Verwende das gleiche Format wie BarDownloader
            start_str = self.start_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.start_date, "strftime") else f"{self.start_date}_000000"
            end_str = self.end_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.end_date, "strftime") else f"{self.end_date}_000000"
            processed_dir = str(Path(self.base_data_dir) / "cache" / f"processed_bar_data_{start_str}_to_{end_str}" / "csv")
            
            csv_path = find_csv_file(self.symbol_for_bybit, processed_dir)
            catalog_root_path = f"{self.base_data_dir}/data_catalog_wrangled"

            # NautilusTrader BarType and InstrumentId for BYBIT
            from nautilus_trader.core.nautilus_pyo3 import (
                BarSpecification, BarType, BarAggregation, PriceType, AggregationSource, InstrumentId, Symbol, Venue
            )
            
            # Parse interval
            raw = str(self.interval).lower().strip()
            if raw.endswith("h"):
                step = int(float(raw[:-1]))
                interval_token_for_wrangler = f"{step}-HOUR"
                aggregation = BarAggregation.HOUR
            elif raw.endswith("d"):
                step = int(float(raw[:-1]))
                interval_token_for_wrangler = f"{step}-DAY"
                aggregation = BarAggregation.DAY
            elif raw.endswith("m"):
                step = int(float(raw[:-1]))
                interval_token_for_wrangler = f"{step}-MINUTE"
                aggregation = BarAggregation.MINUTE
            elif raw.isdigit():
                step = int(raw)
                interval_token_for_wrangler = f"{step}-MINUTE"
                aggregation = BarAggregation.MINUTE
            else:
                raise ValueError(f"Unbekanntes Interval-Format: {self.interval}")

            # Use -LINEAR suffix for Bybit perpetual futures
            if self.is_linear:
                wrangler_init_bar_type_string = f"{self.symbol_for_bybit}-LINEAR.BYBIT-{interval_token_for_wrangler}-LAST-EXTERNAL"
                target_instrument_id = InstrumentId(Symbol(f"{self.symbol_for_bybit}-LINEAR"), Venue("BYBIT"))
            else:
                # Spot trading (not typically used on Bybit linear contracts, but supported)
                wrangler_init_bar_type_string = f"{self.symbol_for_bybit}.BYBIT-{interval_token_for_wrangler}-LAST-EXTERNAL"
                target_instrument_id = InstrumentId(Symbol(self.symbol_for_bybit), Venue("BYBIT"))

            target_bar_spec = BarSpecification(
                step=step,
                aggregation=aggregation,
                price_type=PriceType.LAST
            )
            target_bar_type_obj = BarType(
                instrument_id=target_instrument_id,
                spec=target_bar_spec,
                aggregation_source=AggregationSource.EXTERNAL
            )

            output_columns = [
                "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
            ]
            bar_transformer = BarTransformer(
                csv_path=csv_path,
                catalog_root_path=catalog_root_path,
                wrangler_init_bar_type_string=wrangler_init_bar_type_string,
                target_bar_type_obj=target_bar_type_obj,
                output_columns=output_columns,
                symbol=self.symbol_for_bybit,
                is_linear=self.is_linear,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                base_data_dir=self.base_data_dir,
                csv_output_subdir=self.csv_output_subdir,
            )
            bar_transformer.run()
            
            try:
                shutil.rmtree(Path(self.base_data_dir) / "cache" / f"processed_bar_data_{start_str}_to_{end_str}")
                print(f"[INFO] Bar-Ordner gelöscht: {Path(self.base_data_dir) / 'cache' / f'processed_bar_data_{start_str}_to_{end_str}'}")
            except Exception:
                print(f"[WARN] Bar-Ordner konnte nicht gelöscht werden")
            print("Bar pipeline completed.")
        else:
            raise ValueError(f"Unknown datatype: {self.datatype}")
        

# ============================================================================
# TICK DOWNLOADER
# ============================================================================

class TickDownloader:
    def __init__(self, symbol, start_date, end_date, base_data_dir):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.base_data_dir = Path(base_data_dir)
        self.cache_root = self.base_data_dir / "cache"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = self.cache_root / "temp_tick_downloads"
        self.processed_dir = self.cache_root / f"processed_tick_data_{start_date}_to_{end_date}" / "csv"

    def run(self):
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = self.processed_dir / f"{self.symbol}_TICKS_{self.start_date:%Y-%m-%d}_to_{self.end_date:%Y-%m-%d}.csv"
        if output_file.exists():
            output_file.unlink()
        
        columns = ['trade_id', 'price', 'quantity', 'base_quantity', 'timestamp', 'is_buyer_maker']
        
        total_days = (self.end_date - self.start_date).days + 1
        print(f"Tick download started: {self.symbol} ({total_days} days)")
        
        for n in range(total_days):
            date = self.start_date + dt.timedelta(days=n)
            
            filename = f"{self.symbol}{date:%Y-%m-%d}.csv.gz"
            url = f"{BYBIT_BULK_BASE}/{self.symbol}/{filename}"
            gz_path = self.temp_dir / filename
            
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                print(f"[WARN] No data for {date:%Y-%m-%d} (HTTP {r.status_code})")
                continue
            
            with open(gz_path, "wb") as f:
                f.write(r.content)
            
            csv_file = self.temp_dir / f"{self.symbol}{date:%Y-%m-%d}.csv"
            with gzip.open(gz_path, "rb") as f_in:
                with open(csv_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            try:
                df = pd.read_csv(csv_file, names=columns, low_memory=False)
                df['price'] = pd.to_numeric(df['price'], errors='coerce')
                df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['price', 'quantity', 'timestamp'])
                df = df[(df['price'] > 0) & (df['quantity'] > 0) & (df['timestamp'] > 0)]
                df['timestamp'] = df['timestamp'].astype('int64')
                df['buyer_maker'] = df['is_buyer_maker'].astype(str).str.lower() == 'true'
                
                df = df.sort_values(by='timestamp', ascending=True)
                
                chunk = df[['timestamp', 'trade_id', 'price', 'quantity', 'buyer_maker']]
                mode = 'w' if n == 0 else 'a'
                header = n == 0
                chunk.to_csv(output_file, mode=mode, header=header, index=False)
                
            except Exception as e:
                print(f"[ERROR] Failed to process {csv_file}: {e}")
            
            csv_file.unlink(missing_ok=True)
            gz_path.unlink(missing_ok=True)
        
        for f in self.temp_dir.glob("*"):
            f.unlink(missing_ok=True)
        self.temp_dir.rmdir()
        
        print(f"Tick data written: {output_file}")


# ============================================================================
# TICK TRANSFORMER
# ============================================================================

class TickTransformer:
    def __init__(
        self,
        csv_path,
        catalog_root_path,
        symbol=None,
        is_linear=False,  # Changed from is_perp for Bybit
        save_as_csv=False,
        save_in_catalog=True,
        base_data_dir=None,
        csv_output_subdir: str | None = None,
    ):
        self.csv_path = Path(csv_path)
        self.catalog_root_path = Path(catalog_root_path)
        self.symbol = symbol
        self.is_linear = is_linear
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.base_data_dir = Path(base_data_dir) if base_data_dir else self.catalog_root_path
        self.csv_output_subdir = csv_output_subdir

    def run(self):
        if self.save_in_catalog:
            self.catalog_root_path.mkdir(parents=True, exist_ok=True)
            catalog = ParquetDataCatalog(path=self.catalog_root_path)
            instrument = TestInstrumentProvider.btcusdt_perp_binance()
            catalog.write_data([instrument])
            wrangler = TradeTickDataWrangler(instrument=instrument)
        else:
            catalog = None
            wrangler = None

        chunk_iter = pd.read_csv(self.csv_path, chunksize=5_000_000)
        csv_out_path = None
        first_chunk = True

        for i, chunk_df in enumerate(chunk_iter):
            if self.save_as_csv:
                if csv_out_path is None:
                    subdir = self.csv_output_subdir or os.getenv("CSV_OUTPUT_SUBDIR") or "csv_data"
                    sym_dir = self.base_data_dir / subdir / (self.symbol + ("-LINEAR" if self.is_linear else ""))
                    sym_dir.mkdir(parents=True, exist_ok=True)
                    csv_out_path = sym_dir / "TICK.csv"

                ts_raw = chunk_df["timestamp"]
                if pd.api.types.is_integer_dtype(ts_raw) or pd.api.types.is_float_dtype(ts_raw):
                    ts = pd.to_datetime(ts_raw.astype('int64'), unit='ms', utc=True)
                else:
                    ts = pd.to_datetime(ts_raw, utc=True, errors='coerce', format='ISO8601')
                    mask_na = ts.isna()
                    if mask_na.any():
                        ts_alt = pd.to_datetime(ts_raw[mask_na], utc=True, errors='coerce')
                        ts[mask_na] = ts_alt

                ts_nano = ts.astype('int64')

                rows = pd.DataFrame({
                    "timestamp_nano": ts_nano,
                    "timestamp_iso": ts.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "symbol": self.symbol + ("-LINEAR" if self.is_linear else ""),
                    "price": pd.to_numeric(chunk_df["price"], errors="coerce"),
                    "quantity": pd.to_numeric(chunk_df["quantity"], errors="coerce"),
                    "buyer_maker": chunk_df["buyer_maker"].astype(str),
                    "trade_id": chunk_df["trade_id"],
                }).dropna(subset=["price", "quantity", "timestamp_nano"])

                rows.to_csv(
                    csv_out_path,
                    mode="w" if first_chunk else "a",
                    header=first_chunk,
                    index=False
                )

            if self.save_in_catalog:
                tmp_csv = self.catalog_root_path / f"tmp_tick_chunk_{i}.csv"
                chunk_df.to_csv(tmp_csv, index=False)
                data = CSVTickDataLoader.load(file_path=tmp_csv)
                ticks = wrangler.process(data)
                catalog.write_data(ticks, skip_disjoint_check=True)
                tmp_csv.unlink()

            first_chunk = False


# ============================================================================
# BAR DOWNLOADER
# ============================================================================

class BarDownloader:
    def __init__(self, symbol, interval, start_date, end_date, base_data_dir):
        self.symbol = symbol
        self.interval = interval
        self.bybit_interval = convert_interval_to_bybit(interval)
        self.start_date = start_date
        self.end_date = end_date
        self.base_data_dir = base_data_dir
        self.cache_root = Path(base_data_dir) / "cache"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        
        start_str = self.start_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.start_date, "strftime") else str(self.start_date).replace(":", "").replace(" ", "_")
        end_str = self.end_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.end_date, "strftime") else str(self.end_date).replace(":", "").replace(" ", "_")
        self.processed_dir = self.cache_root / f"processed_bar_data_{start_str}_to_{end_str}" / "csv"

    def run(self):
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        print(f"Bar download started: {self.symbol} ({self.interval})")
        
        start_ms = int(pd.Timestamp(self.start_date).tz_localize("UTC").timestamp() * 1000)
        end_ms = int((pd.Timestamp(self.end_date) + pd.Timedelta(days=1)).tz_localize("UTC").timestamp() * 1000) - 1
        
        # Bybit API limit: chunk into large windows for efficiency
        chunk_days = 1800  # ~5 years per chunk (increased from 180)
        chunk_ms = chunk_days * 24 * 60 * 60 * 1000
        
        all_bars = []
        current_start = start_ms
        chunk_num = 0
        
        while current_start < end_ms:
            chunk_num += 1
            current_end = min(current_start + chunk_ms, end_ms)
            
            print(f"[INFO] Downloading chunk {chunk_num}: {pd.Timestamp(current_start, unit='ms')} to {pd.Timestamp(current_end, unit='ms')}")
            
            params = {
                "category": "linear",
                "symbol": self.symbol,
                "interval": self.bybit_interval,
                "start": current_start,
                "end": current_end,
                "limit": 1000,
            }
            
            cursor = None
            page = 0
            
            while True:
                page += 1
                if cursor:
                    params["cursor"] = cursor
                
                try:
                    data = make_bybit_api_request(BYBIT_ENDPOINTS["kline"], params)
                except Exception as e:
                    print(f"[ERROR] API request failed: {e}")
                    break
                
                result = data.get("result", {})
                bars = result.get("list", [])
                
                if not bars:
                    print(f"[INFO] No more data (chunk {chunk_num}, page {page})")
                    break
                
                all_bars.extend(bars)
                print(f"[INFO] Downloaded {len(bars)} bars (chunk {chunk_num}, page {page}, total: {len(all_bars)})")
                
                cursor = result.get("nextPageCursor")
                if not cursor:
                    break
            
            current_start = current_end + 1
        
        if not all_bars:
            print("[WARN] No bars downloaded")
            return
        
        EXPECTED_COLUMNS = ["open_time_ms", "open", "high", "low", "close", "volume", "turnover"]
        
        df = pd.DataFrame(all_bars, columns=EXPECTED_COLUMNS)
        
        df["open_time_ms"] = pd.to_numeric(df["open_time_ms"], errors="coerce").astype("int64")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        df = df.sort_values(by="open_time_ms", ascending=True)
        
        df = df[(df["open_time_ms"] >= start_ms) & (df["open_time_ms"] <= end_ms)]
        print(f"[INFO] After filter: {len(df)} bars in range {self.start_date} .. {self.end_date}")
        
        df.drop_duplicates(subset=["open_time_ms"], inplace=True)
        df["timestamp"] = df["open_time_ms"]
        df["number_of_trades"] = 0
        
        OUTPUT_COLUMNS = ["timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"]
        df_final = df[OUTPUT_COLUMNS].dropna()
        
        start_str = self.start_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.start_date, "strftime") else str(self.start_date).replace(":", "").replace(" ", "_")
        end_str = self.end_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.end_date, "strftime") else str(self.end_date).replace(":", "").replace(" ", "_")
        output_path = self.processed_dir / f"{self.symbol}_{self.interval}_{start_str}_to_{end_str}.csv"
        df_final.to_csv(output_path, index=False, header=False)
        print(f"Bar source CSV written: {output_path}")


# ============================================================================
# BAR TRANSFORMER
# ============================================================================

class BarTransformer:
    def __init__(
        self,
        csv_path,
        catalog_root_path,
        wrangler_init_bar_type_string,
        target_bar_type_obj,
        output_columns=None,
        symbol=None,
        is_linear=False,  # Changed from is_perp for Bybit
        save_as_csv=False,
        save_in_catalog=True,
        base_data_dir=None,
        csv_output_subdir: str | None = None,
    ):
        self.csv_path = Path(csv_path)
        self.catalog_root_path = Path(catalog_root_path)
        self.wrangler_init_bar_type_string = wrangler_init_bar_type_string
        self.target_bar_type_obj = target_bar_type_obj
        self.output_columns = output_columns or [
            "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
        ]
        self.symbol = symbol
        self.is_linear = is_linear
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.base_data_dir = Path(base_data_dir) if base_data_dir else Path(catalog_root_path)
        self.csv_output_subdir = csv_output_subdir

    def run(self):
        print("Bar transform started.")
        df = pd.read_csv(self.csv_path, header=None, names=self.output_columns)
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("int64")
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors='coerce')
        
        int32_max = 2_147_483_647
        num_clamped = (df["volume"] > int32_max).sum()
        df.loc[df["volume"] > int32_max, "volume"] = int32_max
        if num_clamped > 0:
            print(f"Volumes clamped: {num_clamped}")
        
        df.dropna(inplace=True)
        df = df[(df["volume"] > 0) & (df["high"] != df["low"])]
        print(f"Bars after filter: {len(df)}")
        
        instrument_for_meta = get_instrument(self.symbol, self.is_linear)
        price_precision = instrument_for_meta.price_precision
        size_precision = instrument_for_meta.size_precision
        
        wrangler = BarDataWranglerV2(
            bar_type=self.wrangler_init_bar_type_string,
            price_precision=price_precision,
            size_precision=size_precision,
        )
        initial_bars_from_wrangler = wrangler.from_pandas(df)
        
        final_bars = []
        if initial_bars_from_wrangler and isinstance(initial_bars_from_wrangler[0], Bar):
            for b_in in initial_bars_from_wrangler:
                final_bars.append(Bar(
                    bar_type=self.target_bar_type_obj,
                    open=b_in.open,
                    high=b_in.high,
                    low=b_in.low,
                    close=b_in.close,
                    volume=Quantity(b_in.volume.as_double(), size_precision),
                    ts_event=b_in.ts_event * 1_000_000,
                    ts_init=b_in.ts_init * 1_000_000,
                ))
        else:
            print("No bars produced.")
            return
        
        if self.save_as_csv:
            df_out = pd.DataFrame(
                (
                    (
                        b.ts_event,
                        unix_nanos_to_dt(b.ts_event).isoformat(),
                        self.symbol + ("-LINEAR" if self.is_linear else ""),
                        b.open.as_double(),
                        b.high.as_double(),
                        b.low.as_double(),
                        b.close.as_double(),
                        b.volume.as_double(),
                    )
                    for b in final_bars
                ),
                columns=[
                    "timestamp_nano", "timestamp_iso", "symbol",
                    "open", "high", "low", "close", "volume",
                ],
            )
            
            subdir = self.csv_output_subdir or os.getenv("CSV_OUTPUT_SUBDIR") or "csv_data"
            csv_dir = self.base_data_dir / subdir / (self.symbol + ("-LINEAR" if self.is_linear else ""))
            csv_dir.mkdir(parents=True, exist_ok=True)
            out_file = csv_dir / "OHLCV.csv"
            df_out.to_csv(out_file, index=False)
            print(f"Bars CSV exported: {out_file}")
        
        if self.save_in_catalog:
            bar_type_dir = (
                self.catalog_root_path / "data" /
                ("crypto_perpetual" if self.is_linear else "crypto_spot") /
                self.wrangler_init_bar_type_string
            )
            if bar_type_dir.exists():
                shutil.rmtree(bar_type_dir)
            
            catalog = ParquetDataCatalog(path=self.catalog_root_path)
            catalog.write_data([instrument_for_meta])
            catalog.write_data(final_bars)
            print(f"Bars saved to catalog: {len(final_bars)}")
        
        if final_bars:
            ts_min = unix_nanos_to_dt(min(b.ts_event for b in final_bars))
            ts_max = unix_nanos_to_dt(max(b.ts_event for b in final_bars))
            print(f"Bars range: {ts_min} - {ts_max}")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _fetch_single_symbol_info_bybit(symbol: str, is_linear: bool) -> dict:
    params = {
        "category": "linear" if is_linear else "spot",
        "symbol": symbol,
    }
    
    try:
        data = make_bybit_api_request(BYBIT_ENDPOINTS["instruments"], params)
    except Exception as e:
        raise ValueError(f"Failed to fetch instrument info for {symbol}: {e}")
    
    result = data.get("result", {})
    instruments = result.get("list", [])
    
    if not instruments:
        raise ValueError(f"Bybit instruments-info: Symbol '{symbol}' nicht gefunden (is_linear={is_linear})")
    
    return instruments[0]


def get_instrument(symbol: str, is_linear: bool):
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.test_kit.providers import TestInstrumentProvider
    from nautilus_trader.model.objects import Price, Quantity

    info = _fetch_single_symbol_info_bybit(symbol, is_linear)
    
    price_filter = info.get("priceFilter", {})
    lot_size_filter = info.get("lotSizeFilter", {})
    
    tick_size_str = price_filter.get("tickSize", "0.01")
    min_order_qty_str = lot_size_filter.get("minOrderQty", "0.001")
    
    base_precision_str = lot_size_filter.get("basePrecision", "8")
    quote_precision_str = lot_size_filter.get("quotePrecision", "8")
    
    tick_size = Decimal(tick_size_str)
    calculated_price_precision = abs(tick_size.as_tuple().exponent)
    
    step_size = Decimal(min_order_qty_str)
    calculated_size_precision = abs(step_size.as_tuple().exponent)
    
    use_price_precision = calculated_price_precision
    use_size_precision = calculated_size_precision
    
    if is_linear:
        margin_init = Decimal("0.01")
        margin_maint = Decimal("0.005")
    else:
        margin_init = Decimal("0")
        margin_maint = Decimal("0")
    
    template = TestInstrumentProvider.btcusdt_perp_binance() if is_linear else TestInstrumentProvider.btcusdt_binance()
    
    if is_linear:
        inst_id = InstrumentId(Symbol(f"{symbol}-LINEAR"), Venue("BYBIT"))
    else:
        inst_id = InstrumentId(Symbol(symbol), Venue("BYBIT"))
    
    instrument = template.__class__(
        instrument_id=inst_id,
        raw_symbol=Symbol(symbol),
        base_currency=template.base_currency,
        quote_currency=template.quote_currency,
        settlement_currency=template.settlement_currency,
        is_inverse=template.is_inverse,
        price_precision=use_price_precision,
        size_precision=use_size_precision,
        price_increment=Price.from_str(tick_size_str),
        size_increment=Quantity.from_str(min_order_qty_str),
        margin_init=margin_init,
        margin_maint=margin_maint,
        maker_fee=template.maker_fee,
        taker_fee=template.taker_fee,
        ts_event=template.ts_event,
        ts_init=template.ts_init,
    )
    
    return instrument


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    downloader = CombinedCryptoDataDownloader(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_data_dir=base_data_dir,
        datatype=datatype,
        interval=interval,
        csv_output_subdir=os.getenv("CSV_OUTPUT_SUBDIR"),
    )
    downloader.run()
