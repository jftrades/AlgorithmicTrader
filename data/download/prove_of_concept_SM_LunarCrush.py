import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("LUNARCRUSH_API_KEY")

def get_current_alpaca():
    url = "https://lunarcrush.com/api4/public/topic/alpaca/v1"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        config = data.get('config', {})
        topic_data = data.get('data', {})
        
        current = {
            'timestamp': int(datetime.now().timestamp()),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'topic': config.get('topic', 'alpaca'),
            'name': config.get('name', ''),
            'symbol': config.get('symbol', ''),
            'interactions_24h': topic_data.get('interactions_24h', 0),
            'num_posts': topic_data.get('num_posts', 0),
            'num_contributors': topic_data.get('num_contributors', 0),
            'topic_rank': topic_data.get('topic_rank', 0)
        }
        
        df = pd.DataFrame([current])
        df.to_csv('alpaca_current.csv', index=False)
        return df
    else:
        print(f"Error: {response.status_code}")
        return None

if API_KEY:
    get_current_alpaca()
else:
    print("Set LUNARCRUSH_API_KEY in .env file")