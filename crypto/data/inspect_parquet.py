#war für mich um zu sehen, in welcher Formatierung die .parquet angelegt wird.
# (nämlich mit BarDataWranglerV2 und ParquetDataCatalog von Nautilus Trader selbst)
#in Nanosekunden und mit den Spalten ['open', 'high', 'low', 'close', 'volume', 'ts_event', 'ts_init']
#der Code hier kann gerne, ausser er könnte theoretisch doch noch irgendwann nützlich werden auch obv gelöscht werden :)



import pandas as pd
import os

# Relativer Pfad zu deiner Parquet-Datei (wie im Hauptskript)
relative_file_path = "DATA_STORAGE/data_catalog_wrangled/data/bar/BINANCE.BTCUSDT-15-MINUTE-LAST-EXTERNAL/part-0.parquet" # ANPASSEN, FALLS NÖTIG

# Stelle sicher, dass der Pfad korrekt aufgelöst wird, basierend auf dem aktuellen Arbeitsverzeichnis
absolute_file_path = os.path.abspath(relative_file_path)

print(f"Versuche, Datei zu laden von: {absolute_file_path}")

try:
    # Lese die Parquet-Datei
    df = pd.read_parquet(absolute_file_path)

    # Zeige die Spaltennamen an
    print("\n--- Spaltennamen ---")
    print(list(df.columns))

    # Zeige die Datentypen der Spalten an
    print("\n--- Datentypen der Spalten ---")
    print(df.dtypes)

    # Zeige die ersten paar Zeilen der Daten an
    print("\n--- Erste 5 Zeilen der Daten ---")
    print(df.head())

    # Zeige die letzten paar Zeilen der Daten an (optional, um den Zeitbereich zu sehen)
    print("\n--- Letzte 5 Zeilen der Daten ---")
    print(df.tail())

    # Zeige grundlegende Informationen über den DataFrame
    print("\n--- DataFrame Info ---")
    df.info()

except FileNotFoundError:
    print(f"FEHLER: Datei nicht gefunden unter dem Pfad: {absolute_file_path}")
    print("Bitte stelle sicher, dass der relative Pfad korrekt ist und du das Skript aus dem richtigen Verzeichnis startest.")
except Exception as e:
    print(f"Ein Fehler ist aufgetreten: {e}")
    