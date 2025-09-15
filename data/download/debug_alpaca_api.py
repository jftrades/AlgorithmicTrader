import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("LUNARCRUSH_API_KEY")

def debug_alpaca_response():
    """Debug what the API actually returns"""
    url = "https://lunarcrush.com/api4/public/coins/alpaca/time-series/v2"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {
        "bucket": "hour",
        "interval": "1w"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n=== Full API Response Structure ===")
        print(json.dumps(data, indent=2)[:2000] + "...")  # First 2000 chars
        
        if 'data' in data and len(data['data']) > 0:
            print(f"\n=== First Data Point Keys ===")
            first_point = data['data'][0]
            print(f"Available keys: {list(first_point.keys())}")
            
            print(f"\n=== First Data Point Values ===")
            for key, value in first_point.items():
                print(f"{key}: {value}")
                
            # Check a few more data points
            print(f"\n=== Sample of other data points ===")
            for i in range(min(3, len(data['data']))):
                point = data['data'][i]
                print(f"Point {i}: volume_24h={point.get('volume_24h', 'MISSING')}, market_cap={point.get('market_cap', 'MISSING')}, close={point.get('close', 'MISSING')}")
        else:
            print("No data points found")
    else:
        print(f"Error Response: {response.text}")

if __name__ == "__main__":
    debug_alpaca_response()
