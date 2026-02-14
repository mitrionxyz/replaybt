"""VWAP — Volume Weighted Average Price (daily reset)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator


class VWAP(Indicator):
    """Volume Weighted Average Price.

    Resets at midnight UTC each day (standard for crypto).

    Config:
        No special config needed.
    """

    def __init__(self, name: str, period: int = 1):
        super().__init__(name, period)
        self._cum_vol: float = 0.0
        self._cum_tp_vol: float = 0.0
        self._value: Optional[float] = None
        self._current_day: Optional[int] = None

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "VWAP":
        return cls(name=name)

    def update(self, bar: Bar) -> None:
        day = bar.timestamp.toordinal()

        # Reset on new day
        if self._current_day is not None and day != self._current_day:
            self._cum_vol = 0.0
            self._cum_tp_vol = 0.0

        self._current_day = day

        # Typical price = (H + L + C) / 3
        tp = (bar.high + bar.low + bar.close) / 3
        self._cum_tp_vol += tp * bar.volume
        self._cum_vol += bar.volume

        if self._cum_vol > 0:
            self._value = self._cum_tp_vol / self._cum_vol
            self._ready = True

    def value(self) -> Optional[float]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._cum_vol = 0.0
        self._cum_tp_vol = 0.0
        self._value = None
        self._current_day = None
