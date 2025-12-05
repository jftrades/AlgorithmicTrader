# AlgorithmicTrader
The framework for developing and visualizing various trading strategies.  
We create alpha by engineering self-adapting trading systems.

## Overview
AlgorithmicTrader is a modular research and execution framework for designing, evaluating, and visualizing quantitative trading strategies.  
It integrates data ingestion, signal generation, risk management, backtesting, and an interactive visualization tool into a unified pipeline.

The framework focuses on crypto perpetual futures, including newly listed assets with extreme volatility and alpha-rich dynamics.

---

## Key Features

### Strategy Library
- **New-Listing Short Strategy**: Exploits post-listing mean-reversion patterns of newly listed perp futures. Includes coin classification (meme, AI, utility), social-metric scoring, and long-term survival probability estimation.
- **Momentum & Reversion Signals**: ATR-normalized breakouts, Z-score reversals, volatility-scaled entries.
- **Global Market Filter**: Market regime estimation using SOL/ETH benchmarks, VWAP deviation filters, and Kalman-trend states.
- **Dynamic Risk Scaling**: Volatility-adjusted position sizing, leverage throttling, and event-aware stop systems.

All strategies follow a unified, modular interface.


## Visualization & Analytics
The integrated analytics module provides:

- Equity curves (strategy & portfolio)
- Drawdown / underwater plots
- Trade lineage and execution diagnostics
- Signal overlays and parameter tracing
- Regime-based performance breakdowns
- Comparison across multiple runs


## Backtesting Engine
- Deterministic simulation engine
- Latency-aware fill modeling
- Maker/taker fees and slippage simulation
- YAML-based experiment configuration
- Support for batch backtesting and multi-strategy sweeps


## Data Pipeline
- Unified schemas for kline, trades, funding
- Historical and real-time collectors
- Automatic cleaning, resampling, feature generation
- Exchange connectors for Binance/Bybit (NautilusTrader-compatible)
