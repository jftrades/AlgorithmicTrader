#Folglich ist die Grundidee, wie wir, wenn wir bei einer Strategie mehrere Paramterkombinationen testen vorgehen werden
#Dazu ein Beispielcode/Änderungen die man bei einer Strategie vornehmen muss um dise Optimierung laufen zu lassen
#meine Idee war es, durch Pandas diese Ergebnisse zu sortieren/sortieren zu lassen um schnell folgednes zu sehen
#ist die Strategie overfittet an vergangene Ergebnisse?, ist der positive Return ein Einzelfall (K.O)?...


#Option 1: Python Code schreiben (müsste man denke ich halt immer an die Strategie obv anpassen), der dir verschiedenen
    #Möglichkeiten durchiteriert - er müsste für jede Kombination einen komplett neuen Backtest starten ()
#Option 2: eine externe : Wir bienden eine externe Bibliothek ein, die intelligentere Suchstrategien im Parameterraum anwendet. 
    #-> Eine Funktion definieren, die für gegebene Parameter einen Nautilus-Backtest ausführt und eine Zielmetrik (z.B. Profit oder Sharpe Ratio) zurückgibt.
    #-> Die Bibliothek versucht dann, die Parameter zu finden, die diese Metrik optimieren.
#Option 3:Es gibt mittlerweile irgendwas in nautilus, was so etwas kann


#ich denke am sinnvollsten, meisten Kontrolle und sichersten ist Methode 1:
#um all das zu ermöglichen, müsste zuerst das Backtest Ergebniss sinnvoll und verwendbar geplottet werden - z.B:
metrics = result.portfolio_metrics() # oder: 
result.strategy_report('strategiename').metrics

#1. dann müssen wir wenn backtesting funktioniert manuell eine Liste erstellen - z.B:
ema_short_periods = [10, 15, 20, 25]
ema_long_periods = [30, 40, 50, 60] 

#2. leere Liste als Sammelstelle für kommenden Daten anlegen - z.B:
optimization_results = []


#3. for loops durchlaufen lassen z.B:
for short_p in ema_short_periods:
    for long_p in ema_long_periods:
        # Ungültige Kombis überspringen (short >= long)
        if short_p >= long_p:
            continue 

        print(f"--- Teste EMA Cross: Short={short_p}, Long={long_p} ---")
        
        # ---- HIER KOMMT DEIN CODE AUS PHASE 1 REIN ----
        # ABER: Mit angepasster Strategie-Konfiguration

        # a) Strategie-Config dynamisch erstellen
        current_strategy_config = EMACrossConfig(
            # ... feste Parameter wie instrument_id, bar_type ...
            ema_short=short_p, 
            ema_long=long_p,
            # ... andere Parameter der Strategie ...
        )

        # b) BacktestEngine aufsetzen (wie in Phase 1, aber mit current_strategy_config)
        # engine = BacktestEngine(...)
        # engine.add_data_provider(...)
        # engine.add_strategy(EMACross(config=current_strategy_config))
        
        # c) Backtest laufen lassen
        # result = engine.run()
        
        # d) Metriken extrahieren (aus result - WICHTIG!)
        # Beispielhafte, fiktive Metrik-Extraktion:
        # metrics = result.portfolio_metrics() 
        # pnl = metrics.get('total_pnl_quote', None)
        # drawdown = metrics.get('max_drawdown_pct', None)
        # trades = metrics.get('total_trades', None)
        
        # Platzhalter - ersetzen durch echte Metrik-Extraktion
        pnl = short_p * 2 - long_p 
        drawdown = long_p / 100.0
        trades = short_p + long_p

        # e) Ergebnisse speichern
        optimization_results.append({
            'ema_short': short_p,
            'ema_long': long_p,
            'Total PnL': pnl,
            'Max Drawdown': drawdown,
            'Num Trades': trades,
            # ... weitere Metriken ...
        })
        # --------------------------------------------
        
        # Optional: Kurze Pause oder Speicher freigeben, falls nötig
        # time.sleep(0.1) 
        # del engine, result, metrics # Kann helfen, Speicherprobleme bei sehr vielen Läufen zu vermeiden











#4. Auswertung mit Pandas z.B:

import pandas as pd
import os # Importiere os für die Pfadoperationen beim Speichern

# Sicherstellen, dass die Ergebnisliste existiert (sollte durch Schritt 2 initialisiert sein)
if 'optimization_results' not in locals() or not isinstance(optimization_results, list):
    print("FEHLER: Die Liste 'optimization_results' wurde nicht gefunden oder ist keine Liste.")
    print("Stelle sicher, dass die Optimierungsschleifen vorher gelaufen sind und Ergebnisse hinzugefügt haben.")
else:
    if not optimization_results:
        print("\nWARNUNG: Die Liste 'optimization_results' ist leer. Keine Backtests durchgeführt oder keine Ergebnisse gesammelt.")
    else:
        # --- Ergebnisse in DataFrame umwandeln ---
        try:
            results_df = pd.DataFrame(optimization_results)
            
            print("\n--- Optimierungsergebnisse (Rohtabelle) ---")
            # Zeige alle Spalten und mehr Zeilen an (optional anpassen)
            pd.set_option('display.max_rows', 100) 
            pd.set_option('display.max_columns', None) 
            pd.set_option('display.width', 1000)
            print(results_df)

            # --- Sortieren nach der wichtigsten Metrik (z.B. 'Total PnL') ---
            # Überprüfe, ob die Spalte existiert, bevor du sortierst
            sort_column = 'Total PnL' # ÄNDERE DIES, falls deine Hauptmetrik anders heißt!
            if sort_column in results_df.columns:
                # Erstelle eine Kopie für die sortierte Ansicht
                best_results_df = results_df.sort_values(by=sort_column, ascending=False).copy()
                print(f"\n--- Beste Ergebnisse (sortiert nach {sort_column}) ---")
                print(best_results_df.head(10)) # Zeige die Top 10 Ergebnisse

                # --- Optional: Ergebnisse als CSV speichern ---
                # Erstelle einen Unterordner für die Ergebnisse, falls er nicht existiert
                results_folder = "optimization_output" 
                os.makedirs(results_folder, exist_ok=True) 
                
                # Erstelle einen sinnvollen Dateinamen (kannst du anpassen)
                strategy_name = "EMACross" # Beispiel, passe das an deine Strategie an
                params_str = "_".join(results_df.columns[:2]) # Nimmt die ersten beiden Spalten als Parameter an
                output_filename = f"{strategy_name}_optimierung_{params_str}.csv"
                output_csv_path = os.path.join(results_folder, output_filename)
                
                try:
                    # Speichere den sortierten DataFrame
                    best_results_df.to_csv(output_csv_path, index=False) # index=False, um den Pandas-Index nicht mitzuspeichern
                    print(f"\nOptimierungsergebnisse erfolgreich gespeichert in: {output_csv_path}")
                except Exception as e_save:
                    print(f"\nFEHLER beim Speichern der Ergebnisse als CSV: {e_save}")

            else:
                print(f"\nWARNUNG: Die Spalte '{sort_column}' zum Sortieren wurde im DataFrame nicht gefunden.")
                print("Überprüfe die Namen der Metriken, die in der 'optimization_results'-Liste gespeichert werden.")

        except Exception as e_pandas:
            print(f"\nFEHLER bei der Verarbeitung der Ergebnisse mit Pandas: {e_pandas}")
            print("Überprüfe das Format der Daten in der 'optimization_results'-Liste.")

# --- Ende von Schritt 4 ---