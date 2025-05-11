#diese Skript funktioniert noch nicht, weil das mit der editable version noch nicht geklärt ist - vorerst bitte ignorieren



#hier drinnen werde ich jetzt nachdem ich weiss wie importiert wird, die crypto_ema_cross_ethusdt_trade_ticks.py umbauen wie folgt:
#anstatt 1D ETHUSDT Daten 15min BTCUSDT Binance Daten
#anstatt den bisherigen verschiedene ParameterKombinationen testen und so an in-sample-window Analyse gewöhnen

import time
from decimal import Decimal
import pandas as pd
import os

# Nautilus Trader Imports (gleich geblieben)
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP, EMACrossTWAPConfig
from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import TraderId, Venue, InstrumentId, Symbol
from nautilus_trader.model.instrument import Instrument
from nautilus_trader.model.objects import Money, Quantity

# --- DATENLADEFUNKTION (optimiert und bestätigt für Wrangler-erstellte Parquet-Dateien) ---
def load_bars_from_wrangled_parquet(
    file_path: str,
    # Die folgenden Parameter werden aus der Hauptkonfiguration abgeleitet
    instrument_id_str_for_bar_type: str, # z.B. "BTCUSDT.BINANCE"
    bar_spec_str_for_bar_type: str,      # z.B. "15-MINUTE-LAST-EXTERNAL"
    # Spaltennamen, wie sie typischerweise vom BarDataWranglerV2 + ParquetDataCatalog geschrieben werden
    ts_col: str = "ts_event",       # Ist bereits Nanosekunden-Integer (uint64)
    open_col: str = "open",         # Ist 'object' (serialisiertes Decimal)
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
    base_asset_precision: int = BTC.precision, # Für Quantity-Objekt des Volumens
) -> list[Bar]:
    """Lädt Klines aus einer Nautilus-Wrangler-erstellten Parquet-Datei."""
    abs_file_path = os.path.abspath(file_path)
    if not os.path.exists(abs_file_path):
        raise FileNotFoundError(f"Parquet-Datei nicht gefunden: {file_path} (aufgelöst zu: {abs_file_path})")

    df = pd.read_parquet(abs_file_path)
    if df.empty: raise ValueError(f"Parquet-Datei {abs_file_path} ist leer.")

    # Timestamp ist bereits 'ts_event' und in Nanosekunden (uint64)
    # Sortieren und Duplikate entfernen ist gut, falls die Datei es nicht garantiert
    df_sorted_unique = df.sort_values(by=ts_col).drop_duplicates(subset=[ts_col], keep="first")

    # BarType muss exakt dem entsprechen, was in der Datei gespeichert ist
    # (und was im Transformationsskript als BAR_TYPE verwendet wurde)
    full_bar_type_str = f"{instrument_id_str_for_bar_type}-{bar_spec_str_for_bar_type}"
    bar_type_obj = BarType.from_str(full_bar_type_str)

    bars = [ Bar( bar_type=bar_type_obj,
                 ts_event=r[ts_col],       # Direkt verwenden, da uint64 Nanosekunden
                 ts_init=r.get("ts_init", r[ts_col]), # Nutze ts_init falls vorhanden, sonst ts_event
                 open=Decimal(r[open_col]), # Direktes Umwandeln des 'object' zu Decimal
                 high=Decimal(r[high_col]),
                 low=Decimal(r[low_col]),
                 close=Decimal(r[close_col]),
                 volume=Quantity(Decimal(r[volume_col]), base_asset_precision))
             for _, r in df_sorted_unique.iterrows() ]

    if not bars: raise ValueError("Keine Bars erstellt.")
    print(f"{len(bars)} Bars geladen. Von {pd.to_datetime(bars[0].ts_event, unit='ns')} bis {pd.to_datetime(bars[-1].ts_event, unit='ns')}")
    return bars

