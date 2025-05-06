# preset_nautilus_imports.py (Finale saubere Version mit Erfolgsprint)

try:
    # --- Essentielle Nautilus Trader Importe ---
    import nautilus_trader 

    from nautilus_trader.model.currencies import ETH, USD
    from nautilus_trader.core import datetime as nt_core_datetime
    from nautilus_trader.model.data import Bar, BarType, BarSpecification
    from nautilus_trader.model.objects import Price, Quantity, Money
    from nautilus_trader.model.enums import OrderSide, OrderType
    from nautilus_trader.model.identifiers import InstrumentId, Venue, Symbol
    
    # --- Optionale, häufig genutzte Importe (bei Bedarf einkommentieren und erweitern) ---
    # from nautilus_trader.model.instruments import Instrument
    # from nautilus_trader.model.orders import MarketOrder, LimitOrder 
    # from nautilus_trader.core.engine import BacktestEngine, BacktestEngineConfig
    # from nautilus_trader.test_kit.providers import TestInstrumentProvider
    # from nautilus_trader.examples.strategies.ema_cross import EMACross, EMACrossConfig
    
    print("[NAUTILUS PRESET] Alle Basis-Module erfolgreich importiert.") # Erfolgsmeldung

except ImportError as e:
    print(f"[NAUTILUS IMPORT ERROR] Module not found: {e}")
    print("Ensure Nautilus Trader is installed correctly in your virtual environment (e.g., via 'pip install -e .').")
except Exception as e_general:
    print(f"[UNEXPECTED NAUTILUS IMPORT ERROR]: {e_general}")

# --- Dein Projektcode beginnt hier (außerhalb dieses Presets) ---
# if __name__ == "__main__":
#     print("Nautilus Trader Module (Basis) scheinen geladen zu sein.") # Kann jetzt weg, da oben bestätigt
#     # Deine Logik hier...