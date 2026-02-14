"""Simple Moving Average — incremental with rolling window."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator


class SMA(Indicator):
    """Simple Moving Average.

    Config:
        period: SMA window size.
        source: Price field to use ('close', 'open', 'high', 'low').
    """

    def __init__(self, name: str, period: int = 14, source: str = "close"):
        super().__init__(name, period)
        self.source = source
        self._window: deque = deque(maxlen=period)
        self._sum: float = 0.0
        self._value: Optional[float] = None

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "SMA":
        return cls(
            name=name,
            period=config.get("period", 14),
            source=config.get("source", "close"),
        )

    def update(self, bar: Bar) -> None:
        price = getattr(bar, self.source, bar.close)

        # If window is full, subtract the oldest value
        if len(self._window) == self.period:
            self._sum -= self._window[0]

        self._window.append(price)
        self._sum += price

        if len(self._window) >= self.period:
            self._value = self._sum / self.period
            self._ready = True

    def value(self) -> Optional[float]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._window.clear()
        self._sum = 0.0
        self._value = None
