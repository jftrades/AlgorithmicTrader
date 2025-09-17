import json
from pathlib import Path
from typing import Tuple, Dict, Any

from lunar_metrics_download import LunarMetricsDownloader
from venue_metrics_download import VenueMetricsDownloader
from binance_data_download import CombinedCryptoDataDownloader
import binance_data_download as bdd
# Entfernt: from new_future_list_download import BinancePerpetualFuturesDiscovery

# ========================
# Konfiguration (anpassen)
# ========================
SYMBOL = "ETHUSDT-Perp"
START_DATE = "2025-01-06"
END_DATE = "2025-01-07"
BASE_DATA_DIR = str(Path(__file__).resolve().parents[3] / "DATA_STORAGE")

RUN_LUNAR = True
RUN_VENUE = True
RUN_BINANCE = True
# Entfernt: RUN_NEW_FUTURES und Fenster-Konfiguration

LUNAR_BUCKET = "hour"
BINANCE_DATATYPE = "bar"
BINANCE_INTERVAL = "1h"

SAVE_AS_CSV = True
SAVE_IN_CATALOG = True
DOWNLOAD_IF_MISSING = True
# ========================

class CryptoDataOrchestrator:
    def __init__(
        self,
        symbol: str,
        start: str,
        end: str,
        base_data_dir: str,
        run_lunar: bool,
        run_venue: bool,
        run_binance: bool,
        lunar_bucket: str,
        binance_datatype: str,
        binance_interval: str,
        save_as_csv: bool,
        save_in_catalog: bool,
        download_if_missing: bool,
    ):
        # ...existing code...
        self.symbol = symbol
        self.start = start
        self.end = end
        self.base_data_dir = base_data_dir
        self.run_lunar = run_lunar
        self.run_venue = run_venue
        self.run_binance = run_binance
        self.lunar_bucket = lunar_bucket
        self.binance_datatype = binance_datatype
        self.binance_interval = binance_interval
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.download_if_missing = download_if_missing
        self.base_symbol, self.perp_symbol = self._normalize_symbols(self.symbol)
        # Entfernt: futures-bezogene Attribute

    @staticmethod
    def _normalize_symbols(symbol: str) -> Tuple[str, str]:
        # ...existing code...
        s = symbol.upper().replace(" ", "")
        if s.endswith("-PERP"):
            perp = s
        elif s.endswith("USDT"):
            perp = f"{s}-PERP"
        elif s.endswith("USDT-PERP"):
            perp = s
        else:
            perp = f"{s}USDT-PERP"
        if "USDT" in perp:
            base = perp.split("USDT")[0].replace("-PERP", "")
        else:
            base = perp.replace("-PERP", "")
        return base, perp

    # Entfernt: run_new_futures_list

    def run_lunar_metrics(self) -> Dict[str, Any]:
        # ...existing code...
        try:
            return LunarMetricsDownloader(
                symbol=self.base_symbol,
                start_date=self.start,
                end_date=self.end,
                base_data_dir=self.base_data_dir,
                instrument_id_str=self.perp_symbol,
                bucket=self.lunar_bucket,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                download_if_missing=self.download_if_missing,
            ).run()
        except Exception as e:
            return {"error": str(e)}

    def run_venue_metrics(self) -> Dict[str, Any]:
        # ...existing code...
        try:
            return VenueMetricsDownloader(
                symbol=self.perp_symbol,
                start_date=self.start,
                end_date=self.end,
                base_data_dir=self.base_data_dir,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                download_if_missing=self.download_if_missing,
            ).run()
        except Exception as e:
            return {"error": str(e)}

    def run_binance_data(self) -> Dict[str, Any]:
        # ...existing code...
        try:
            bdd.save_as_csv = self.save_as_csv
            bdd.save_in_catalog = self.save_in_catalog
            CombinedCryptoDataDownloader(
                symbol=self.perp_symbol,
                start_date=self.start,
                end_date=self.end,
                base_data_dir=self.base_data_dir,
                datatype=self.binance_datatype,
                interval=self.binance_interval,
            ).run()
            return {
                "datatype": self.binance_datatype,
                "interval": self.binance_interval,
                "status": "ok",
            }
        except Exception as e:
            return {"error": str(e)}

    def run(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        if self.run_lunar:
            results["lunar"] = self.run_lunar_metrics()
        if self.run_venue:
            results["venue_metrics"] = self.run_venue_metrics()
        if self.run_binance:
            results["binance_data"] = self.run_binance_data()
        return {
            "input": {
                "symbol_input": self.symbol,
                "normalized_base": self.base_symbol,
                "normalized_perp": self.perp_symbol,
                "start": self.start,
                "end": self.end,
            },
            "results": results,
        }

if __name__ == "__main__":
    orchestrator = CryptoDataOrchestrator(
        symbol=SYMBOL,
        start=START_DATE,
        end=END_DATE,
        base_data_dir=BASE_DATA_DIR,
        run_lunar=RUN_LUNAR,
        run_venue=RUN_VENUE,
        run_binance=RUN_BINANCE,
        lunar_bucket=LUNAR_BUCKET,
        binance_datatype=BINANCE_DATATYPE,
        binance_interval=BINANCE_INTERVAL,
        save_as_csv=SAVE_AS_CSV,
        save_in_catalog=SAVE_IN_CATALOG,
        download_if_missing=DOWNLOAD_IF_MISSING,
    )
    summary = orchestrator.run()
    print(json.dumps(summary, indent=2))
