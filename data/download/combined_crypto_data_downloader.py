"""
Zentrale Steuerung für crypto-Daten-Download und -Transformation via Binance
Kompatibel zu NautilusTrader 1.219
"""
from data.download.download_logic_crypto import TickDownloader, BarDownloader, TickTransformer, BarTransformer, find_csv_file
from pathlib import Path
from datetime import datetime
import shutil

# Parameter hier anpassen
symbol = "BTCUSDT-PERP"
start_date = "2024-10-01"
end_date = "2024-10-04"
base_data_dir = str(Path(__file__).resolve().parents[1] / "DATA_STORAGE")
datatype = "tick"  # oder "tick"
interval = "5min"    # nur für Bars relevant

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

    def run(self):
        if self.datatype == "tick":
            print("[INFO] Starte Tick-Download und -Transformation...")
            tick_downloader = TickDownloader(
                symbol=self.symbol_for_binance,
                start_date=self.start_date,
                end_date=self.end_date,
                base_data_dir=self.base_data_dir
            )
            tick_downloader.run()
            processed_dir = str(Path(self.base_data_dir) / f"processed_tick_data_{self.start_date}_to_{self.end_date}" / "csv")
            csv_path = find_csv_file(self.symbol_for_binance, processed_dir)
            catalog_root_path = f"{self.base_data_dir}/data_catalog_wrangled"
            tick_transformer = TickTransformer(
                csv_path=csv_path,
                catalog_root_path=catalog_root_path
            )
            tick_transformer.run()
            try:
                shutil.rmtree(Path(self.base_data_dir) / f"processed_tick_data_{self.start_date}_to_{self.end_date}")
                print(f"[INFO] Tick-Ordner gelöscht: {Path(self.base_data_dir) / f'processed_tick_data_{self.start_date}_to_{self.end_date}'}")
            except Exception as e:
                print(f"[WARN] Tick-Ordner konnte nicht gelöscht werden: {e}")
        elif self.datatype == "bar":
            print("[INFO] Starte Bar-Download und -Transformation...")
            bar_downloader = BarDownloader(
                symbol=self.symbol_for_binance,
                interval=self.interval,
                start_date=self.start_date,
                end_date=self.end_date,
                base_data_dir=self.base_data_dir
            )
            bar_downloader.run()
            processed_dir = str(Path(self.base_data_dir) / f"processed_bar_data_{self.start_date}_to_{self.end_date}" / "csv")
            csv_path = find_csv_file(self.symbol_for_binance, processed_dir)
            catalog_root_path = f"{self.base_data_dir}/data_catalog_wrangled"

            # NautilusTrader BarType und InstrumentId korrekt erzeugen
            from nautilus_trader.core.nautilus_pyo3 import (
                BarSpecification, BarType, BarAggregation, PriceType, AggregationSource, InstrumentId, Symbol, Venue
            )
            interval_num = int(self.interval.lower().replace("m", ""))
            interval_str = f"{interval_num}-MINUTE"

            if self.is_perp:
                wrangler_init_bar_type_string = f"{self.symbol_for_binance}-PERP.BINANCE-{interval_str}-LAST-EXTERNAL"
                target_instrument_id = InstrumentId(Symbol(f"{self.symbol_for_binance}-PERP"), Venue("BINANCE"))
            else:
                wrangler_init_bar_type_string = f"{self.symbol_for_binance}.BINANCE-{interval_str}-LAST-EXTERNAL"
                target_instrument_id = InstrumentId(Symbol(self.symbol_for_binance), Venue("BINANCE"))

            target_bar_spec = BarSpecification(
                step=interval_num,
                aggregation=BarAggregation.MINUTE,
                price_type=PriceType.LAST
            )
            target_bar_type_obj = BarType(
                instrument_id=target_instrument_id,
                spec=target_bar_spec,
                aggregation_source=AggregationSource.EXTERNAL
            )
            price_precision = 1
            size_precision = 3
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
                symbol=self.symbol_for_binance,
                is_perp=self.is_perp,
            )
            bar_transformer.run()
            try:
                shutil.rmtree(Path(self.base_data_dir) / f"processed_bar_data_{self.start_date}_to_{self.end_date}")
                print(f"[INFO] Bar-Ordner gelöscht: {Path(self.base_data_dir) / f'processed_bar_data_{self.start_date}_to_{self.end_date}'}")
            except Exception as e:
                print(f"[WARN] Bar-Ordner konnte nicht gelöscht werden: {e}")
        else:
            raise ValueError(f"Unbekannter Datentyp: {self.datatype}")

if __name__ == "__main__":
    downloader = CombinedCryptoDataDownloader(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_data_dir=base_data_dir,
        datatype=datatype,
        interval=interval
    )
    downloader.run()