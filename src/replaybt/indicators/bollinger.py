"""Bollinger Bands — SMA ± N standard deviations."""

from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Any, Dict, Optional, Tuple

from ..data.types import Bar
from .base import Indicator


class BollingerBands(Indicator):
    """Bollinger Bands.

    Returns a dict with keys: 'upper', 'middle', 'lower', 'bandwidth', 'pct_b'.

    Config:
        period: SMA period (default 20).
        num_std: Number of standard deviations (default 2.0).
        source: Price field ('close').
    """

    def __init__(
        self,
        name: str,
        period: int = 20,
        num_std: float = 2.0,
        source: str = "close",
    ):
        super().__init__(name, period)
        self.num_std = num_std
        self.source = source
        self._window: deque = deque(maxlen=period)
        self._value: Optional[Dict[str, float]] = None

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "BollingerBands":
        return cls(
            name=name,
            period=config.get("period", 20),
            num_std=config.get("num_std", 2.0),
            source=config.get("source", "close"),
        )

    def update(self, bar: Bar) -> None:
        price = getattr(bar, self.source, bar.close)
        self._window.append(price)

        if len(self._window) < self.period:
            return

        n = self.period
        mean = sum(self._window) / n
        variance = sum((x - mean) ** 2 for x in self._window) / n
        std = sqrt(variance)

        upper = mean + self.num_std * std
        lower = mean - self.num_std * std
        bandwidth = (upper - lower) / mean * 100 if mean > 0 else 0
        pct_b = (price - lower) / (upper - lower) if upper != lower else 0.5

        self._value = {
            "upper": upper,
            "middle": mean,
            "lower": lower,
            "bandwidth": bandwidth,
            "pct_b": pct_b,
        }
        self._ready = True

    def value(self) -> Optional[Dict[str, float]]:
        return self._value

    @property
    def upper(self) -> Optional[float]:
        return self._value["upper"] if self._value else None

    @property
    def middle(self) -> Optional[float]:
        return self._value["middle"] if self._value else None

    @property
    def lower(self) -> Optional[float]:
        return self._value["lower"] if self._value else None

    def reset(self) -> None:
        super().reset()
        self._window.clear()
        self._value = None
