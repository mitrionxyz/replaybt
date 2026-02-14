"""Indicator base class and manager."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..data.types import Bar


class Indicator(ABC):
    """Abstract indicator that processes bars incrementally.

    Indicators receive completed bars and maintain internal state.
    They expose their current value(s) via the value property.
    """

    def __init__(self, name: str, period: int = 14):
        self.name = name
        self.period = period
        self._ready = False

    @abstractmethod
    def update(self, bar: Bar) -> None:
        """Process a new completed bar."""
        ...

    @abstractmethod
    def value(self) -> Any:
        """Return current indicator value(s)."""
        ...

    @property
    def ready(self) -> bool:
        """True when enough data has been processed for valid output."""
        return self._ready

    def reset(self) -> None:
        """Reset internal state. Override in subclass."""
        self._ready = False

    @staticmethod
    def batch_ema(series, period: int):
        """Compute EMA on a pandas Series (batch mode)."""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def batch_rsi_wilder(closes, period: int = 14):
        """Compute Wilder's RSI on a pandas Series (batch mode)."""
        import pandas as pd
        delta = closes.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def batch_rsi_simple(closes, period: int = 14):
        """Compute Simple RSI on a pandas Series (batch mode)."""
        delta = closes.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


class IndicatorManager:
    """Manages a set of indicators, routing bars by timeframe.

    Handles resampling: 1m bars are aggregated into higher TF bars,
    and indicators are updated only when a higher TF bar completes.

    Config format:
        {
            "30m_ema_15": {"type": "ema", "timeframe": "30m", "period": 15, "source": "close"},
            "1h_ema_35": {"type": "ema", "timeframe": "1h", "period": 35, "source": "close"},
            "1m_rsi_7": {"type": "rsi", "timeframe": "1m", "period": 7, "mode": "wilder"},
        }
    """

    # Registry of indicator types
    _registry: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, indicator_class: type) -> None:
        cls._registry[name] = indicator_class

    def __init__(self, config: Dict[str, Dict] = None):
        self._config = config or {}
        self._indicators: Dict[str, Indicator] = {}
        self._resamplers: Dict[str, "_BarAccumulator"] = {}
        self._tf_indicators: Dict[str, List[str]] = defaultdict(list)

        self._build()

    def _register_builtins(self) -> None:
        """Auto-register all built-in indicator types."""
        from .ema import EMA
        from .rsi import RSI
        from .sma import SMA
        from .atr import ATR
        from .chop import CHOP
        from .bollinger import BollingerBands
        from .macd import MACD
        from .stochastic import Stochastic
        from .vwap import VWAP
        from .obv import OBV

        builtins = {
            "ema": EMA,
            "rsi": RSI,
            "sma": SMA,
            "atr": ATR,
            "chop": CHOP,
            "bollinger": BollingerBands,
            "bb": BollingerBands,
            "macd": MACD,
            "stochastic": Stochastic,
            "stoch": Stochastic,
            "vwap": VWAP,
            "obv": OBV,
        }
        for key, cls in builtins.items():
            if key not in self._registry:
                self._registry[key] = cls

    def _build(self) -> None:
        """Build indicators from config."""
        self._register_builtins()

        for name, cfg in self._config.items():
            ind_type = cfg.get("type", "ema")
            cls = self._registry.get(ind_type)
            if cls is None:
                available = ", ".join(sorted(self._registry.keys()))
                raise ValueError(
                    f"Unknown indicator type: '{ind_type}'. "
                    f"Available: {available}. "
                    f"Use IndicatorManager.register(name, YourClass) to add custom indicators."
                )

            indicator = cls.from_config(name, cfg)
            self._indicators[name] = indicator

            tf = cfg.get("timeframe", "1m")
            self._tf_indicators[tf].append(name)

            # Create resampler for non-1m timeframes
            if tf != "1m" and tf not in self._resamplers:
                self._resamplers[tf] = _BarAccumulator(tf)

    def update(self, bar: Bar) -> None:
        """Process a 1m bar. Resamples and updates indicators."""
        # Update 1m indicators directly
        for name in self._tf_indicators.get("1m", []):
            self._indicators[name].update(bar)

        # Accumulate into higher TFs
        for tf, accumulator in self._resamplers.items():
            completed_bar = accumulator.add(bar)
            if completed_bar is not None:
                for name in self._tf_indicators.get(tf, []):
                    self._indicators[name].update(completed_bar)

    def values(self) -> Dict[str, Any]:
        """Return current values of all indicators."""
        return {
            name: ind.value() for name, ind in self._indicators.items()
        }

    def get(self, name: str) -> Any:
        """Get a single indicator's value."""
        ind = self._indicators.get(name)
        return ind.value() if ind else None

    def reset(self) -> None:
        for ind in self._indicators.values():
            ind.reset()
        for acc in self._resamplers.values():
            acc.reset()


class _BarAccumulator:
    """Accumulates 1m bars into higher TF bars.

    Emits a completed bar when a new period boundary is crossed.
    """

    # Map timeframe strings to minutes
    TF_MINUTES = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "15min": 15,
        "30m": 30, "30min": 30, "1h": 60, "2h": 120, "4h": 240,
        "1d": 1440, "1D": 1440,
    }

    def __init__(self, timeframe: str):
        self.timeframe = timeframe
        self.minutes = self.TF_MINUTES.get(timeframe)
        if self.minutes is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        self._open: Optional[float] = None
        self._high: float = 0.0
        self._low: float = float("inf")
        self._close: float = 0.0
        self._volume: float = 0.0
        self._start_ts = None
        self._symbol: str = ""
        self._count: int = 0

    def _bar_boundary(self, bar: Bar) -> int:
        """Return the period boundary index for a timestamp."""
        from datetime import timezone
        ts = bar.timestamp
        # Minutes since midnight UTC
        total_minutes = ts.hour * 60 + ts.minute
        if self.minutes >= 1440:
            return ts.toordinal()
        return total_minutes // self.minutes

    def add(self, bar: Bar) -> Optional[Bar]:
        """Add a 1m bar. Returns completed higher-TF bar or None."""
        boundary = self._bar_boundary(bar)

        completed = None

        if self._start_ts is not None:
            prev_boundary = self._bar_boundary(
                Bar(timestamp=self._start_ts, open=0, high=0, low=0, close=0, volume=0)
            )
            if boundary != prev_boundary:
                # New period — emit the accumulated bar
                completed = Bar(
                    timestamp=self._start_ts,
                    open=self._open,
                    high=self._high,
                    low=self._low,
                    close=self._close,
                    volume=self._volume,
                    symbol=self._symbol,
                    timeframe=self.timeframe,
                )
                # Reset for new period
                self._open = None
                self._high = 0.0
                self._low = float("inf")
                self._volume = 0.0
                self._count = 0

        # Accumulate
        if self._open is None:
            self._open = bar.open
            self._start_ts = bar.timestamp
            self._symbol = bar.symbol
        self._high = max(self._high, bar.high)
        self._low = min(self._low, bar.low)
        self._close = bar.close
        self._volume += bar.volume
        self._count += 1

        return completed

    def reset(self) -> None:
        self._open = None
        self._high = 0.0
        self._low = float("inf")
        self._close = 0.0
        self._volume = 0.0
        self._start_ts = None
        self._count = 0
