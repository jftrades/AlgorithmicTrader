import datetime as dt
from datetime import datetime
from pathlib import Path
import pandas as pd
import shutil
import requests
import zipfile
import sys
from decimal import Decimal  # neu für Margin-Umrechnung
from binance_historical_data import BinanceDataDumper
from nautilus_trader.core.nautilus_pyo3 import Bar, BarSpecification, BarType, BarAggregation, PriceType, AggregationSource, InstrumentId, Symbol, Venue, Price, Quantity
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.persistence.catalog import ParquetDataCatalog
import glob
import os


# Parameter hier anpassen
symbol = "SOLUSDT-PERP"
start_date = "2025-01-01"
end_date = "2025-01-02"
base_data_dir = str(Path(__file__).resolve().parents[3] / "DATA_STORAGE")
datatype = "bar"  # oder "tick"
interval = "1h"    # nur für Bars relevant

save_as_csv = True    # Bars zusätzlich als OHLCV.csv speichern
save_in_catalog = True  # Bars in Nautilus Parquet-Katalog schreiben

class CombinedCryptoDataDownloader:
    def __init__(self, symbol, start_date, end_date, base_data_dir, datatype="tick", interval="1h"):
        # Symbol-Handling für Spot und Futures (PERP)
        self.is_perp = symbol.endswith("-PERP")
        self.symbol_for_binance = symbol.replace("-PERP", "")
        self.symbol_for_nt = symbol if self.is_perp else symbol
        self.symbol = symbol
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if isinstance(start_date, str) else start_date
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if isinstance(end_date, str) else end_date
        self.base_data_dir = base_data_dir
        self.datatype = datatype
        self.interval = interval
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog

    def run(self):
        if self.datatype == "tick":
            print("Mode: tick")
            tick_downloader = TickDownloader(
                symbol=self.symbol_for_binance,
                start_date=self.start_date,
                end_date=self.end_date,
                base_data_dir=self.base_data_dir
            )
            tick_downloader.run()
            processed_dir = str(Path(self.base_data_dir) / "cache" / f"processed_tick_data_{self.start_date}_to_{self.end_date}" / "csv")
            csv_path = find_csv_file(self.symbol_for_binance, processed_dir)
            catalog_root_path = f"{self.base_data_dir}/data_catalog_wrangled"
            tick_transformer = TickTransformer(
                csv_path=csv_path,
                catalog_root_path=catalog_root_path,
                symbol=self.symbol_for_binance,
                is_perp=self.is_perp,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                base_data_dir=self.base_data_dir,
            )
            tick_transformer.run()
            try:
                shutil.rmtree(Path(self.base_data_dir) / "cache" / f"processed_tick_data_{self.start_date}_to_{self.end_date}")
                print(f"[INFO] Tick-Ordner gelöscht: {Path(self.base_data_dir) / 'cache' / f'processed_tick_data_{self.start_date}_to_{self.end_date}'}")
            except Exception as e:
                print(f"[WARN] Tick-Ordner konnte nicht gelöscht werden: {e}")
            print("Tick pipeline completed.")
        elif self.datatype == "bar":
            print("Mode: bar")
            bar_downloader = BarDownloader(
                symbol=self.symbol_for_binance,
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
            
            csv_path = find_csv_file(self.symbol_for_binance, processed_dir)
            catalog_root_path = f"{self.base_data_dir}/data_catalog_wrangled"

            # NautilusTrader BarType und InstrumentId korrekt erzeugen
            from nautilus_trader.core.nautilus_pyo3 import (
                BarSpecification, BarType, BarAggregation, PriceType, AggregationSource, InstrumentId, Symbol, Venue
            )
            # Verwende das Intervall-Token direkt, keine Umrechnung in Minuten!
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

            if self.is_perp:
                wrangler_init_bar_type_string = f"{self.symbol_for_binance}-PERP.BINANCE-{interval_token_for_wrangler}-LAST-EXTERNAL"
                target_instrument_id = InstrumentId(Symbol(f"{self.symbol_for_binance}-PERP"), Venue("BINANCE"))
            else:
                wrangler_init_bar_type_string = f"{self.symbol_for_binance}.BINANCE-{interval_token_for_wrangler}-LAST-EXTERNAL"
                target_instrument_id = InstrumentId(Symbol(self.symbol_for_binance), Venue("BINANCE"))

            # BarSpecification: step ist jetzt ein Integer und aggregation korrekt gesetzt
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
                symbol=self.symbol_for_binance,
                is_perp=self.is_perp,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                base_data_dir=self.base_data_dir,
            )
            bar_transformer.run()
            try:
                shutil.rmtree(Path(self.base_data_dir) / "cache" / f"processed_bar_data_{start_str}_to_{end_str}")
                print(f"[INFO] Bar-Ordner gelöscht: {Path(self.base_data_dir) / 'cache' / f'processed_bar_data_{start_str}_to_{end_str}'}")
            except Exception as e:
                print(f"[WARN] Bar-Ordner konnte nicht gelöscht werden: {e}")
            print("Bar pipeline completed.")
        else:
            raise ValueError(f"Unknown datatype: {self.datatype}")
        

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
        self.futures_url = "https://data.binance.vision/data/futures/um/daily/trades"

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
            filename = f"{self.symbol}-trades-{date:%Y-%m-%d}.zip"
            url = f"{self.futures_url}/{self.symbol}/{filename}"
            zip_path = self.temp_dir / filename
            r = requests.get(url)
            if r.status_code != 200:
                continue
            with open(zip_path, "wb") as f:
                f.write(r.content)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(self.temp_dir)
            for csv_file in self.temp_dir.glob("*.csv"):
                df = pd.read_csv(csv_file, names=columns, low_memory=False)
                df['price'] = pd.to_numeric(df['price'], errors='coerce')
                df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')  # ms since epoch
                df = df.dropna(subset=['price', 'quantity', 'timestamp'])
                df = df[(df['price'] > 0) & (df['quantity'] > 0) & (df['timestamp'] > 0)]
                df['timestamp'] = df['timestamp'].astype('int64')  # sicherstellen int
                df['buyer_maker'] = df['is_buyer_maker'].astype(str).str.lower() == 'true'
                chunk = df[['timestamp', 'trade_id', 'price', 'quantity', 'buyer_maker']]
                mode = 'w' if n == 0 else 'a'
                header = n == 0
                chunk.to_csv(output_file, mode=mode, header=header, index=False)
                csv_file.unlink(missing_ok=True)
            zip_path.unlink(missing_ok=True)
        for f in self.temp_dir.glob("*"):
            f.unlink(missing_ok=True)
        self.temp_dir.rmdir()
        print(f"Tick data written: {output_file}")

