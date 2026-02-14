"""MACD — Moving Average Convergence Divergence."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator
from .ema import EMA


class MACD(Indicator):
    """MACD indicator.

    Returns a dict with keys: 'macd', 'signal', 'histogram'.

    MACD line = fast EMA - slow EMA
    Signal line = EMA of MACD line
    Histogram = MACD - Signal

    Config:
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal line EMA period (default 9).
        source: Price field ('close').
    """

    def __init__(
        self,
        name: str,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        source: str = "close",
        period: int = 26,
    ):
        super().__init__(name, period=slow_period)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.source = source

        self._fast_ema = EMA(f"{name}_fast", period=fast_period, source=source)
        self._slow_ema = EMA(f"{name}_slow", period=slow_period, source=source)
        # Signal EMA processes MACD values, not bar prices
        self._signal_multiplier = 2.0 / (signal_period + 1)
        self._signal_value: Optional[float] = None
        self._signal_count: int = 0
        self._value: Optional[Dict[str, float]] = None

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "MACD":
        return cls(
            name=name,
            fast_period=config.get("fast_period", 12),
            slow_period=config.get("slow_period", 26),
            signal_period=config.get("signal_period", 9),
            source=config.get("source", "close"),
        )

    def update(self, bar: Bar) -> None:
        self._fast_ema.update(bar)
        self._slow_ema.update(bar)

        if not (self._fast_ema.ready and self._slow_ema.ready):
            return

        macd_line = self._fast_ema.value() - self._slow_ema.value()

        # Update signal EMA incrementally
        self._signal_count += 1
        if self._signal_value is None:
            self._signal_value = macd_line
        else:
            self._signal_value = (
                (macd_line - self._signal_value) * self._signal_multiplier
                + self._signal_value
            )

        histogram = macd_line - self._signal_value

        self._value = {
            "macd": macd_line,
            "signal": self._signal_value,
            "histogram": histogram,
        }

        if self._signal_count >= self.signal_period:
            self._ready = True

    def value(self) -> Optional[Dict[str, float]]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._fast_ema.reset()
        self._slow_ema.reset()
        self._signal_value = None
        self._signal_count = 0
        self._value = None
