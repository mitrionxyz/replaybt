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
from .engine.orders import Order, MarketOrder, LimitOrder

# Data types
from .data.types import Bar, Fill, Position, Trade, Side, OrderType, ExitReason, PendingOrder, ScaleInOrder

# Data providers
from .data.providers.base import DataProvider
from .data.providers.csv import CSVProvider

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

# Reporting
from .reporting.metrics import BacktestResults

__all__ = [
    # Engine
    "BacktestEngine",
    "ExecutionModel",
    "Portfolio",
    "Order",
    "MarketOrder",
    "LimitOrder",
    # Data
    "Bar",
    "Fill",
    "Position",
    "Trade",
    "Side",
    "OrderType",
    "ExitReason",
    "PendingOrder",
    "ScaleInOrder",
    "DataProvider",
    "CSVProvider",
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
    # Reporting
    "BacktestResults",
]
