"""Stochastic Oscillator — %K and %D."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator


class Stochastic(Indicator):
    """Stochastic Oscillator.

    Returns a dict with keys: 'k' (%K), 'd' (%D).

    %K = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
    %D = SMA of %K

    Config:
        k_period: Lookback for highest high / lowest low (default 14).
        d_period: Smoothing period for %D (default 3).
        smooth_k: Smoothing period for %K (default 3, set 1 for fast stoch).
    """

    def __init__(
        self,
        name: str,
        k_period: int = 14,
        d_period: int = 3,
        smooth_k: int = 3,
        period: int = 14,
    ):
        super().__init__(name, period=k_period)
        self.k_period = k_period
        self.d_period = d_period
        self.smooth_k = smooth_k

        self._highs: deque = deque(maxlen=k_period)
        self._lows: deque = deque(maxlen=k_period)
        self._raw_k: deque = deque(maxlen=smooth_k)
        self._k_values: deque = deque(maxlen=d_period)
        self._value: Optional[Dict[str, float]] = None

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "Stochastic":
        return cls(
            name=name,
            k_period=config.get("k_period", config.get("period", 14)),
            d_period=config.get("d_period", 3),
            smooth_k=config.get("smooth_k", 3),
        )

    def update(self, bar: Bar) -> None:
        self._highs.append(bar.high)
        self._lows.append(bar.low)

        if len(self._highs) < self.k_period:
            return

        highest = max(self._highs)
        lowest = min(self._lows)

        if highest == lowest:
            raw_k = 50.0
        else:
            raw_k = (bar.close - lowest) / (highest - lowest) * 100

        # Smooth %K
        self._raw_k.append(raw_k)
        if len(self._raw_k) < self.smooth_k:
            return
        k = sum(self._raw_k) / self.smooth_k

        # %D = SMA of %K
        self._k_values.append(k)
        if len(self._k_values) < self.d_period:
            self._value = {"k": k, "d": k}
            self._ready = True
            return

        d = sum(self._k_values) / self.d_period
        self._value = {"k": k, "d": d}
        self._ready = True

    def value(self) -> Optional[Dict[str, float]]:
        return self._value

    @property
    def k(self) -> Optional[float]:
        return self._value["k"] if self._value else None

    @property
    def d(self) -> Optional[float]:
        return self._value["d"] if self._value else None

    def reset(self) -> None:
        super().reset()
        self._highs.clear()
        self._lows.clear()
        self._raw_k.clear()
        self._k_values.clear()
        self._value = None
