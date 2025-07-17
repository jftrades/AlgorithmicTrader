"""
Download- und Transformationslogik für Index-Daten via Databento
Kompatibel zu NautilusTrader 1.219
"""
# die Importe aller Dateien
import datetime as dt
from pathlib import Path
import pandas as pd
import shutil
import traceback
import requests
import zipfile
import sys
from binance_historical_data import BinanceDataDumper
from nautilus_trader.core.nautilus_pyo3 import Bar, BarSpecification, BarType, BarAggregation, PriceType, AggregationSource, InstrumentId, Symbol, Venue, Price, Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.persistence.catalog import ParquetDataCatalog
import glob
from nautilus_trader.core.nautilus_pyo3 import InstrumentId, Symbol, Venue
import os

class TickDownloader:
    def __init__(self, symbol, start_date, end_date, base_data_dir):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.base_data_dir = Path(base_data_dir)
        self.temp_dir = self.base_data_dir / "temp_tick_downloads"
        self.processed_dir = self.base_data_dir / f"processed_tick_data_{start_date}_to_{end_date}" / "csv"
        self.futures_url = "https://data.binance.vision/data/futures/um/daily/trades"

    def run(self):
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        start_str = self.start_date.strftime("%Y-%m-%d")
        end_str = self.end_date.strftime("%Y-%m-%d")
        output_file = self.processed_dir / f"{self.symbol}_TICKS_{start_str}_to_{end_str}.csv"
        if output_file.exists():
            output_file.unlink()
        columns = ['trade_id', 'price', 'quantity', 'base_quantity', 'timestamp', 'is_buyer_maker']
        total_days = (self.end_date - self.start_date).days + 1
        print(f"Download {self.symbol} Ticks: {start_str} bis {end_str}")
        for n in range(total_days):
            date = self.start_date + dt.timedelta(days=n)
            filename = f"{self.symbol}-trades-{date.strftime('%Y-%m-%d')}.zip"
            url = f"{self.futures_url}/{self.symbol}/{filename}"
            zip_path = self.temp_dir / filename
            sys.stdout.write(f"\r[{n+1:>3}/{total_days}] {date.strftime('%Y-%m-%d')} ...")
            sys.stdout.flush()
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
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['price', 'quantity', 'timestamp'])
                df = df[(df['price'] > 0) & (df['quantity'] > 0) & (df['timestamp'] > 0)]
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                df['buyer_maker'] = df['is_buyer_maker'].astype(str).str.lower() == 'true'
                chunk = df[['timestamp', 'trade_id', 'price', 'quantity', 'buyer_maker']]
                mode = 'w' if n == 0 else 'a'
                header = n == 0
                chunk.to_csv(output_file, mode=mode, header=header, index=False)
                csv_file.unlink(missing_ok=True)
            zip_path.unlink(missing_ok=True)
        print("\nDownload abgeschlossen.")
        for f in self.temp_dir.glob("*"):
            f.unlink(missing_ok=True)
        self.temp_dir.rmdir()

class TickTransformer:
    def __init__(self, csv_path, catalog_root_path):
        self.csv_path = Path(csv_path)
        self.catalog_root_path = Path(catalog_root_path)

    def run(self):
        self.catalog_root_path.mkdir(parents=True, exist_ok=True)
        catalog = ParquetDataCatalog(path=self.catalog_root_path)
        instrument = TestInstrumentProvider.btcusdt_perp_binance()
        catalog.write_data([instrument])
        CHUNK_SIZE = 10_000_000
        chunk_iter = pd.read_csv(self.csv_path, chunksize=CHUNK_SIZE)
        wrangler = TradeTickDataWrangler(instrument=instrument)
        for i, chunk_df in enumerate(chunk_iter):
            print(f"Verarbeite Chunk {i+1}...")
            tmp_csv = self.catalog_root_path / f"tmp_chunk_{i}.csv"
            chunk_df.to_csv(tmp_csv, index=False)
            data = CSVTickDataLoader.load(file_path=tmp_csv)
            ticks = wrangler.process(data)
            catalog.write_data(ticks, skip_disjoint_check=True)
            tmp_csv.unlink()
        print("✅ Alle Chunks erfolgreich verarbeitet.")