class TickTransformer:
    def __init__(self, csv_path, catalog_root_path,
                 symbol=None, is_perp=False,
                 save_as_csv=False, save_in_catalog=True,
                 base_data_dir=None):
        self.csv_path = Path(csv_path)
        self.catalog_root_path = Path(catalog_root_path)
        self.symbol = symbol
        self.is_perp = is_perp
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.base_data_dir = Path(base_data_dir) if base_data_dir else self.catalog_root_path

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
            # Parsing timestamp robust: numeric (ms) oder ISO-String aus Altbeständen
            if self.save_as_csv:
                if csv_out_path is None:
                    sym_dir = self.base_data_dir / "csv_data" / (self.symbol + ("-PERP" if self.is_perp else ""))
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

                ts_nano = ts.astype('int64')  # statt deprecated .view("int64")

                rows = pd.DataFrame({
                    "timestamp_nano": ts_nano,
                    "timestamp_iso": ts.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "symbol": self.symbol + ("-PERP" if self.is_perp else ""),
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

class BarDownloader:
    def __init__(self, symbol, interval, start_date, end_date, base_data_dir):
        self.symbol = symbol
        self.interval = interval
        self.start_date = start_date
        self.end_date = end_date
        self.base_data_dir = base_data_dir
        self.cache_root = Path(base_data_dir) / "cache"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.temp_raw_download_dir = self.cache_root / "temp_raw_downloads"
        start_str = self.start_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.start_date, "strftime") else str(self.start_date).replace(":", "").replace(" ", "_")
        end_str = self.end_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.end_date, "strftime") else str(self.end_date).replace(":", "").replace(" ", "_")
        self.processed_dir = self.cache_root / f"processed_bar_data_{start_str}_to_{end_str}" / "csv"

    def run(self):
        self.temp_raw_download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        print(f"Bar download started: {self.symbol} ({self.interval})")
        dumper = BinanceDataDumper(
            path_dir_where_to_dump=str(self.temp_raw_download_dir),
            asset_class="um",
            data_type="klines",
            data_frequency=self.interval,
        )
        date_start = self.start_date.date() if hasattr(self.start_date, "date") else self.start_date
        date_end = self.end_date.date() if hasattr(self.end_date, "date") else self.end_date
        dumper.dump_data(
            tickers=[self.symbol],
            date_start=date_start,
            date_end=date_end,
            is_to_update_existing=False
        )
        all_csvs = list(self.temp_raw_download_dir.rglob("*.csv"))
        if not all_csvs:
            print("No bar source CSV files found.")
            return
        EXPECTED_COLUMNS = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_volume", "ignore"
        ]
        OUTPUT_COLUMNS = ["timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"]
        def normalize_timestamp_units(df):
            max_raw = df["open_time"].max()
            ts_2200 = int(pd.Timestamp("2200-01-01").timestamp() * 1000)
            if max_raw > ts_2200:
                for factor in [1000, 1000000]:
                    scaled = df["open_time"] // factor
                    if scaled.max() < ts_2200:
                        df["open_time"] = scaled
                        return df
                raise ValueError("open_time enthält nicht korrigierbare Zeitstempel.")
            return df
        df_list = []
        for file in all_csvs:
            try:
                with open(file, "r") as f:
                    first_line = f.readline()
                skip = 1 if "open_time" in first_line else 0
                df = pd.read_csv(
                    file,
                    header=None,
                    names=EXPECTED_COLUMNS,
                    dtype={"open_time": "int64"},
                    skiprows=skip,
                )
                df = normalize_timestamp_units(df)
                df_list.append(df)
            except Exception as e:
                pass
        if not df_list:
            print("No valid data loaded.")
            return
        df = pd.concat(df_list, ignore_index=True)

        # NEU: Zeitfenster-Filter exakt anwenden
        start_ms = int(pd.Timestamp(self.start_date).tz_localize("UTC").timestamp() * 1000)
        end_ms = int((pd.Timestamp(self.end_date) + pd.Timedelta(days=1)).tz_localize("UTC").timestamp() * 1000) - 1
        before_len = len(df)
        df = df[(df["open_time"] >= start_ms) & (df["open_time"] <= end_ms)]
        after_len = len(df)
        if after_len < before_len:
            print(f"[INFO] Filter applied: kept {after_len}/{before_len} rows in range {self.start_date} .. {self.end_date}")

        df.rename(columns={"open_time": "open_time_ms"}, inplace=True)
        df.drop_duplicates(subset=["open_time_ms"], inplace=True)
        df.sort_values(by="open_time_ms", inplace=True)
        df["timestamp"] = df["open_time_ms"].astype("int64")
        df_final = df[OUTPUT_COLUMNS].dropna()
        start_str = self.start_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.start_date, "strftime") else str(self.start_date).replace(":", "").replace(" ", "_")
        end_str = self.end_date.strftime("%Y-%m-%d_%H%M%S") if hasattr(self.end_date, "strftime") else str(self.end_date).replace(":", "").replace(" ", "_")
        processed_dir = Path(self.base_data_dir) / "cache" / f"processed_bar_data_{start_str}_to_{end_str}" / "csv"
        processed_dir.mkdir(parents=True, exist_ok=True)
        output_path = processed_dir / f"{self.symbol}_{self.interval}_{start_str}_to_{end_str}.csv"
        df_final.to_csv(output_path, index=False, header=False)
        print(f"Bar source CSV written: {output_path}")
        if self.temp_raw_download_dir.exists():
            shutil.rmtree(self.temp_raw_download_dir)

