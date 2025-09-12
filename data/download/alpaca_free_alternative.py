"""
Simple ALPACA data fetcher using CoinGecko's FREE API
Gets current price + timestamp (no subscription needed)
"""
import requests
import pandas as pd
from datetime import datetime

def get_alpaca_coingecko():
    """Get current ALPACA data from CoinGecko - completely free"""
    
    # CoinGecko API - free, no auth needed
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        'ids': 'alpaca-finance',  # ALPACA coin ID on CoinGecko
        'vs_currencies': 'usd',
        'include_market_cap': 'true',
        'include_24hr_vol': 'true',
        'include_24hr_change': 'true'
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        
        if 'alpaca-finance' in data:
            alpaca = data['alpaca-finance']
            
            current = {
                'timestamp': int(datetime.now().timestamp()),
                'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'price': alpaca.get('usd', 0),
                'market_cap': alpaca.get('usd_market_cap', 0),
                'volume_24h': alpaca.get('usd_24h_vol', 0),
                'price_change_24h': alpaca.get('usd_24h_change', 0)
            }
            
            # Save to CSV
            df = pd.DataFrame([current])
            df.to_csv('alpaca_coingecko.csv', index=False)
            
            print("ALPACA Current Data (CoinGecko):")
            print(f"Time: {current['datetime']}")
            print(f"Price: ${current['price']:.4f}")
            print(f"24h Change: {current['price_change_24h']:.2f}%")
            print(f"Volume 24h: ${current['volume_24h']:,.0f}")
            print(f"Market Cap: ${current['market_cap']:,.0f}")
            print(f"✓ Saved to: alpaca_coingecko.csv")
            
            return df
        else:
            print("ALPACA not found in CoinGecko response")
            return None
    else:
        print(f"CoinGecko API Error: {response.status_code}")
        return None

if __name__ == "__main__":
    print("=== Free ALPACA Data (CoinGecko) ===")
    get_alpaca_coingecko()
