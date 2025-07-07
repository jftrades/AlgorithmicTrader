# Standard Library Importe
import sys
import time
from pathlib import Path

# Nautilus Kern Importe
from nautilus_trader.backtest.node import BacktestNode
from core.visualizing.dashboard import TradingDashboard

def setup_visualizer():
    """
    Setzt den Visualizer-Pfad und importiert TradingDashboard
    
    Returns:
        TradingDashboard: Dashboard Klasse
    """
    VIS_PATH = Path(__file__).resolve().parent.parent / "data" / "visualizing"
    
    if str(VIS_PATH) not in sys.path:
        sys.path.insert(0, str(VIS_PATH))
    
    return TradingDashboard


def run_backtest_and_visualize(run_config, TradingDashboard=None):
    """
    Führt Backtest aus und startet Visualizer
    
    Args:
        run_config: Nautilus BacktestRunConfig
        TradingDashboard: Optional - falls bereits mit setup_visualizer() geholt
    
    Returns:
        results: Backtest Ergebnisse
    """
    # Backtest ausführen
    try:
        node = BacktestNode(configs=[run_config])
        print(f"Starte Backtest...")
        results = node.run()
    except Exception as e:
        print(f"FEHLER: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Ergebnisse anzeigen
    if results:
        result = results[0]
        print("=" * 50)
        print(f"Backtest: {result.backtest_start} bis {result.backtest_end}")
        print(f"Orders: {result.total_orders} | Positionen: {result.total_positions}")
        
        # Performance
        for currency, metrics in result.stats_pnls.items():
            pnl = metrics.get('PnL', 0)
            print(f"{currency} PnL: {pnl:.2f}")
        
        # Trade Reports
        engine = node.get_engine(run_config.id)
        trader = engine.trader
        fills_report = trader.generate_order_fills_report()
        
        if not fills_report.empty:
            print(f"Trades: {len(fills_report)}")
        else:
            print("Keine Trades!")
        print("=" * 50)
    else:
        print("Keine Ergebnisse.")
        return None

    time.sleep(1)

    # VISUALIZER
    if TradingDashboard is None:
        TradingDashboard = setup_visualizer()
    
    visualizer = TradingDashboard()
    visualizer.collect_results(results)
    visualizer.load_data_from_csv()

    if visualizer.bars_df is not None:
        print(f"  - Bars geladen: {len(visualizer.bars_df)} Einträge")
    else:
        print("  - Keine Bars gefunden!")

    if visualizer.trades_df is not None:
        print(f"  - Trades geladen: {len(visualizer.trades_df)} Einträge")
    else:
        print("  - Keine Trades gefunden!")

    print(f"  - Indikatoren geladen: {len(visualizer.indicators_df)} Indikatoren")
    print(f"  - Metriken geladen: {len(visualizer.metrics) if visualizer.metrics else 0} Metriken")
    print("Starte Dashboard...")
    visualizer.visualize(visualize_after_backtest=True)

    return results
