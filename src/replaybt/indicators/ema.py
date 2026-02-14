"""Exponential Moving Average — batch and incremental."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator


class EMA(Indicator):
    """Exponential Moving Average.

    Supports both incremental (bar-by-bar) and batch (pandas) modes.

    Config:
        period: EMA period (e.g. 15, 35).
        source: Price field to use ('close', 'open', 'high', 'low').
    """

    def __init__(self, name: str, period: int = 14, source: str = "close"):
        super().__init__(name, period)
        self.source = source
        self._multiplier = 2.0 / (period + 1)
        self._value: Optional[float] = None
        self._count = 0
        self._sum = 0.0

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "EMA":
        return cls(
            name=name,
            period=config.get("period", 14),
            source=config.get("source", "close"),
        )

    def update(self, bar: Bar) -> None:
        price = getattr(bar, self.source, bar.close)
        self._count += 1

        if self._value is None:
            # First value seeds the EMA (matches pandas ewm adjust=False)
            self._value = price
        else:
            self._value = (price - self._value) * self._multiplier + self._value

        if self._count >= self.period:
            self._ready = True

    def value(self) -> Optional[float]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._value = None
        self._count = 0
        self._sum = 0.0
