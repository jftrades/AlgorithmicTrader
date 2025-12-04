"""
Bybit Data Download Orchestrator

Coordinates downloads from multiple data sources:
1. Bybit OHLCV bars and trade ticks (bybit_data_download)
2. Bybit venue metrics (bybit_venue_metrics_download)
3. Third-party data (Lunar, Fear & Greed) - exchange-agnostic

Key differences from Binance version:
- Uses -LINEAR suffix instead of -PERP
- BYBIT venue instead of BINANCE
- No BinanceDataDumper dependency
- Direct Bybit V5 API calls
"""

import json
import os
from pathlib import Path
from typing import Tuple, Dict, Any

from bybit_venue_metrics_download import BybitVenueMetricsDownloader
from bybit_data_download import CombinedCryptoDataDownloader
import bybit_data_download as bdd

# Import third-party downloaders from binance_downloads (exchange-agnostic)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "binance_downloads"))
from lunar_metrics_download import LunarMetricsDownloader
from fear_and_greed_download import FearAndGreedDownloader


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "BTCUSDT-LINEAR"  # Changed from -PERP to -LINEAR for Bybit
START_DATE = "2024-01-01"
END_DATE = "2024-01-07"
BASE_DATA_DIR = str(Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data_catalog")

# Toggle which downloaders to run
RUN_LUNAR = False
RUN_VENUE = False
RUN_BYBIT = True
RUN_FNG = False

# Lunar configuration (exchange-agnostic)
LUNAR_BUCKET = "hour"

# Bybit data configuration
BYBIT_DATATYPE = "bar"  # or "tick"
BYBIT_INTERVAL = "15m"

# Fear & Greed configuration (exchange-agnostic)
FNG_INSTRUMENT_ID = "FNG-INDEX.BYBIT"

# Output configuration
SAVE_AS_CSV = True
SAVE_IN_CATALOG = True
DOWNLOAD_IF_MISSING = True
CSV_OUTPUT_SUBDIR = None  # Optional: specify subdirectory for CSV output


# ============================================================================
# ORCHESTRATOR CLASS
# ============================================================================

class BybitDataOrchestrator:
    """
    Orchestrates data downloads from Bybit and third-party sources.
    
    Manages multiple downloader classes and consolidates results.
    """
    
    def __init__(
        self,
        symbol: str,
        start: str,
        end: str,
        base_data_dir: str,
        run_lunar: bool,
        run_venue: bool,
        run_bybit: bool,
        lunar_bucket: str,
        bybit_datatype: str,
        bybit_interval: str,
        save_as_csv: bool,
        save_in_catalog: bool,
        download_if_missing: bool,
        run_fng: bool = False,
        fng_instrument_id: str = "FNG-INDEX.BYBIT",
        csv_output_subdir: str | None = None,
    ):
        self.symbol = symbol
        self.start = start
        self.end = end
        self.base_data_dir = base_data_dir
        self.run_lunar = run_lunar
        self.run_venue = run_venue
        self.run_bybit = run_bybit
        self.lunar_bucket = lunar_bucket
        self.bybit_datatype = bybit_datatype
        self.bybit_interval = bybit_interval
        self.save_as_csv = save_as_csv
        self.save_in_catalog = save_in_catalog
        self.download_if_missing = download_if_missing
        self.run_fng = run_fng
        self.fng_instrument_id = fng_instrument_id
        self.csv_output_subdir = csv_output_subdir
        
        # Normalize symbols
        self.base_symbol, self.linear_symbol = self._normalize_symbols(self.symbol)

    @staticmethod
    def _normalize_symbols(symbol: str) -> Tuple[str, str]:
        """
        Normalize symbol input to base and linear perpetual formats.
        
        Args:
            symbol: Input symbol (various formats accepted)
            
        Returns:
            Tuple of (base_symbol, linear_perpetual_symbol)
            
        Examples:
            "BTCUSDT" -> ("BTC", "BTCUSDT-LINEAR")
            "BTCUSDT-LINEAR" -> ("BTC", "BTCUSDT-LINEAR")
            "BTC" -> ("BTC", "BTCUSDT-LINEAR")
        """
        s = symbol.upper().replace(" ", "")
        
        # Handle -LINEAR suffix
        if s.endswith("-LINEAR"):
            linear = s
        elif s.endswith("USDT"):
            linear = f"{s}-LINEAR"
        elif s.endswith("USDT-LINEAR"):
            linear = s
        else:
            linear = f"{s}USDT-LINEAR"
        
        # Extract base symbol
        if "USDT" in linear:
            base = linear.split("USDT")[0].replace("-LINEAR", "")
        else:
            base = linear.replace("-LINEAR", "")
        
        return base, linear

    def run_lunar_metrics(self) -> Dict[str, Any]:
        """
        Download social metrics from LunarCrush API.
        
        Exchange-agnostic - works for any venue.
        
        Returns:
            Dict with download statistics or error
        """
        print("\n" + "="*60)
        print("RUNNING: Lunar Metrics Download")
        print("="*60)
        
        try:
            return LunarMetricsDownloader(
                symbol=self.base_symbol,
                start_date=self.start,
                end_date=self.end,
                base_data_dir=self.base_data_dir,
                instrument_id_str=self.linear_symbol,  # Use -LINEAR format
                bucket=self.lunar_bucket,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                download_if_missing=self.download_if_missing,
            ).run()
        except Exception as e:
            print(f"[ERROR] Lunar metrics download failed: {e}")
            return {"error": str(e)}

    def run_venue_metrics(self) -> Dict[str, Any]:
        """
        Download Bybit-specific venue metrics.
        
        Uses Bybit V5 API endpoints for:
        - Open interest
        - Long/short account ratio
        - Funding rate history
        
        Returns:
            Dict with download statistics or error
        """
        print("\n" + "="*60)
        print("RUNNING: Bybit Venue Metrics Download")
        print("="*60)
        
        try:
            return BybitVenueMetricsDownloader(
                symbol=self.linear_symbol,
                start_date=self.start,
                end_date=self.end,
                base_data_dir=self.base_data_dir,
                interval="1h",
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                csv_output_subdir=self.csv_output_subdir,
            ).run()
        except Exception as e:
            print(f"[ERROR] Venue metrics download failed: {e}")
            return {"error": str(e)}

    def run_bybit_data(self) -> Dict[str, Any]:
        """
        Download OHLCV bars or trade ticks from Bybit.
        
        Uses Bybit V5 API for klines or bulk download service for ticks.
        
        Returns:
            Dict with download statistics or error
        """
        print("\n" + "="*60)
        print(f"RUNNING: Bybit {self.bybit_datatype.upper()} Download")
        print("="*60)
        
        try:
            # Set module-level flags (same pattern as Binance version)
            bdd.save_as_csv = self.save_as_csv
            bdd.save_in_catalog = self.save_in_catalog
            
            CombinedCryptoDataDownloader(
                symbol=self.linear_symbol,
                start_date=self.start,
                end_date=self.end,
                base_data_dir=self.base_data_dir,
                datatype=self.bybit_datatype,
                interval=self.bybit_interval,
                csv_output_subdir=self.csv_output_subdir,
            ).run()
            
            return {
                "datatype": self.bybit_datatype,
                "interval": self.bybit_interval,
                "status": "ok",
            }
        except Exception as e:
            print(f"[ERROR] Bybit data download failed: {e}")
            return {"error": str(e)}

    def run_fear_greed(self) -> Dict[str, Any]:
        """
        Download Fear & Greed Index data.
        
        Exchange-agnostic - works for any venue.
        
        Returns:
            Dict with download statistics or error
        """
        print("\n" + "="*60)
        print("RUNNING: Fear & Greed Index Download")
        print("="*60)
        
        try:
            return FearAndGreedDownloader(
                start_date=self.start,
                end_date=self.end,
                base_data_dir=self.base_data_dir,
                instrument_id_str=self.fng_instrument_id,
                save_as_csv=self.save_as_csv,
                save_in_catalog=self.save_in_catalog,
                download_if_missing=self.download_if_missing,
                remove_processed=True,
            ).run()
        except Exception as e:
            print(f"[ERROR] Fear & Greed download failed: {e}")
            return {"error": str(e)}

    def run(self) -> Dict[str, Any]:
        """
        Execute all enabled downloaders.
        
        Returns:
            Dict with input parameters and results from each downloader
        """
        print("\n" + "="*80)
        print("BYBIT DATA ORCHESTRATOR - STARTING")
        print("="*80)
        print(f"Symbol: {self.symbol} -> {self.linear_symbol}")
        print(f"Date Range: {self.start} to {self.end}")
        print(f"Enabled: Lunar={self.run_lunar}, Venue={self.run_venue}, "
              f"Bybit={self.run_bybit}, FnG={self.run_fng}")
        
        results: Dict[str, Any] = {}
        
        if self.run_lunar:
            results["lunar"] = self.run_lunar_metrics()
        
        if self.run_venue:
            results["venue_metrics"] = self.run_venue_metrics()
        
        if self.run_bybit:
            results["bybit_data"] = self.run_bybit_data()
        
        if self.run_fng:
            results["fear_greed"] = self.run_fear_greed()
        
        print("\n" + "="*80)
        print("BYBIT DATA ORCHESTRATOR - COMPLETE")
        print("="*80)
        
        return {
            "input": {
                "symbol_input": self.symbol,
                "normalized_base": self.base_symbol,
                "normalized_linear": self.linear_symbol,
                "start": self.start,
                "end": self.end,
            },
            "results": results,
        }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    orchestrator = BybitDataOrchestrator(
        symbol=SYMBOL,
        start=START_DATE,
        end=END_DATE,
        base_data_dir=BASE_DATA_DIR,
        run_lunar=RUN_LUNAR,
        run_venue=RUN_VENUE,
        run_bybit=RUN_BYBIT,
        lunar_bucket=LUNAR_BUCKET,
        bybit_datatype=BYBIT_DATATYPE,
        bybit_interval=BYBIT_INTERVAL,
        save_as_csv=SAVE_AS_CSV,
        save_in_catalog=SAVE_IN_CATALOG,
        download_if_missing=DOWNLOAD_IF_MISSING,
        run_fng=RUN_FNG,
        fng_instrument_id=FNG_INSTRUMENT_ID,
        csv_output_subdir=CSV_OUTPUT_SUBDIR,
    )
    
    summary = orchestrator.run()
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(json.dumps(summary, indent=2))
