import asyncio
import datetime
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.adapters.interactive_brokers.historical.client import HistoricInteractiveBrokersClient
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pathlib import Path
import pandas as pd


async def download__ib_historical_data(delete_temp_files=False):
    client = HistoricInteractiveBrokersClient(
        host="127.0.0.1",
        port=4002,
        client_id=1,
        log_level="INFO"
    )

    #connect
    await client.connect()
    await asyncio.sleep(2)  

    # Define contracts
    contracts = [
        IBContract(secType="STK", symbol="SPY", exchange="ARCA", primaryExchange="ARCA"),
    ]

    # Request instruments
    instruments = await client.request_instruments(contracts=contracts)

    # Save instruments only if not already present
    catalog = ParquetDataCatalog("C:/Users/Ferdi/Desktop/projectx/AlgorithmicTrader/data/DATA_STORAGE/data_catalog_wrangled")
    # Check if instruments already exist
    try:
        existing_instruments = catalog.read_instruments()
    except Exception:
        existing_instruments = []
    if not existing_instruments:
        catalog.write_data(instruments)

    start_date = datetime.datetime(2021, 1, 1, 9, 30)
    end_date = datetime.datetime(2024, 9, 1, 16, 30)
    bar_spec = "5-MINUTE-LAST"
    tz_name = "America/New_York"
    batch_months = 3
    current = start_date
    # Monatsweise Download in temp Ordner mit Rate-Limit
    temp_dir = Path("C:/Users/Ferdi/Desktop/projectx/AlgorithmicTrader/data/DATA_STORAGE/temp_ib_monthly")
    temp_dir.mkdir(parents=True, exist_ok=True)
    current = start_date
    request_count = 0
    while current < end_date:
        month_start = current
        # Bestimme Monatsende
        if current.month == 12:
            next_month = current.replace(year=current.year+1, month=1, day=1, hour=16, minute=30)
        else:
            next_month = current.replace(month=current.month+1, day=1, hour=16, minute=30)
        month_end = min(next_month, end_date)
        temp_file = temp_dir / f"SPY.ARCA-{bar_spec}-TEMP-{month_start.strftime('%Y%m%d')}-{month_end.strftime('%Y%m%d')}.parquet"
        print(f"Requesting bars: {month_start} to {month_end}")
        bars = await client.request_bars(
            bar_specifications=[bar_spec],
            start_date_time=month_start,
            end_date_time=month_end,
            tz_name=tz_name,
            contracts=contracts,
            use_rth=False,
        )
        request_count += 1
        if bars:
            if hasattr(bars[0], "to_dict"):
                df = pd.DataFrame([type(bar).to_dict(bar) for bar in bars])
            else:
                df = pd.DataFrame([{k: getattr(bar, k) for k in dir(bar) if not k.startswith('_') and not callable(getattr(bar, k))} for bar in bars])
            df.to_parquet(temp_file)
            print(f"Downloaded {len(bars)} bars for {temp_file.name}.")
        else:
            print(f"Keine Bars im Monat {month_start.strftime('%Y-%m')} wird übersprungen.")
        if request_count % 60 == 0:
            print("API-Limit erreicht, pausiere 10 Minuten...")
            await asyncio.sleep(600)
        current = month_end

    # Nach Download: Alle Monatsdateien einlesen, sortieren, Duplikate entfernen, mergen und als eine Datei speichern
    monthly_files = sorted(temp_dir.glob("*.parquet"))
    merged_dfs = []
    last_ts_event = None
    for f in monthly_files:
        try:
            df = pd.read_parquet(f)
            if last_ts_event is not None:
                df = df[df["ts_event"] > last_ts_event]
            if not df.empty:
                last_ts_event = df["ts_event"].max()
                merged_dfs.append(df)
        except Exception:
            continue
    if not merged_dfs:
        print("Keine gültigen Bars im gesamten Zeitraum, wird übersprungen.")
        return
    merged_df = pd.concat(merged_dfs, ignore_index=True)
    merged_df = merged_df.drop_duplicates(subset=["ts_event"]).sort_values("ts_event")
    # Zielordner und Dateinamen nach bar_spec und Zeitintervall
    bar_folder_name = f"SPY.ARCA-{bar_spec}-EXTERNAL"
    # Zielpfad absolut zum Projektordner, nicht relativ zum download-Ordner
    target_dir = Path(__file__).parent.parent / "DATA_STORAGE" / "data_catalog_wrangled" / "data" / "bar" / bar_folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    # Ermittle Start- und Endzeit aus den Daten
    start_ts = pd.to_datetime(merged_df["ts_event"].iloc[0], unit="ns").strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    end_ts = pd.to_datetime(merged_df["ts_event"].iloc[-1], unit="ns").strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    file_name = f"{start_ts}_{end_ts}.parquet"
    file_path = target_dir / file_name
    merged_df.to_parquet(file_path)
    print(f"Gemergte Datei gespeichert: {file_path} mit {len(merged_df)} Bars.")

    # Optional: Lösche temporäre Dateien nach Mergen
    if delete_temp_files:
        for f in monthly_files:
            try:
                f.unlink()
            except Exception as e:
                print(f"Fehler beim Löschen von {f}: {e}")
        try:
            temp_dir.rmdir()
        except Exception:
            pass
        print("Temporäre Dateien wurden gelöscht.")
