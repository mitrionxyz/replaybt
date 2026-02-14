"""RSI — Wilder's exponential and Simple rolling."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Optional

from ..data.types import Bar
from .base import Indicator


class RSI(Indicator):
    """Relative Strength Index.

    Supports two modes:
    - 'wilder' (default): Exponential smoothing with alpha=1/period (Wilder's)
    - 'simple': Simple rolling average

    Wilder's RSI outperforms Simple RSI by +$9,885 on HYPE (validated).

    Config:
        period: RSI period (default 14).
        mode: 'wilder' or 'simple'.
        source: Price field ('close').
    """

    def __init__(
        self,
        name: str,
        period: int = 14,
        mode: str = "wilder",
        source: str = "close",
    ):
        super().__init__(name, period)
        self.mode = mode
        self.source = source

        self._prev_close: Optional[float] = None
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0
        self._value: Optional[float] = None
        self._count = 0

        # For simple mode: rolling windows
        self._gains: deque = deque(maxlen=period)
        self._losses: deque = deque(maxlen=period)

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "RSI":
        return cls(
            name=name,
            period=config.get("period", 14),
            mode=config.get("mode", "wilder"),
            source=config.get("source", "close"),
        )

    def update(self, bar: Bar) -> None:
        price = getattr(bar, self.source, bar.close)

        if self._prev_close is None:
            self._prev_close = price
            return

        delta = price - self._prev_close
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        self._prev_close = price
        self._count += 1

        if self.mode == "wilder":
            self._update_wilder(gain, loss)
        else:
            self._update_simple(gain, loss)

    def _update_wilder(self, gain: float, loss: float) -> None:
        """Wilder's exponential smoothing: alpha = 1/period.

        Matches pandas ewm(alpha=1/period, min_periods=period, adjust=False)
        applied to a gain/loss series where index 0 is 0.0 (from NaN diff).

        pandas processes: [0, delta1, delta2, ..., deltaN]
        We process:       [delta1, delta2, ..., deltaN]  (first bar sets _prev_close)

        To match: seed avg_gain/avg_loss at 0.0, apply EWM including
        a phantom 0-gain/0-loss step, then report after period-1 real deltas
        (= period total including the phantom step).
        """
        alpha = 1.0 / self.period

        if self._count == 1:
            # Account for the phantom 0,0 step pandas sees at index 0
            # ewm(0.0) = 0.0, then ewm(gain) = alpha*gain + (1-alpha)*0 = alpha*gain
            self._avg_gain = alpha * gain
            self._avg_loss = alpha * loss
        else:
            self._avg_gain = alpha * gain + (1 - alpha) * self._avg_gain
            self._avg_loss = alpha * loss + (1 - alpha) * self._avg_loss

        # pandas min_periods=period: valid at index period-1 of gain/loss series
        # which corresponds to our count = period - 1 (since pandas has one extra 0-step)
        if self._count >= self.period - 1:
            if self._avg_loss == 0:
                self._value = 100.0
            else:
                rs = self._avg_gain / self._avg_loss
                self._value = 100 - (100 / (1 + rs))
            self._ready = True

    def _update_simple(self, gain: float, loss: float) -> None:
        """Simple rolling average RSI."""
        self._gains.append(gain)
        self._losses.append(loss)

        if len(self._gains) < self.period:
            return

        avg_gain = sum(self._gains) / self.period
        avg_loss = sum(self._losses) / self.period

        if avg_loss == 0:
            self._value = 100.0
        else:
            rs = avg_gain / avg_loss
            self._value = 100 - (100 / (1 + rs))

        self._ready = True

    def value(self) -> Optional[float]:
        return self._value

    @property
    def avg_gain(self) -> float:
        return self._avg_gain

    @property
    def avg_loss(self) -> float:
        return self._avg_loss

    def reset(self) -> None:
        super().reset()
        self._prev_close = None
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._value = None
        self._count = 0
        self._gains.clear()
        self._losses.clear()
