"""
Zentrale Steuerung für Futures-Daten-Download und -Transformation via Binance
Für neu gelistete Perpetual Futures (Listing-Datum bis 1 Monat danach)
Kompatibel zu NautilusTrader 1.219
"""
from data.download.download_logic_crypto import BarTransformer, BarDownloader, find_csv_file
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import csv
import pandas as pd

class CombinedFuturesDataDownloader:
    def __init__(self, symbol, listing_date, base_data_dir, interval="5m"):
        self.symbol = symbol
        self.start_date = listing_date
        self.end_date = listing_date + timedelta(days=7)
        self.base_data_dir = base_data_dir
        self.interval = interval

    def run(self):
        if self.end_date <= self.start_date:
            print(f"[SKIP] Ungültiger Zeitraum für {self.symbol}: Enddatum {self.end_date} <= Startdatum {self.start_date}. Symbol wird übersprungen.")
            return
        print(f"[INFO] {self.symbol}: Lade Daten von {self.start_date} bis {self.end_date} ...")
        start_str = self.start_date.strftime("%Y-%m-%d_%H%M%S")
        end_str = self.end_date.strftime("%Y-%m-%d_%H%M%S")
        bar_downloader = BarDownloader(
            symbol=self.symbol,
            interval=self.interval,
            start_date=self.start_date,
            end_date=self.end_date,
            base_data_dir=self.base_data_dir
        )
        bar_downloader.run()
        processed_dir = Path(self.base_data_dir) / f"processed_bar_data_{start_str}_to_{end_str}" / "csv"
        if not processed_dir.exists():
            print(f"[SKIP] Kein Datenverzeichnis für {self.symbol} ({processed_dir}). Symbol wird übersprungen.")
            return
        try:
            csv_path = find_csv_file(self.symbol, processed_dir)
        except FileNotFoundError as e:
            print(f"[SKIP] Keine CSV für {self.symbol} gefunden: {e}. Symbol wird übersprungen.")
            return

        # Filtere die CSV nach dem gewünschten Zeitraum
        df = pd.read_csv(csv_path, header=None, names=[
            "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
        ])
        ts_start = int(pd.Timestamp(self.start_date).value)
        ts_end = int(pd.Timestamp(self.end_date).value)
        df = df[(df["timestamp"] >= ts_start) & (df["timestamp"] < ts_end)]
        if df.empty:
            print(f"[SKIP] Keine Daten im gewünschten Zeitraum für {self.symbol}. Symbol wird übersprungen.")
            return
        df.to_csv(csv_path, index=False, header=False)

        catalog_root_path = Path(self.base_data_dir) / "data_catalog_wrangled"
        wrangler_init_bar_type_string = f"{self.symbol}-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"
        from nautilus_trader.core.nautilus_pyo3 import BarSpecification, BarType, BarAggregation, PriceType, AggregationSource
        from nautilus_trader.core.nautilus_pyo3 import InstrumentId as Pyo3InstrumentId, Symbol as Pyo3Symbol, Venue as Pyo3Venue
        target_bar_spec = BarSpecification(step=5, aggregation=BarAggregation.MINUTE, price_type=PriceType.LAST)
        pyo3_instrument_id = Pyo3InstrumentId(Pyo3Symbol(f"{self.symbol}-PERP"), Pyo3Venue("BINANCE"))
        target_bar_type_obj = BarType(
            instrument_id=pyo3_instrument_id,
            spec=target_bar_spec,
            aggregation_source=AggregationSource.EXTERNAL
        )
        price_precision = 8
        size_precision = 8
        output_columns = [
            "timestamp", "open_time_ms", "open", "high", "low", "close", "volume", "number_of_trades"
        ]

        bar_transformer = BarTransformer(
            csv_path=csv_path,
            catalog_root_path=catalog_root_path,
            wrangler_init_bar_type_string=wrangler_init_bar_type_string,
            target_bar_type_obj=target_bar_type_obj,
            price_precision=price_precision,
            size_precision=size_precision,
            output_columns=output_columns,
            symbol=self.symbol,
            is_perp=True,
        )
        bar_transformer.run()

if __name__ == "__main__":
    base_data_dir = str(Path(__file__).resolve().parents[1] / "DATA_STORAGE")
    csv_path = Path(__file__).parent.parent / "DATA_STORAGE" / "project_future_scraper" / "new_binance_perpetual_futures.csv"
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row["symbol"]
            listing_date = datetime.strptime(row["onboardDate"], "%Y-%m-%d %H:%M:%S")
            downloader = CombinedFuturesDataDownloader(
                symbol=symbol,
                listing_date=listing_date,
                base_data_dir=base_data_dir,
                interval="5m"
            )
            downloader.run()
    # Nach allen Durchläufen: Lösche alle processed_bar_data_* Ordner
    storage_dir = Path(base_data_dir)
    for folder in storage_dir.glob("processed_bar_data_*_to_*"):
        try:
            shutil.rmtree(folder)
            print(f"[INFO] Bar-Ordner gelöscht: {folder}")
        except Exception as e:
            print(f"[WARN] Bar-Ordner konnte nicht gelöscht werden: {e}")
