import asyncio
import datetime
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.adapters.interactive_brokers.historical.client import HistoricInteractiveBrokersClient
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pathlib import Path


async def download__ib_historical_data():
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
        IBContract(secType="STK", symbol="SPY", exchange="SMART", primaryExchange="ARCA"),
    ]

    # Request instruments
    instruments = await client.request_instruments(contracts=contracts)

    # Request historical bars
    bars = await client.request_bars(
        bar_specifications=["5-MINUTE-LAST"],
        start_date_time=datetime.datetime(2018, 1, 1, 9, 30),
        end_date_time=datetime.datetime(2025, 1, 1, 16, 30),
        tz_name="America/New_York",
        contracts=contracts,
        use_rth=False,
    )

    # Save to catalog
    catalog = ParquetDataCatalog("C:/Users/Ferdi/Desktop/projectx/AlgorithmicTrader/data/DATA_STORAGE/data_catalog_wrangled")
    catalog.write_data(instruments)
    catalog.write_data(bars)

    print(f"Downloaded {len(instruments)} instruments")
    print(f"Downloaded {len(bars)} bars")