class BarDownloader:
    def __init__(self, symbol, interval, start_date, end_date, base_data_dir):
        self.symbol = symbol
        self.interval = interval
        self.start_date = start_date
        self.end_date = end_date
        self.base_data_dir = base_data_dir
        self.temp_raw_download_dir = Path(base_data_dir) / "temp_raw_downloads"
        self.processed_dir = Path(base_data_dir) / f"processed_bar_data_{self.start_date}_to_{self.end_date}" / "csv"

    def run(self):
        self.temp_raw_download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        dumper = BinanceDataDumper(
            path_dir_where_to_dump=str(self.temp_raw_download_dir),
            asset_class="um",
            data_type="klines",
            data_frequency=self.interval,
        )
        dumper.dump_data(
            tickers=[self.symbol],
            date_start=self.start_date,
            date_end=self.end_date,
            is_to_update_existing=False
        )
        # Suche alle CSVs im temp_raw_download_dir
        all_csvs = list(self.temp_raw_download_dir.rglob("*.csv"))
        if not all_csvs:
            print("❌ Keine CSV-Dateien gefunden.")
            return
        print(f"📁 {len(all_csvs)} CSV-Dateien gefunden. Lade und verarbeite...")
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
                print(f"⚠️ Fehler beim Verarbeiten von {file.name}: {e}")
        if not df_list:
            print("❌ Keine gültigen Daten geladen.")
            return
        df = pd.concat(df_list, ignore_index=True)
        df.rename(columns={"open_time": "open_time_ms"}, inplace=True)
        df.drop_duplicates(subset=["open_time_ms"], inplace=True)
        df.sort_values(by="open_time_ms", inplace=True)
        df["timestamp"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True).astype("int64")
        for col in ["open", "high", "low", "close", "volume", "number_of_trades"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df_final = df[OUTPUT_COLUMNS].dropna()
        if df_final.empty:
            print("❌ Nach Filtern keine gültigen Zeilen übrig.")
            return
        start_dt = pd.to_datetime(df_final["open_time_ms"].min(), unit="ms")
        end_dt = pd.to_datetime(df_final["open_time_ms"].max(), unit="ms")

        # Korrekte Output-Path-Berechnung
        interval_num = int(self.interval.lower().replace("m", ""))
        interval_str = f"{interval_num}MINUTE"
        start_str = self.start_date.strftime("%Y-%m-%d") if hasattr(self.start_date, "strftime") else str(self.start_date)
        end_str = self.end_date.strftime("%Y-%m-%d") if hasattr(self.end_date, "strftime") else str(self.end_date)
        processed_dir = Path(self.base_data_dir) / f"processed_bar_data_{start_str}_to_{end_str}" / "csv"
        processed_dir.mkdir(parents=True, exist_ok=True)
        output_path = processed_dir / f"{self.symbol}_{interval_str}_{start_str}_to_{end_str}.csv"

        df_final.to_csv(output_path, index=False, header=False)
        print(f"✅ CSV erfolgreich gespeichert: {output_path.resolve()}")
        print(f"📅 Zeitbereich: {start_dt} bis {end_dt}")
        if self.temp_raw_download_dir.exists():
            shutil.rmtree(self.temp_raw_download_dir)
            print(f"🧹 Temporäres Verzeichnis gelöscht: {self.temp_raw_download_dir.resolve()}")

class BarTransformer:
    def __init__(
        self,
        csv_path,
        catalog_root_path,
        wrangler_init_bar_type_string,
        target_bar_type_obj,
        price_precision,
        size_precision,
        output_columns=None,
        symbol=None,
        is_perp=False,
    ):
        self.csv_path = Path(csv_path)
        self.catalog_root_path = Path(catalog_root_path)
        self.wrangler_init_bar_type_string = wrangler_init_bar_type_string
        self.target_bar_type_obj = target_bar_type_obj
        self.price_precision = price_precision
        self.size_precision = size_precision
        self.output_columns = output_columns or [
            "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
        ]
        self.symbol = symbol
        self.is_perp = is_perp

    def run(self):
        print(f"INFO: Daten werden für BarType '{self.target_bar_type_obj}' vorbereitet.")

        df = pd.read_csv(self.csv_path, header=None, names=self.output_columns)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns")
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors='coerce')

        initial_len = len(df)
        df.dropna(inplace=True)
        df = df[df["volume"] > 0]
        df = df[df["high"] != df["low"]]
        print(f"INFO: Gefiltert: {initial_len - len(df)} ungültige Zeilen entfernt, {len(df)} verbleiben.")

        wrangler = BarDataWranglerV2(
            bar_type=self.wrangler_init_bar_type_string,
            price_precision=self.price_precision,
            size_precision=self.size_precision
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
                    volume=Quantity(b_in.volume.as_double(), self.size_precision),
                    ts_event=b_in.ts_event,
                    ts_init=b_in.ts_init,
                ))
            print(f"INFO: {len(final_bars)} Bar-Objekte vom Wrangler erzeugt.")
        else:
            print("WARNUNG: Keine gültigen Bar-Objekte vom Wrangler erhalten. Beende.")
            return

        bar_type_dir = (
            self.catalog_root_path / "data" / 
            ("crypto_perpetual" if self.is_perp else "crypto_spot") / 
            self.wrangler_init_bar_type_string
        )
        if bar_type_dir.exists():
            print(f"[INFO] Entferne alten Zielordner: {bar_type_dir}")
            shutil.rmtree(bar_type_dir)
        catalog = ParquetDataCatalog(path=self.catalog_root_path)
        instrument_for_meta = get_instrument(self.symbol, self.is_perp)
        catalog.write_data([instrument_for_meta])
        catalog.write_data(final_bars)

        if instrument_for_meta.size_precision != self.size_precision:
            print(f"WARNUNG: size_precision des TestInstruments ({instrument_for_meta.size_precision}) != {self.size_precision}")


        print(f"✅ {len(final_bars)} Bars in '{self.catalog_root_path.resolve()}' gespeichert.")

        if final_bars:
            from nautilus_trader.core.datetime import unix_nanos_to_dt
            ts_min = unix_nanos_to_dt(min(bar.ts_event for bar in final_bars))
            ts_max = unix_nanos_to_dt(max(bar.ts_event for bar in final_bars))
            print(f"📈 Gespeicherter Zeitbereich: {ts_min} bis {ts_max}")
        else:
            print("❌ Keine Bars vorhanden zum Prüfen des Zeitbereichs.")

