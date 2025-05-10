from binance_historical_data import BinanceDataDumper
import datetime
import os

def main():
    # Speicherpfad sicherstellen
    os.makedirs("./DATA_STORAGE", exist_ok=True)

    # Initialisiere den DataDumper
    data_dumper = BinanceDataDumper(
        path_dir_where_to_dump = "./DATA_STORAGE",  # Verzeichnis zum Speichern der Daten
        asset_class="spot",                         # 'spot' für Spot-Markt
        data_type="klines",                         # 'klines' für Kerzendaten
        data_frequency="15m"                        # 15-Minuten-Intervalle
    )

    # Definiere den Zeitraum
    start_date = datetime.date(2022, 7, 8)  # Startdatum
    end_date = datetime.date(2023, 2, 2)    # Enddatum

    # Lade die Daten herunter
    data_dumper.dump_data(
        tickers=["BTCUSDT"],
        date_start=start_date,
        date_end=end_date
    )

if __name__ == "__main__":
    main()
