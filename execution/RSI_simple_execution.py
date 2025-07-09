# Standard Library Importe
import sys
import time
import pandas as pd
from pathlib import Path
from decimal import Decimal 

# Nautilus Core Importe (v2.18 safe order)
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, AccountId
from nautilus_trader.model.currencies import USDT, BTC

# Import in separate groups to avoid circular dependency
from nautilus_trader.model.objects import Money

# Strategy and config imports
from nautilus_trader.trading.config import ImportableStrategyConfig

# Backtest imports - in correct order
from nautilus_trader.backtest.config import BacktestDataConfig, BacktestVenueConfig, BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.results import BacktestResult

from core.visualizing.dashboard import TradingDashboard

# Hier die gleichen Parameter wie aus strategy aber halt anpassen
symbol = Symbol("BTCUSDT")
venue = Venue("BINANCE")
instrument_id = InstrumentId(symbol, venue)
instrument_id_str = "BTCUSDT-PERP.BINANCE"
bar_type_str_for_configs = "BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"
trade_size = Decimal("0.5")
rsi_period = 14
rsi_overbought = 0.8
rsi_oversold = 0.2
close_positions_on_stop = True

start_date = "2024-10-01T00:00:00Z"
end_date = "2024-10-31T00:00:00Z"

catalogPath = str(Path(__file__).resolve().parents[1] / "data" / "DATA_STORAGE" / "data_catalog_wrangled")

# DataConfig
data_config = BacktestDataConfig(
    data_cls="nautilus_trader.model.data:Bar", # Traditioneller Pfad, der für Deserialisierung funktionierte
    catalog_path=catalogPath,
    bar_types=[bar_type_str_for_configs]
)


# VenueConfig - CHANGED TO CASH for automatic PnL balance updates
venue_config = BacktestVenueConfig(
    name="BINANCE",
    oms_type="NETTING", 
    account_type="MARGIN",  # FIXED: CASH automatically updates balance with realized PnL
    starting_balances=["100000 USDT"]
)


# StrategyConfig - IMMER anpassen!!
strategy_config = ImportableStrategyConfig(
    strategy_path = "RSI_simple_strategy_crypto:RSISimpleStrategy",
    config_path = "RSI_simple_strategy_crypto:RSISimpleStrategyConfig",

    config={
        "instrument_id": instrument_id_str,
        "bar_type": bar_type_str_for_configs,
        "trade_size": "0.5", # Trade Size in BTC
        #hier kommen jetzt die Strategie spezifischen Parameter
        "rsi_period": 14,
        "rsi_overbought": 0.8, 
        "rsi_oversold": 0.2,
        "close_positions_on_stop": True # Positionen werden beim Stop der Strategie geschlossen

    }
)


# EngineConfig -> welche Strategien bei diesem Backtest laufen sollen
engine_config = BacktestEngineConfig(strategies=[strategy_config])