# --- HAUPTSKRIPT ---
if __name__ == "__main__":
    # === KONFIGURATION AM ANFANG ===
    # Relativer Pfad zur Parquet-Datei (part-0.parquet)
    PARQUET_FILE_PATH = "DATA_STORAGE/data_catalog_wrangled/data/bar/BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL/part-0.parquet"

    # Spaltennamen in der Parquet-Datei (bestätigt durch inspect_parquet.py und Transformationsskript)
    # Die Ladefunktion verwendet diese jetzt als Standard, aber zur Klarheit hier aufgeführt:
    # PARQUET_TS_COL = "ts_event"
    # PARQUET_OPEN_COL = "open" ... etc.

    # Instrument- und Handelsplatzdetails
    INSTRUMENT_SYMBOL = "BTCUSDT"
    VENUE_NAME = "BINANCE"
    # Der Bar-Spezifikations-Teil des BarType, wie im Transformationsskript und Pfad verwendet
    BAR_SPECIFICATION_SUFFIX = "15-MINUTE-LAST-EXTERNAL"
    BASE_CURRENCY = BTC
    QUOTE_CURRENCY = USDT
    INSTRUMENT_PRICE_PRECISION = 2
    INSTRUMENT_SIZE_PRECISION = 4 # Angepasst an dein Transformationsskript

    # Strategieparameter
    STRATEGY_TRADE_SIZE = Decimal("0.01")
    FAST_EMA_PERIOD = 10
    SLOW_EMA_PERIOD = 20
    TWAP_HORIZON_SECS = 60.0
    TWAP_INTERVAL_SECS = 10.0

    # Startkapital
    STARTING_USDT = 1_000_000.0
    STARTING_BASE_ASSET = 1.0
    # === ENDE KONFIGURATION ===

    # Abgeleitete Konfigurationen für Nautilus
    # Dies bildet den ersten Teil des BarType: "BTCUSDT.BINANCE"
    instrument_venue_id_str = f"{INSTRUMENT_SYMBOL}.{VENUE_NAME}"
    venue = Venue(VENUE_NAME)
    # Der vollständige BarType String für die Strategie und Dateninterpretation
    # Wird zu "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL"
    full_strategy_bar_type_str = f"{instrument_venue_id_str}-{BAR_SPECIFICATION_SUFFIX}"


    # Backtest Engine Initialisierung (gleich geblieben)
    engine = BacktestEngine(config=BacktestEngineConfig(
        trader_id=TraderId("BACKTESTER-001"),
        logging=LoggingConfig(log_level="INFO", log_colors=True, use_pyo3=False),
    ))

    # Venue und Account Setup (gleich geblieben)
    engine.add_venue(
        venue=venue, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(STARTING_USDT, QUOTE_CURRENCY), Money(STARTING_BASE_ASSET, BASE_CURRENCY)],
        book_type=BookType.NONE, trade_execution=True,
    )

    # Instrument Setup (gleich geblieben, SIZE_PRECISION angepasst)
    instrument = Instrument(
        venue=venue, id=InstrumentId.from_str(instrument_venue_id_str), symbol=Symbol(INSTRUMENT_SYMBOL),
        base_asset=BASE_CURRENCY, quote_asset=QUOTE_CURRENCY,
        price_precision=INSTRUMENT_PRICE_PRECISION, size_precision=INSTRUMENT_SIZE_PRECISION,
        min_size=Quantity(Decimal(f"1e-{INSTRUMENT_SIZE_PRECISION}"), INSTRUMENT_SIZE_PRECISION),
        min_price_tick=Decimal(f"1e-{INSTRUMENT_PRICE_PRECISION}"),
        maker_fee=Decimal("0.001"), taker_fee=Decimal("0.001"),
    )
    engine.add_instrument(instrument)

    # Daten laden und hinzufügen
    try:
        print(f"Lade Daten aus relativem Pfad: {PARQUET_FILE_PATH}")
        bars_data = load_bars_from_wrangled_parquet(
            file_path=PARQUET_FILE_PATH,
            instrument_id_str_for_bar_type=instrument_venue_id_str, # "BTCUSDT.BINANCE"
            bar_spec_str_for_bar_type=BAR_SPECIFICATION_SUFFIX,   # "15-MINUTE-LAST-EXTERNAL"
            # Spaltennamen-Parameter werden nicht mehr benötigt, da die Funktion Defaults hat,
            # die zu Wrangler-erzeugten Dateien passen.
            base_asset_precision=instrument.base_asset.precision, # Für Volume Quantity
        )
        engine.add_data(bars_data)
    except Exception as e:
        print(f"Kritischer Fehler beim Laden der Daten: {e}")
        # import traceback; traceback.print_exc() # Für mehr Debug-Infos
        exit(1)

    # Strategie und Execution Algorithmus Setup
    strategy_config = EMACrossTWAPConfig(
        instrument_id=instrument.id,
        bar_type=BarType.from_str(full_strategy_bar_type_str), # Muss exakt passen!
        trade_size=STRATEGY_TRADE_SIZE, fast_ema_period=FAST_EMA_PERIOD,
        slow_ema_period=SLOW_EMA_PERIOD, twap_horizon_secs=TWAP_HORIZON_SECS,
        twap_interval_secs=TWAP_INTERVAL_SECS,
    )
    engine.add_strategy(EMACrossTWAP(config=strategy_config))
    engine.add_exec_algorithm(TWAPExecAlgorithm()) # Gleich geblieben

    # Backtest starten (gleich geblieben)
    print(f"Starte Backtest für {instrument.id} mit BarType {full_strategy_bar_type_str}...")
    start_time = time.time()
    engine.run()
    print(f"Backtest Dauer: {time.time() - start_time:.2f} Sekunden.")

    # Ergebnisse ausgeben (gleich geblieben)
    with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 1000):
        print(f"\n--- Account Report ({QUOTE_CURRENCY.code}) ---")
        print(engine.trader.generate_account_report(venue, currency=QUOTE_CURRENCY))
        print("\n--- Order Fills Report ---")
        print(engine.trader.generate_order_fills_report())
        print("\n--- Positions Report ---")
        print(engine.trader.generate_positions_report())

    engine.dispose() # Gleich geblieben
    print("Skript erfolgreich beendet.") 