class BarTransformer:
    def __init__(
        self,
        csv_path,
        catalog_root_path,
        wrangler_init_bar_type_string,
        target_bar_type_obj,
        output_columns=None,
        symbol=None,
        is_perp=False,
        save_as_csv=False,
        save_in_catalog=True,
        base_data_dir=None,
    ):
        self.csv_path = Path(csv_path)
        self.catalog_root_path = Path(catalog_root_path)
        self.wrangler_init_bar_type_string = wrangler_init_bar_type_string
        self.target_bar_type_obj = target_bar_type_obj
        self.output_columns = output_columns or [
            "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
        ]
        self.symbol = symbol
        self.is_perp = is_perp
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.base_data_dir = Path(base_data_dir) if base_data_dir else Path(catalog_root_path)

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
        initial_len = len(df)
        df.dropna(inplace=True)
        df = df[(df["volume"] > 0) & (df["high"] != df["low"])]
        print(f"Bars after filter: {len(df)}")
        instrument_for_meta = get_instrument(self.symbol, self.is_perp)
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
                        self.symbol + ("-PERP" if self.is_perp else ""),
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
        if self.save_in_catalog:
            bar_type_dir = (
                self.catalog_root_path / "data" /
                ("crypto_perpetual" if self.is_perp else "crypto_spot") /
                self.wrangler_init_bar_type_string
            )
            if bar_type_dir.exists():
                shutil.rmtree(bar_type_dir)
            catalog = ParquetDataCatalog(path=self.catalog_root_path)
            catalog.write_data([instrument_for_meta])
            catalog.write_data(final_bars)
            print(f"Bars saved to catalog: {len(final_bars)}")

            csv_dir = self.base_data_dir / "csv_data" / (self.symbol + ("-PERP" if self.is_perp else ""))
            csv_dir.mkdir(parents=True, exist_ok=True)
            out_file = csv_dir / "OHLCV.csv"
            df_out.to_csv(out_file, index=False)
            print(f"Bars CSV exported: {out_file}")
        if final_bars:
            ts_min = unix_nanos_to_dt(min(b.ts_event for b in final_bars))
            ts_max = unix_nanos_to_dt(max(b.ts_event for b in final_bars))
            print(f"Bars range: {ts_min} - {ts_max}")

