"""replaybt — Realistic backtesting engine for algo traders & AI agents.

Engine owns execution. Strategy only emits signals.
No look-ahead bias. Gap protection. Adverse slippage. Fees.

Quick start:
    from replaybt import BacktestEngine, CSVProvider, Strategy, Bar, Order, MarketOrder

    class MyStrategy(Strategy):
        def on_bar(self, bar, indicators, positions):
            # Your logic here — return Order or None
            return None

    engine = BacktestEngine(
        strategy=MyStrategy(),
        data=CSVProvider('ETH_1m.csv'),
        config={'initial_equity': 10000},
    )
    results = engine.run()
    print(results.summary())
"""

from .version import __version__

# Core engine
from .engine.loop import BacktestEngine
from .engine.execution import ExecutionModel
from .engine.portfolio import Portfolio
from .engine.orders import Order, MarketOrder, LimitOrder, CancelPendingLimitsOrder
from .engine.step import StepEngine, StepObservation, StepResult
from .engine.processor import BarProcessor
from .engine.multi import MultiAssetEngine

# Data types
from .data.types import Bar, Fill, Position, Trade, Side, OrderType, ExitReason, PendingOrder

# Data providers
from .data.providers.base import DataProvider
from .data.providers.csv import CSVProvider
from .data.providers.replay import ReplayProvider
from .data.providers.live import AsyncDataProvider, HyperliquidProvider, LighterProvider

# Indicators
from .indicators.base import Indicator, IndicatorManager
from .indicators.ema import EMA
from .indicators.sma import SMA
from .indicators.rsi import RSI
from .indicators.atr import ATR
from .indicators.chop import CHOP
from .indicators.bollinger import BollingerBands
from .indicators.macd import MACD
from .indicators.stochastic import Stochastic
from .indicators.vwap import VWAP
from .indicators.obv import OBV
from .indicators.resampler import Resampler

# Strategy
from .strategy.base import Strategy
from .strategy.config import StrategyConfig
from .strategy.declarative import DeclarativeStrategy

# Reporting
from .reporting.metrics import BacktestResults
from .reporting.monthly import MonthStats, monthly_breakdown, format_monthly_table
from .reporting.multi import MultiAssetResults

# Validation
from .validation.auditor import BacktestAuditor, Issue, audit_file
from .validation.stress import DelayTest, DelayTestResult, OOSSplit, OOSResult

# Optimization
from .optimize.sweep import ParameterSweep
from .optimize.results import SweepResults

__all__ = [
    # Engine
    "BacktestEngine",
    "ExecutionModel",
    "Portfolio",
    "Order",
    "MarketOrder",
    "LimitOrder",
    "CancelPendingLimitsOrder",
    "StepEngine",
    "StepObservation",
    "StepResult",
    "BarProcessor",
    "MultiAssetEngine",
    # Data
    "Bar",
    "Fill",
    "Position",
    "Trade",
    "Side",
    "OrderType",
    "ExitReason",
    "PendingOrder",
    "DataProvider",
    "CSVProvider",
    "ReplayProvider",
    "AsyncDataProvider",
    "HyperliquidProvider",
    "LighterProvider",
    # Indicators
    "Indicator",
    "IndicatorManager",
    "EMA",
    "SMA",
    "RSI",
    "ATR",
    "CHOP",
    "BollingerBands",
    "MACD",
    "Stochastic",
    "VWAP",
    "OBV",
    "Resampler",
    # Strategy
    "Strategy",
    "StrategyConfig",
    "DeclarativeStrategy",
    # Reporting
    "BacktestResults",
    "MonthStats",
    "monthly_breakdown",
    "format_monthly_table",
    "MultiAssetResults",
    # Validation
    "BacktestAuditor",
    "Issue",
    "audit_file",
    "DelayTest",
    "DelayTestResult",
    "OOSSplit",
    "OOSResult",
    # Optimization
    "ParameterSweep",
    "SweepResults",
]
