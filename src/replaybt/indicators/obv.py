"""On-Balance Volume."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator


class OBV(Indicator):
    """On-Balance Volume.

    Running total of volume: +volume on up closes, -volume on down closes.

    Config:
        No special config.
    """

    def __init__(self, name: str, period: int = 1):
        super().__init__(name, period)
        self._prev_close: Optional[float] = None
        self._obv: float = 0.0

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "OBV":
        return cls(name=name)

    def update(self, bar: Bar) -> None:
        if self._prev_close is not None:
            if bar.close > self._prev_close:
                self._obv += bar.volume
            elif bar.close < self._prev_close:
                self._obv -= bar.volume
            # Equal close: no change
        self._prev_close = bar.close
        self._ready = True

    def value(self) -> float:
        return self._obv

    def reset(self) -> None:
        super().reset()
        self._prev_close = None
        self._obv = 0.0
