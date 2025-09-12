"""
LunarCrush API v4 Downloader for Binance Futures Listing Data
Downloads hourly social data for 6 specific metrics from 14 days after listing
"""
import requests
import pandas as pd
import time
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class LunarCrushDownloader:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://lunarcrush.com/api4/public"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        
        # Rate limiting
        self.requests_per_minute = 10
        self.requests_per_day = 2000
        self.daily_request_count = 0
        self.last_request_time = 0
        
    def _wait_for_rate_limit(self):
        """Ensure we don't exceed rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        # Ensure at least 6 seconds between requests (10 per minute)
        if time_since_last < 6:
            time.sleep(6 - time_since_last)
            
        self.last_request_time = time.time()
        self.daily_request_count += 1
        
    def _symbol_to_topic(self, symbol: str) -> str:
        if symbol.endswith('USDT'):
            base_symbol = symbol[:-4]
        else:
            base_symbol = symbol
        
        return base_symbol.lower()
    
    def get_topic_time_series(self, topic: str, listing_timestamp: int) -> Dict:
        """
        Get 14 days of hourly time series data starting from listing timestamp.
        
        Uses the Topic Time Series v2 endpoint which provides all metrics in one call:
        - GalaxyScore (galaxy_score)
        - Engagements (interactions) 
        - Mentions (posts_active)
        - Creators (contributors_active)
        - Market Dominance (market_dominance)
        - Trading Volume (volume_24h)
        """
        self._wait_for_rate_limit()
        
        # Calculate time range: 14 days from listing
        start_time = listing_timestamp
        end_time = start_time + (14 * 24 * 3600)  # 14 days in seconds
        
        endpoint = f"{self.base_url}/topic/{topic}/time-series/v2"
        params = {
            "bucket": "hour",  # Hourly data
            "start": start_time,
            "end": end_time
        }
        
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for {topic}: {e}")
            return {}
    
    def _process_time_series_data(self, symbol: str, topic: str, data: Dict, listing_timestamp: int) -> pd.DataFrame:
        records = []
        
        if 'data' not in data:
            print(f"No data found for {symbol}")
            return pd.DataFrame()
        
        listing_datetime = datetime.fromtimestamp(listing_timestamp)
        
        for point in data['data']:
            # Calculate hours from listing
            point_timestamp = point.get('time', 0)
            point_datetime = datetime.fromtimestamp(point_timestamp)
            hours_from_listing = int((point_timestamp - listing_timestamp) / 3600)
            
            record = {
                'symbol': symbol,
                'topic': topic,
                'listing_timestamp': listing_timestamp,
                'listing_date': listing_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'data_timestamp': point_timestamp,
                'data_datetime': point_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'hours_from_listing': hours_from_listing,
                
                # 6 Requested metrics
                'galaxy_score': point.get('galaxy_score', 0),
                'engagements': point.get('interactions', 0),
                'mentions': point.get('posts_active', 0),
                'creators': point.get('contributors_active', 0),
                'market_dominance': point.get('market_dominance', 0),
                'trading_volume': point.get('volume_24h', 0),
                
                # Additional useful metrics
                'sentiment': point.get('sentiment', 0),
                'social_dominance': point.get('social_dominance', 0),
                'alt_rank': point.get('alt_rank', 0),
                'price': point.get('close', 0)
            }
            records.append(record)
        
        return pd.DataFrame(records)
    
    def download_binance_futures_data(self, futures_data: List[Dict], days_from_listing: int = 14) -> pd.DataFrame:
        all_data = []
        
        print(f"Starting download for {len(futures_data)} futures...")
        print(f"Requesting {days_from_listing} days of hourly data per coin")
        
        if len(futures_data) > self.requests_per_day:
            print(f"WARNING: {len(futures_data)} coins exceeds daily limit of {self.requests_per_day}")
            print("Processing first 2000 coins only...")
            futures_data = futures_data[:2000]
        
        for i, future in enumerate(futures_data):
            symbol = future['symbol']
            listing_date_str = future['onboardDate']
            
            # Convert listing date to timestamp
            try:
                listing_dt = datetime.strptime(listing_date_str, '%Y-%m-%d %H:%M:%S')
                listing_timestamp = int(listing_dt.timestamp())
            except ValueError:
                print(f"Invalid date format for {symbol}: {listing_date_str}")
                continue
            
            # Convert symbol to topic
            topic = self._symbol_to_topic(symbol)
            
            print(f"Processing {symbol} ({topic}) - {i+1}/{len(futures_data)}")
            print(f"Listing: {listing_date_str}")
            
            # Get time series data
            time_series_data = self.get_topic_time_series(topic, listing_timestamp)
            
            if time_series_data:
                # Process the data
                coin_df = self._process_time_series_data(symbol, topic, time_series_data, listing_timestamp)
                if not coin_df.empty:
                    all_data.append(coin_df)
                    print(f"Downloaded {len(coin_df)} hourly data points for {symbol}")
                else:
                    print(f"No data points found for {symbol}")
            
            # Check if approaching daily limits
            if self.daily_request_count >= self.requests_per_day - 10:
                print(f"Approaching daily limit. Processed {i+1} coins.")
                break
                
            # Progress update
            if (i + 1) % 10 == 0:
                print(f"Completed {i+1}/{len(futures_data)} coins. Requests used: {self.daily_request_count}")
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            # Sort by symbol and hours from listing
            final_df = final_df.sort_values(['symbol', 'hours_from_listing'])
            return final_df
        else:
            return pd.DataFrame()
    
    def load_binance_futures_data(self, csv_path: str) -> List[Dict]:
        """Load Binance futures data from CSV file."""
        futures_data = []
        
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    futures_data.append({
                        'symbol': row['symbol'],
                        'onboardDate': row['onboardDate']
                    })
            
            print(f"Loaded {len(futures_data)} futures from {csv_path}")
            return futures_data
            
        except FileNotFoundError:
            print(f"File not found: {csv_path}")
            return []
        except Exception as e:
            print(f"Error loading futures data: {e}")
            return []
    
    def save_data(self, df: pd.DataFrame, output_path: str = None) -> str:
        """Save DataFrame to CSV with timestamp."""
        if df.empty:
            print("No data to save.")
            return ""
        
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"lunarcrush_binance_futures_{timestamp}.csv"
        
        df.to_csv(output_path, index=False)
        print(f"Data saved to {output_path}")
        print(f"Total records: {len(df)}")
        print(f"Coins processed: {df['symbol'].nunique()}")
        
        # Summary statistics
        print("\n=== Data Summary ===")
        print(f"Date range: {df['data_datetime'].min()} to {df['data_datetime'].max()}")
        print(f"Average data points per coin: {len(df) / df['symbol'].nunique():.1f}")
        
        return output_path


def main():
    # Configuration
    API_KEY = "your_lunarcrush_api_key_here"  # Replace with your actual API key
    
    # Paths
    futures_csv_path = Path(__file__).parent.parent / "DATA_STORAGE" / "project_future_scraper" / "new_binance_perpetual_futures.csv"
    output_dir = Path(__file__).parent.parent / "DATA_STORAGE" / "lunarcrush_data"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize downloader
    downloader = LunarCrushDownloader(API_KEY)
    
    # Load Binance futures data
    futures_data = downloader.load_binance_futures_data(str(futures_csv_path))
    
    if not futures_data:
        print("No futures data found. Please run the Binance discovery script first.")
        return
    
    # Download LunarCrush data
    df = downloader.download_binance_futures_data(futures_data, days_from_listing=14)
    
    if not df.empty:
        # Save data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"lunarcrush_binance_futures_{timestamp}.csv"
        downloader.save_data(df, str(output_path))
    else:
        print("No data downloaded.")


if __name__ == "__main__":
    main()
