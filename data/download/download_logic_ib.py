# JUHUU RAPHAEL GOAT
import asyncio
import datetime
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.adapters.interactive_brokers.historical.client import HistoricInteractiveBrokersClient
from nautilus_trader.persistence.catalog import ParquetDataCatalog

async def download__ib_historical_data():
    client = HistoricInteractiveBrokersClient(
        host="127.0.0.1",
        port=4002,
        client_id=1,
        log_level="INFO"
    )
    await client.connect()
    await asyncio.sleep(2)

    contracts = [IBContract(secType="STK", symbol="SPY", exchange="ARCA", primaryExchange="ARCA")]
    instruments = await client.request_instruments(contracts=contracts)
    catalog = ParquetDataCatalog("C:/Users/Ferdi/Desktop/projectx/AlgorithmicTrader/data/DATA_STORAGE/data_catalog_wrangled")
    try:
        existing_instruments = catalog.read_instruments()
    except Exception:
        existing_instruments = []
    if not existing_instruments:
        catalog.write_data(instruments)

    start_date = datetime.datetime(2020, 6, 1, 9, 30)
    end_date = datetime.datetime(2021, 1, 1, 16, 30)
    bar_spec = "5-MINUTE-LAST"
    tz_name = "America/New_York"
    current = start_date
    last_bar_ts = None

    while current < end_date:
        month_start = current
        if current.month == 12:
            next_month = current.replace(year=current.year+1, month=1, day=1, hour=16, minute=30)
        else:
            next_month = current.replace(month=current.month+1, day=1, hour=16, minute=30)
        month_end = min(next_month, end_date)

        bars = await client.request_bars(
            bar_specifications=[bar_spec],
            start_date_time=month_start,
            end_date_time=month_end,
            tz_name=tz_name,
            contracts=contracts,
            use_rth=False,
        )

        # Filter: Nur Bars mit ts_event > last_bar_ts
        if bars:
            if last_bar_ts is not None:
                bars = [bar for bar in bars if bar.ts_event > last_bar_ts]
            if bars:
                last_bar_ts = bars[-1].ts_event
                catalog.write_data(bars)
                print(f"{len(bars)} Bars gespeichert bis {month_end}.")
            else:
                print(f"Keine neuen Bars im Monat {month_start.strftime('%Y-%m')}.")
        else:
            print(f"Keine Bars im Monat {month_start.strftime('%Y-%m')}.")
        current = month_end

    print("Download und Speicherung abgeschlossen.")