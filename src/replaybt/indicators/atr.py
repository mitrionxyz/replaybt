"""Average True Range — incremental."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator


class ATR(Indicator):
    """Average True Range.

    Uses simple rolling mean of True Range (matches the batch
    pattern in backtest_combined_clean.py).

    True Range = max(H-L, |H-prev_close|, |L-prev_close|)

    Config:
        period: ATR period (default 14).
        mode: 'sma' (default) or 'wilder' (exponential smoothing).
    """

    def __init__(self, name: str, period: int = 14, mode: str = "sma"):
        super().__init__(name, period)
        self.mode = mode
        self._prev_close: Optional[float] = None
        self._tr_window: deque = deque(maxlen=period)
        self._value: Optional[float] = None
        # For wilder mode
        self._wilder_atr: Optional[float] = None
        self._count: int = 0

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "ATR":
        return cls(
            name=name,
            period=config.get("period", 14),
            mode=config.get("mode", "sma"),
        )

    def update(self, bar: Bar) -> None:
        if self._prev_close is None:
            self._prev_close = bar.close
            # First bar: TR = high - low (no previous close)
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self._prev_close),
                abs(bar.low - self._prev_close),
            )
            self._prev_close = bar.close

        self._count += 1

        if self.mode == "wilder":
            self._update_wilder(tr)
        else:
            self._update_sma(tr)

    def _update_sma(self, tr: float) -> None:
        """Simple rolling mean of TR."""
        self._tr_window.append(tr)
        if len(self._tr_window) >= self.period:
            self._value = sum(self._tr_window) / self.period
            self._ready = True

    def _update_wilder(self, tr: float) -> None:
        """Wilder's smoothed ATR: ATR = ((period-1)*prev_ATR + TR) / period."""
        if self._wilder_atr is None:
            self._tr_window.append(tr)
            if len(self._tr_window) >= self.period:
                self._wilder_atr = sum(self._tr_window) / self.period
                self._value = self._wilder_atr
                self._ready = True
        else:
            self._wilder_atr = ((self.period - 1) * self._wilder_atr + tr) / self.period
            self._value = self._wilder_atr

    def value(self) -> Optional[float]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._prev_close = None
        self._tr_window.clear()
        self._value = None
        self._wilder_atr = None
        self._count = 0
