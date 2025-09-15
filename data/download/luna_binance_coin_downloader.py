"""
Integrated Binance Futures Discovery + LunarCrush Data Download
Automatically discovers new Binance perpetual futures and downloads social data from LunarCrush
"""
import requests
import pandas as pd
import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from lunar_crush_downloader_v2 import LunarCrushDownloader


def discover_binance_futures(months_back: int = 12) -> list:
    """
    Discover newly listed Binance Perpetual Futures.
    
    Args:
        months_back: How many months back to look for new listings
        
    Returns:
        List of dicts with 'symbol' and 'onboardDate' keys
    """
    print("Discovering Binance Perpetual Futures...")
    
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=months_back*30)
    new_futures = []
    
    for symbol_info in data["symbols"]:
        if symbol_info["contractType"] == "PERPETUAL":
            listing_date = datetime.fromtimestamp(symbol_info["onboardDate"]/1000, tz=timezone.utc)
            if listing_date > cutoff:
                new_futures.append({
                    "symbol": symbol_info["symbol"],
                    "onboardDate": listing_date.strftime("%Y-%m-%d %H:%M:%S")
                })
    
    # Filter to USDT pairs only
    new_futures = [f for f in new_futures if f["symbol"].endswith("USDT")]
    
    print(f"Found {len(new_futures)} new USDT perpetual futures in the last {months_back} months")
    
    # Show last 10 for reference
    print("Last 10 discovered futures:")
    for fut in new_futures[-10:]:
        print(f"  {fut['symbol']} - Listed: {fut['onboardDate']}")
    
    return new_futures


def save_futures_data(futures_data: list, output_path: str) -> None:
    """Save futures data to CSV."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "onboardDate"])
        writer.writeheader()
        writer.writerows(futures_data)
    
    print(f"Saved {len(futures_data)} futures to {output_path}")


def main():
    """
    Main execution:
    1. Discover Binance futures
    2. Download LunarCrush social data
    3. Save results
    """
    print("=== Binance Futures + LunarCrush Integration ===")
    
    # Configuration
    API_KEY = "your_lunarcrush_api_key_here"  # Replace with your actual API key
    MONTHS_BACK = 12  # Look back 12 months for new listings
    
    # Setup paths
    base_dir = Path(__file__).parent.parent / "DATA_STORAGE"
    futures_dir = base_dir / "project_future_scraper"
    lunarcrush_dir = base_dir / "lunarcrush_data"
    
    # Create directories
    futures_dir.mkdir(parents=True, exist_ok=True)
    lunarcrush_dir.mkdir(parents=True, exist_ok=True)
    
    futures_csv_path = futures_dir / "new_binance_perpetual_futures.csv"
    
    # Step 1: Discover Binance Futures
    try:
        futures_data = discover_binance_futures(months_back=MONTHS_BACK)
        
        if not futures_data:
            print("No new futures found.")
            return
        
        # Save futures data
        save_futures_data(futures_data, str(futures_csv_path))
        
    except Exception as e:
        print(f"Error discovering futures: {e}")
        return
    
    # Step 2: Download LunarCrush Data
    if API_KEY == "your_lunarcrush_api_key_here":
        print("\nWARNING: Please set your actual LunarCrush API key!")
        print("Skipping LunarCrush download.")
        return
    
    try:
        print(f"\n=== Starting LunarCrush Download ===")
        
        # Initialize downloader
        downloader = LunarCrushDownloader(API_KEY)
        
        # Download data (14 days of hourly data from each listing date)
        df = downloader.download_binance_futures_data(futures_data, days_from_listing=14)
        
        if not df.empty:
            # Save LunarCrush data
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = lunarcrush_dir / f"lunarcrush_binance_futures_{timestamp}.csv"
            downloader.save_data(df, str(output_path))
            
            # Additional analysis
            print(f"\n=== Analysis ===")
            print(f"Symbols with data: {df['symbol'].nunique()}")
            print(f"Total hourly data points: {len(df)}")
            print(f"Average hours of data per symbol: {len(df) / df['symbol'].nunique():.1f}")
            
            # Show metrics summary
            numeric_cols = ['galaxy_score', 'engagements', 'mentions', 'creators', 'market_dominance', 'trading_volume']
            print(f"\n=== Metrics Summary ===")
            for col in numeric_cols:
                if col in df.columns:
                    mean_val = df[col].mean()
                    max_val = df[col].max()
                    print(f"{col}: avg={mean_val:.2f}, max={max_val:.2f}")
        else:
            print("No LunarCrush data downloaded.")
    
    except Exception as e:
        print(f"Error downloading LunarCrush data: {e}")
        return
    
    print(f"\n=== Completed Successfully ===")
    print(f"Futures data: {futures_csv_path}")
    if not df.empty:
        print(f"LunarCrush data: {output_path}")


if __name__ == "__main__":
    main()