# RunConfig -> hier wird data, venues und engine zusammengeführt
run_config = BacktestRunConfig(data=[data_config], venues=[venue_config], engine=engine_config, start=start_date, end=end_date)



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
    
    # === EINGEBAUTE TRADE REPORTS ===
    print("\n" + "=" * 60)
    print("📊 TRADE REPORTS (Built-in NautilusTrader Analyzer)")
    print("=" * 60)
    
    # Correct way: get the engine from the node, then access its trader
    engine = node.get_engine(run_config.id)
    trader = engine.trader
    
    # Reports generieren
    fills_report = trader.generate_order_fills_report()
    positions_report = trader.generate_positions_report()
    orders_report = trader.generate_orders_report()
    
    # Alle Trades mit PnL anzeigen
    if not fills_report.empty:
        print("\n🔸 ALL TRADES WITH PnL:")
        print(f"Available columns: {list(fills_report.columns)}")
        
        # Nur verfügbare Spalten verwenden
        wanted_cols = ['instrument_id', 'side', 'order_side', 'quantity', 'last_qty', 'price', 'last_px', 
                      'avg_px', 'commission', 'realized_pnl', 'ts_event', 'ts_last', 'ts_init']
        available_cols = [col for col in wanted_cols if col in fills_report.columns]
        
        if available_cols:
            print(fills_report[available_cols].to_string())
        else:
            print("Showing all available data:")
            print(fills_report.to_string())
        print(f"\nTotal Trades: {len(fills_report)}")
    else:
        print("\n🔸 Keine Fills/Trades gefunden!")
    
    # Positions Summary mit PnL
    if not positions_report.empty:
        print("\n🔸 POSITIONS SUMMARY:")
        pos_cols = ['instrument_id', 'side', 'avg_px_open', 'avg_px_close', 'realized_pnl']
        available_cols = [col for col in pos_cols if col in positions_report.columns]
        print(positions_report[available_cols].to_string())
        
        # Total PnL aus Positions - handle Money objects properly
        if 'realized_pnl' in positions_report.columns:
            try:
                # Extract numeric values from Money objects (remove currency)
                pnl_values = []
                for pnl in positions_report['realized_pnl']:
                    if isinstance(pnl, str):
                        # Extract number from "123.45 USDT" format
                        numeric_part = pnl.split()[0] if ' ' in str(pnl) else str(pnl)
                        pnl_values.append(float(numeric_part))
                    else:
                        pnl_values.append(float(pnl))
                
                total_pnl = sum(pnl_values)
                print(f"\n💰 Total Realized PnL from Positions: {total_pnl:.4f} USDT")
            except Exception as e:
                print(f"\n💰 Total Realized PnL calculation error: {e}")
                print(f"Raw PnL data: {list(positions_report['realized_pnl'])[:3]}...")
    else:
        print("\n🔸 Keine Positionen gefunden!")
    
    # Orders Overview
    if not orders_report.empty:
        print(f"\n🔸 ORDERS OVERVIEW: {len(orders_report)} total orders")
        # Check what columns are available for orders
        if 'filled_qty' in orders_report.columns:
            try:
                # Convert filled_qty to numeric for comparison
                orders_report['filled_qty_numeric'] = pd.to_numeric(orders_report['filled_qty'], errors='coerce')
                filled_orders = orders_report[orders_report['filled_qty_numeric'] > 0]
                print(f"   - Filled Orders: {len(filled_orders)}")
                print(f"   - Cancelled/Rejected: {len(orders_report) - len(filled_orders)}")
            except Exception as e:
                print(f"   - Error processing filled_qty: {e}")
                print(f"   - Sample filled_qty values: {list(orders_report['filled_qty'].head())}")
        else:
            print(f"   - Available columns: {list(orders_report.columns)}")
            print("   - Showing first few orders:")
            print(orders_report.head().to_string())
    else:
        print("\n🔸 Keine Orders gefunden!")
    
    print("=" * 60)
    
    # === DETAILED PnL ANALYSIS ===
    print("\n" + "=" * 60)
    print("🔍 DETAILED PnL ANALYSIS - Investigating Discrepancy")
    print("=" * 60)
    
    # 1. Portfolio-level PnL - Get account balances instead of net_liquidating_value
    portfolio = engine.trader._portfolio  # Use _portfolio instead of portfolio
    total_realized_pnl_portfolio = portfolio.realized_pnl(instrument_id)
    total_unrealized_pnl_portfolio = portfolio.unrealized_pnl(instrument_id)
    
    # Get account for portfolio value calculation using venue directly
    account = portfolio.account(venue)
    if account:
        usdt_balance = account.balance_total(USDT)
        total_portfolio_value = usdt_balance.as_double() if usdt_balance else 0.0
    else:
        total_portfolio_value = 0.0
    
    print(f"\n🔸 PORTFOLIO LEVEL:")
    print(f"   - Realized PnL (Portfolio): {total_realized_pnl_portfolio}")
    print(f"   - Unrealized PnL (Portfolio): {total_unrealized_pnl_portfolio}")
    print(f"   - Total Portfolio Value: {total_portfolio_value:.2f} USDT")
    
    # 2. Account-level balances
    # account is already retrieved above for portfolio value calculation
    if account:
        print(f"\n🔸 ACCOUNT LEVEL:")
        usdt_balance = account.balance_total(USDT)
        print(f"   - Account balance USDT: {usdt_balance}")
        starting_balance = Money(100000, USDT)
        if usdt_balance:
            balance_change = usdt_balance.as_double() - starting_balance.as_double()
            print(f"   - Starting balance: {starting_balance}")
            print(f"   - Current balance: {usdt_balance}")
            print(f"   - Balance change: {balance_change:.4f} USDT")
    
    # 3. Commission analysis
    if not fills_report.empty and 'commissions' in fills_report.columns:
        print(f"\n🔸 COMMISSION ANALYSIS:")
        print(f"   - Sample commissions: {list(fills_report['commissions'].head())}")
        # Try to sum commissions if they're numeric
        try:
            if fills_report['commissions'].dtype == 'object':
                # Extract numeric part from commission strings
                comm_values = []
                for comm in fills_report['commissions']:
                    if comm and str(comm) != 'nan':
                        if isinstance(comm, str) and ' ' in comm:
                            numeric_part = comm.split()[0]
                            comm_values.append(float(numeric_part))
                        else:
                            comm_values.append(float(comm))
                total_commissions = sum(comm_values) if comm_values else 0
            else:
                total_commissions = fills_report['commissions'].sum()
            print(f"   - Total commissions: {total_commissions:.4f}")
        except Exception as e:
            print(f"   - Commission calculation error: {e}")
    
    print("=" * 60)
else:
    print("No results to display.")

    time.sleep(1)


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
print("INFO: Starte Dashboard...")
visualizer.visualize(visualize_after_backtest=True)