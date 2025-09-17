import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()
API_KEY = os.getenv("LUNARCRUSH_API_KEY")
START_DATE = "2025-08-18"
END_DATE = "2025-08-30"

# Create storage directory
STORAGE_PATH = Path(__file__).resolve().parents[2] / "DATA_STORAGE"
STORAGE_PATH.mkdir(parents=True, exist_ok=True)

def get_cream_custom_range():
    symbol = "CREAM"
    start_timestamp = int(datetime.strptime(START_DATE, '%Y-%m-%d').timestamp())
    end_timestamp = int(datetime.strptime(END_DATE, '%Y-%m-%d').timestamp())
    # Using coins time-series endpoint (full Individual plan access)
    url = f"https://lunarcrush.com/api4/public/coins/{symbol}/time-series/v2"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {
        "bucket": "hour",
        "start": start_timestamp,
        "end": end_timestamp
    }
    
    response = requests.get(url, headers=headers, params=params)

    print("Status Code:", response.status_code)

    try:
        data = response.json()
        # Pretty print JSON
        import json
        print(json.dumps(data, indent=2)[:2000])  # nur die ersten 2000 Zeichen, sonst wird’s zu viel
    except Exception as e:
        print("Response text (kein JSON):")
        print(response.text)
        print("Error beim JSON-Parsing:", e)

    
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