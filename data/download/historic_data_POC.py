import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()
API_KEY = os.getenv("LUNARCRUSH_API_KEY")
START_DATE = "2020-09-18"
END_DATE = "2020-09-30"

# Create storage directory
STORAGE_PATH = Path(r"C:\Users\Ferdi\Desktop\projectx\AlgorithmicTrader\data\DATA_STORAGE\lunar_crush")
STORAGE_PATH.mkdir(parents=True, exist_ok=True)

def get_cream_custom_range():
    start_timestamp = int(datetime.strptime(START_DATE, '%Y-%m-%d').timestamp())
    end_timestamp = int(datetime.strptime(END_DATE, '%Y-%m-%d').timestamp())
    # Using coins time-series endpoint (full Individual plan access)
    url = "https://lunarcrush.com/api4/public/coins/cream/time-series/v2"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {
        "bucket": "hour",
        "start": start_timestamp,
        "end": end_timestamp
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        records = []
        
        for point in data.get('data', []):
            records.append({
                'timestamp': point.get('time'),
                'datetime': datetime.fromtimestamp(point.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                'contributors_active': point.get('contributors_active', 0),  # Active contributors
                'contributors_created': point.get('contributors_created', 0),  # New contributors
                'interactions': point.get('interactions', 0),  # Social interactions
                'posts_active': point.get('posts_active', 0),  # Active posts
                'posts_created': point.get('posts_created', 0),  # New posts created
                'sentiment': point.get('sentiment', 0),  # Sentiment score
                # Note: Financial data (price, volume_24h, market_cap, galaxy_score) not available for CREAM
            })
        
        df = pd.DataFrame(records)
        output_file = STORAGE_PATH / f'cream_{START_DATE}_to_{END_DATE}.csv'
        df.to_csv(output_file, index=False)
        print(f"✓ Downloaded {len(records)} hours of CREAM data from {START_DATE} to {END_DATE}")
        print(f"✓ Saved to: {output_file}")
        return df
    else:
        print(f"Error: {response.status_code}")
        return None

if API_KEY:
    get_cream_custom_range()
else:
    print("Set LUNARCRUSH_API_KEY in .env file")