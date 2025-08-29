"""
Discovery-Skript für neu gelistete Binance Perpetual Futures der letzten 12 Monate.
Speichert die Instrument-IDs und Listing-Daten.
"""
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

def get_new_binance_perpetual_futures(months_back):
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
    # Print the last 10 discovered futures
    print("[INFO] Die letzten 10 neu gelisteten Perpetual Futures:")
    for fut in new_futures[-10:]:
        print(fut)
    return new_futures

if __name__ == "__main__":
    print("start")
    futures = get_new_binance_perpetual_futures(months_back=12)
    # Nur Symbole mit USDT am Ende behalten
    futures = [f for f in futures if f["symbol"].endswith("USDT")]
    # Speichern als CSV
    import csv
    # Zielverzeichnis setzen
    target_dir = Path(__file__).parent.parent / "DATA_STORAGE" / "project_future_scraper"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "new_binance_perpetual_futures.csv"
    print("start")
    with open(target_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "onboardDate"])
        writer.writeheader()
        writer.writerows(futures)
    print(f"[INFO] {len(futures)} neue Perpetual Futures gefunden und gespeichert: {target_path}")
    print("end")