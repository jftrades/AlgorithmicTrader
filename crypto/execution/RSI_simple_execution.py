
# Standard Library Importe
import sys
import time
from pathlib import Path
from decimal import Decimal 
import pandas as pd


# Nautilus Kern Importe (für Backtest eigentlich immer hinzufügen)
from nautilus_trader.core.nautilus_pyo3 import InstrumentId, Symbol, Venue
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USDT, BTC
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig,BacktestRunConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.results import BacktestResult



# Nautilus Strategie spezifische Importe
from nautilus_trader.trading.config import ImportableStrategyConfig
from nautilus_trader.persistence.catalog import ParquetDataCatalog

# FÜGE HIER EIN (nach Zeile 25):
print("=" * 60)
print("DATENCHECK:")
print("=" * 60)

catalogPath = str(Path(__file__).resolve().parent.parent / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

catalog = ParquetDataCatalog(catalogPath)
print("Verfügbare Instrumente:", catalog.instruments())
# KORREKTE METHODE FÜR BAR-DATEN:
try:
    # Prüfe direkt mit bars() Methode
    test_instrument_id_str = "BTCUSDT-PERP.BINANCE"
    test_bar_type_str = "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL"
    
    available_data = catalog.bars(
        instrument_ids=[test_instrument_id_str],
        bar_types=[test_bar_type_str]
    )
    
    if available_data is not None and len(available_data) > 0:
        print("✅ DATEN GEFUNDEN!")
        print("Datenbereich:", available_data.index.min(), "bis", available_data.index.max())
        print("Anzahl Bars:", len(available_data))
        
        # Prüfe ob 2021 Daten verfügbar sind
        data_2021 = available_data.loc['2021-01-01':'2021-03-01']
        if len(data_2021) > 0:
            print("✅ 2021 DATEN VERFÜGBAR:", len(data_2021), "Bars")
        else:
            print("❌ KEINE 2021 DATEN im gewünschten Zeitraum!")
    else:
        print("❌ KEINE DATEN für", test_instrument_id_str, "gefunden!")
        
        # Versuche alternative Bar-Typen
        alternative_bar_types = [
            "BTCUSDT.BINANCE-5-MINUTE-LAST-EXTERNAL",  # SPOT statt PERP
            "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL",  # 1min statt 5min
        ]
        
        for alt_bar_type in alternative_bar_types:
            try:
                alt_data = catalog.bars(bar_types=[alt_bar_type])
                if alt_data is not None and len(alt_data) > 0:
                    print(f"✅ ALTERNATIVE DATEN GEFUNDEN: {alt_bar_type}")
                    break
            except:
                continue
                
except Exception as e:
    print("FEHLER beim Laden der Daten:", e)

print("=" * 60)

# Hier die gleichen Parameter wie aus strategy aber halt anpassen
symbol = Symbol("BTCUSDT-PERP")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT-PERP.BINANCE"
bar_type_str_for_configs = "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL"
trade_size = Decimal("0.001")
rsi_period = 14
rsi_overbought = 0.65
rsi_oversold = 0.45
close_positions_on_stop = True

start_date = "2021-01-01T00:00:00Z"
end_date = "2021-03-01T00:00:00Z"

# Strategien-Ordner liegt parallel zu AlgorithmicTrader
STRATEGY_PATH = Path(__file__).resolve().parents[1] / "strategies"
if str(STRATEGY_PATH) not in sys.path:
    sys.path.insert(0, str(STRATEGY_PATH))


# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar",
    catalog_path=catalogPath,
    bar_types=[bar_type_str_for_configs],
    start_time=pd.Timestamp("2021-01-01T00:00:00", tz="UTC"),
    end_time=pd.Timestamp("2021-03-01T00:00:00", tz="UTC")
)

# VenueConfig - FUTURES/MARGIN TRADING KORRIGIERT
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING", 
    account_type="MARGIN",
    base_currency="USDT",  # Base Currency für Futures
    starting_balances=["100000 USDT"],  # Nur USDT für Futures
    default_leverage=1.0,  # REDUZIERE Leverage auf 1x
    leverages={"BTCUSDT-PERP.BINANCE": 1.0}  # Keine Leverage für Tests
)


# StrategyConfig - IMMER anpassen!!
strategy_config = ImportableStrategyConfig(
    strategy_path = "RSI_simple_strategy:RSISimpleStrategy",
    config_path = "RSI_simple_strategy:RSISimpleStrategyConfig",

    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": "0.0010", # Trade Size in BTC
        #hier kommen jetzt die Strategie spezifischen Parameter
        "rsi_period": 14,
        "rsi_overbought": 0.65, 
        "rsi_oversold": 0.35,
        "close_positions_on_stop": True # Positionen werden beim Stop der Strategie geschlossen

    }
)

# EngineConfig -> welche Strategien bei diesem Backtest laufen sollen
engine_config = BacktestEngineConfig(strategies=[strategy_config])

# RunConfig -> hier wird data, venues und engine zusammengeführt
run_config = BacktestRunConfig(
    data=[data_config], 
    venues=[venue_config], 
    engine=engine_config,
    start=pd.Timestamp("2021-01-01T00:00:00", tz="UTC"),  # <-- pd.Timestamp
    end=pd.Timestamp("2021-03-01T00:00:00", tz="UTC")     # <-- pd.Timestamp
)

# Launch Node #-> startet den eigentlichen Backtest mit node.run()try:
try:
    node = BacktestNode(configs=[run_config])
    print(f"INFO: Backtest: Starte Backtest-Node...")
    results = node.run()
except Exception as e:
    print(f"FATAL: Backtest: Ein Fehler ist im Backtest-Node aufgetreten: {e}")
    import traceback
    traceback.print_exc()

# Ergebnisse auswerten:
def print_backtest_summary(result: BacktestResult):
    print("=" * 60)
    print(f"Backtest Run-ID: {result.run_id}")
    print(f"Zeitraum: {result.backtest_start} bis {result.backtest_end}")
    print(f"Dauer (real): {result.elapsed_time:.2f}s")
    print(f"Iterationen: {result.iterations}")
    print(f"Events: {result.total_events}, Orders: {result.total_orders}, Positionen: {result.total_positions}")
    print("=" * 60)
    print("Performance (PnL pro Währung):")
    for currency, metrics in result.stats_pnls.items():
        print(f"\n🔸 {currency}")
        for key, val in metrics.items():
            print(f"  {key.replace('_', ' ').title()}: {val:.4f}")
    print("\n Return Statistics:")
    for key, val in result.stats_returns.items():
        print(f"  {key.replace('_', ' ').title()}: {val:.4f}")
    print("=" * 60)

if results:
    print_backtest_summary(results[0])
else:
    print("No results to display.")