def find_csv_file(symbol, processed_dir):
    pattern = os.path.join(processed_dir, f"{symbol}*.csv")
    csv_files = glob.glob(pattern)
    if len(csv_files) == 0:
        raise FileNotFoundError(f"No CSV for pattern {pattern}")
    selected = csv_files[0]
    return selected

def _fetch_single_symbol_info(symbol: str, is_perp: bool) -> dict:
    base_url = "https://fapi.binance.com/fapi/v1/exchangeInfo" if is_perp else "https://api.binance.com/api/v3/exchangeInfo"
    resp = requests.get(base_url, params={"symbol": symbol}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    symbols = data.get("symbols") or []
    if not symbols:
        raise ValueError(f"exchangeInfo: Symbol '{symbol}' nicht gefunden (is_perp={is_perp}).")
    return symbols[0]

def get_instrument(symbol: str, is_perp: bool):
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.test_kit.providers import TestInstrumentProvider
    from nautilus_trader.model.objects import Price, Quantity

    raw_symbol = symbol.replace("-PERP", "") if is_perp else symbol
    info = _fetch_single_symbol_info(raw_symbol, is_perp)
    filters = {f["filterType"]: f for f in info["filters"]}
    tick_size_str = filters["PRICE_FILTER"]["tickSize"]
    step_size_str = filters["LOT_SIZE"]["stepSize"]
    use_price_precision = int(info["pricePrecision"])
    use_size_precision = int(info["quantityPrecision"])
    if is_perp:
        margin_init = Decimal(info["requiredMarginPercent"]) / Decimal(100)
        margin_maint = Decimal(info["maintMarginPercent"]) / Decimal(100)
    else:
        margin_init = Decimal("0")
        margin_maint = Decimal("0")
    min_notional = filters.get("MIN_NOTIONAL", {}).get("notional")
    min_qty = filters["LOT_SIZE"]["minQty"]
    max_qty = filters["LOT_SIZE"]["maxQty"]
    template = TestInstrumentProvider.btcusdt_perp_binance() if is_perp else TestInstrumentProvider.btcusdt_binance()
    inst_id = InstrumentId(Symbol(f"{raw_symbol}-PERP"), Venue("BINANCE")) if is_perp else InstrumentId(Symbol(raw_symbol), Venue("BINANCE"))
    instrument = template.__class__(
        instrument_id=inst_id,
        raw_symbol=Symbol(raw_symbol),
        base_currency=template.base_currency,
        quote_currency=template.quote_currency,
        settlement_currency=template.settlement_currency,
        is_inverse=template.is_inverse,
        price_precision=use_price_precision,
        size_precision=use_size_precision,
        price_increment=Price.from_str(tick_size_str),
        size_increment=Quantity.from_str(step_size_str),
        margin_init=margin_init,
        margin_maint=margin_maint,
        maker_fee=template.maker_fee,
        taker_fee=template.taker_fee,
        ts_event=template.ts_event,
        ts_init=template.ts_init,
    )
    return instrument



if __name__ == "__main__":
    downloader = CombinedCryptoDataDownloader(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_data_dir=base_data_dir,
        datatype=datatype,
        interval=interval,
    )
    downloader.run()
