import asyncio
from download_logic_ib import download__ib_historical_data

if __name__ == "__main__":
    asyncio.run(download__ib_historical_data())