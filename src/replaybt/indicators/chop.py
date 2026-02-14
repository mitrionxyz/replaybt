"""Choppiness indicator — ATR/Price * 100."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator
from .atr import ATR


class CHOP(Indicator):
    """Choppiness filter: ATR / Close * 100.

    High values = choppy/ranging market (avoid entries).
    Low values = trending market (safe to enter).

    Validated threshold: 1.1% filters 38% of trades, +$4,912 vs disabled.

    Config:
        period: ATR period (default 14).
        atr_mode: ATR smoothing mode ('sma' or 'wilder').
    """

    def __init__(self, name: str, period: int = 14, atr_mode: str = "sma"):
        super().__init__(name, period)
        self._atr = ATR(f"{name}_atr", period=period, mode=atr_mode)
        self._value: Optional[float] = None
        self._last_close: float = 0.0

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "CHOP":
        return cls(
            name=name,
            period=config.get("period", 14),
            atr_mode=config.get("atr_mode", "sma"),
        )

    def update(self, bar: Bar) -> None:
        self._atr.update(bar)
        self._last_close = bar.close

        if self._atr.ready and bar.close > 0:
            self._value = (self._atr.value() / bar.close) * 100
            self._ready = True

    def value(self) -> Optional[float]:
        return self._value

    @property
    def atr_value(self) -> Optional[float]:
        """Access the underlying ATR value."""
        return self._atr.value()

    def reset(self) -> None:
        super().reset()
        self._atr.reset()
        self._value = None
        self._last_close = 0.0
