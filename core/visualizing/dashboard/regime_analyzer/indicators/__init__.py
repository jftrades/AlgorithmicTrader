"""
Advanced Indicator System for Regime Analysis

This module provides a comprehensive indicator infrastructure that combines:
- CSV-based indicators from backtest runs
- General financial indicators (RSI, MACD, etc.)
- Chart-based technical indicators
- Crypto-specific indicators (Fear & Greed, etc.)
- Index/Stock-specific indicators

Architecture:
- BaseIndicator: Abstract base class for all indicators
- GeneralIndicator: Common financial indicators (RSI, MACD, Bollinger Bands, etc.)
- ChartBasedIndicator: Price action derived indicators
- CryptoIndicator: Cryptocurrency market specific indicators
- IndexIndicator: Stock market/index specific indicators
- IndicatorManager: Orchestrates indicator loading based on analysis type
"""

from .base_indicator import BaseIndicator
from .general_indicator import GeneralIndicator
from .chart_based_indicator import ChartBasedIndicator
from .crypto_indicator import CryptoIndicator
from .index_indicator import IndexIndicator
from .indicator_manager import IndicatorManager

__all__ = [
    'BaseIndicator',
    'GeneralIndicator', 
    'ChartBasedIndicator',
    'CryptoIndicator',
    'IndexIndicator',
    'IndicatorManager'
]