def find_csv_file(symbol, processed_dir):
    """
    Sucht eine CSV-Datei, die mit dem Symbol beginnt, im angegebenen Verzeichnis.
    Gibt den Pfad zur ersten gefundenen Datei zurück, wirft Fehler wenn keine gefunden wird.
    """
    import glob
    import os
    pattern = os.path.join(processed_dir, f"{symbol}*.csv")
    csv_files = glob.glob(pattern)
    if not csv_files:
        raise FileNotFoundError(f"Keine CSV gefunden mit Pattern: {pattern}\nVerzeichnisinhalt: {os.listdir(processed_dir) if os.path.exists(processed_dir) else 'Verzeichnis existiert nicht!'}")
    if len(csv_files) > 1:
        print(f"[WARN] Mehrere CSV-Dateien gefunden: {csv_files}. Verwende die erste.")
    return csv_files[0]

def get_instrument(symbol: str, is_perp: bool):
    if is_perp:
        # Futures (PERP)
        return TestInstrumentProvider.btcusdt_perp_binance() if symbol.upper() == "BTCUSDT" else \
            InstrumentId(Symbol(f"{symbol}-PERP"), Venue("BINANCE"))
    else:
        # Spot
        return TestInstrumentProvider.btcusdt_binance() if symbol.upper() == "BTCUSDT" else \
            InstrumentId(Symbol(symbol), Venue("BINANCE"))