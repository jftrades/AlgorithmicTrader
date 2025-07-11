from pathlib import Path
from nautilus_trader.persistence.catalog import ParquetDataCatalog

catalogPath = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")
catalog = ParquetDataCatalog(catalogPath)

print("=== CATALOG DEBUG ===")
print(f"Catalog path: {catalogPath}")

# 1. Alle verfügbaren Instrumente
print("\n1. Available instruments:")
instruments = catalog.instruments()
print(f"Total instruments: {len(instruments)}")
for instrument in instruments:
    print(f"  - ID: {instrument.id}")
    print(f"    Symbol: {instrument.id.symbol}")
    print(f"    Venue: {instrument.id.venue}")
    print(f"    Type: {type(instrument).__name__}")
    if hasattr(instrument, 'raw_symbol'):
        print(f"    Raw Symbol: {instrument.raw_symbol}")
    print()

# 2. Alle verfügbaren Bar-Typen
print("\n2. Available bar types:")
try:
    all_bars = catalog.bars()
    if all_bars:
        bar_types = set()
        for bar in all_bars[:10]:  # Nur erste 10 für Beispiel
            bar_types.add(str(bar.bar_type))
        for bar_type in sorted(bar_types):
            print(f"  - {bar_type}")
    else:
        print("  No bars found")
except Exception as e:
    print(f"  Error reading bars: {e}")

# 3. Suche nach ES-verwandten Instrumenten
print("\n3. ES-related instruments:")
es_instruments = [inst for inst in instruments if "ES" in str(inst.id)]
for instrument in es_instruments:
    print(f"  - {instrument.id} ({type(instrument).__name__})")

# 4. Liste alle Datentypen
print("\n4. Data types in catalog:")
data_types = catalog.list_data_types()
for data_type in data_types:
    print(f"  - {data_type}")