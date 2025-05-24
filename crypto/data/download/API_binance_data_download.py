#lädt je nach Parameter eine CSV dementsprechend die Daten direkt in Krypto_Daten
#ich habe das skript von gemini schon gekürzt, können wir aber gerne auch noch mal durchgehen
#habe gesehen, dass sie bei ema crossing... auch auf eine CSV zugegriffen haben -> so müsste ein fiexer weg sein um OHLC nach belieben zu laden 


from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta
import os
import time 


API_KEY = ""  # Optional: Trage hier deinen API Key ein, wenn du höhere Limits brauchst
API_SECRET = "" # Optional: Trage hier deinen API Secret ein
SYMBOL = "BTCUSDT"
INTERVAL_STRING = "15m"     # Binance API String: "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"
START_DATE_STR = "2023-01-01"
DAYS_TO_FETCH = 45         # Anzahl der Tage ab START_DATE_STR
REQUEST_TIMEOUT_SECONDS = 30
OUTPUT_BASE_FOLDER = "crypto" 
# -----------------------------------------

def get_binance_interval_timedelta(interval_string):
    """Konvertiert einen Binance Intervall-String in ein timedelta-Objekt."""
    value = int(interval_string[:-1])
    unit = interval_string[-1].lower()
    if unit == 'm': return timedelta(minutes=value)
    if unit == 'h': return timedelta(hours=value)
    if unit == 'd': return timedelta(days=value)
    if unit == 'w': return timedelta(weeks=value)
    if unit == 'M': return timedelta(days=value * 30) 
    raise ValueError(f"Unbekanntes oder nicht unterstütztes Intervall für timedelta: {interval_string}")

# --- Setup ---
client = Client(API_KEY, API_SECRET, requests_params={'timeout': REQUEST_TIMEOUT_SECONDS})
os.makedirs(OUTPUT_BASE_FOLDER, exist_ok=True)

# Zieldatei dynamisch erstellen
start_dt = datetime.fromisoformat(START_DATE_STR)
end_dt_approx = start_dt + timedelta(days=DAYS_TO_FETCH)
filename = f"{SYMBOL}_{INTERVAL_STRING.upper()}_{start_dt.strftime('%Y%m%d')}_to_{end_dt_approx.strftime('%Y%m%d')}.csv"
full_output_path = os.path.join(OUTPUT_BASE_FOLDER, filename)

# --- Datenabruf ---
all_klines_data = []
current_fetch_start_dt = start_dt
single_interval_delta = get_binance_interval_timedelta(INTERVAL_STRING)

print(f"Starte Download für {SYMBOL} ({INTERVAL_STRING}) von {start_dt.strftime('%Y-%m-%d')} für {DAYS_TO_FETCH} Tage.")
print(f"Speichere Daten in: {full_output_path}")

try:
    while current_fetch_start_dt < end_dt_approx:
        start_ts_ms_str = str(int(current_fetch_start_dt.timestamp() * 1000))
        
        print(f"  Rufe Daten ab ab: {current_fetch_start_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        klines = client.get_historical_klines(SYMBOL, INTERVAL_STRING, start_ts_ms_str, limit=1000)
        
        if not klines:
            print(f"  Keine weiteren Daten ab {current_fetch_start_dt.strftime('%Y-%m-%d %H:%M:%S')} gefunden. Download beendet.")
            break
            
        all_klines_data.extend(klines)
        
        # Nächste Startzeit ist die Open-Time der letzten Kerze + 1 Intervall
        # Dies handhabt auch den Fall, dass weniger als `limit` Kerzen zurückkommen.
        last_kline_open_time_ms = klines[-1][0]
        current_fetch_start_dt = datetime.fromtimestamp(last_kline_open_time_ms / 1000.0) + single_interval_delta
        
        # Kurze Pause, um API-Limits nicht zu überschreiten (optional, aber gute Praxis)
        time.sleep(0.2) # 200 Millisekunden

except requests.exceptions.ReadTimeout as e_timeout: # Spezifischer Timeout-Error
    print(f"TIMEOUT beim Abrufen der Daten: {e_timeout}.")
    print(f"Versuche, den REQUEST_TIMEOUT_SECONDS ({REQUEST_TIMEOUT_SECONDS}s) zu erhöhen oder überprüfe deine Internetverbindung.")
except Exception as e: # Alle anderen Fehler
    print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")

# --- Datenverarbeitung und Speicherung ---
if all_klines_data:
    df = pd.DataFrame(all_klines_data, columns=[
        "kline_open_time", "open", "high", "low", "close", "volume", 
        "kline_close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["kline_open_time"], unit='ms', utc=True) # Wichtig: Als UTC interpretieren
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    
    df.set_index("timestamp", inplace=True)

    df.to_csv(full_output_path)
    print(f"\nDaten erfolgreich in '{full_output_path}' gespeichert. {len(df)} Zeilen.")
    print("Die ersten 3 Zeilen der Daten:")
    print(df.head(3))
else:
    print("\nKeine Daten heruntergeladen.")