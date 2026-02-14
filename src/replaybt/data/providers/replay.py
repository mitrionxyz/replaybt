"""ReplayProvider: wall-clock throttled bar delivery for visualization."""

from __future__ import annotations

import time
from typing import Callable, Iterator, Optional

from ..types import Bar
from .base import DataProvider


class ReplayProvider(DataProvider):
    """Wraps any DataProvider and injects time.sleep() between bar yields.

    Delays are proportional to timestamp gaps between consecutive bars,
    scaled by the speed factor. This simulates real-time bar arrival
    for visualization or live-replay workflows.

    Args:
        inner: The underlying DataProvider to wrap.
        speed: Playback speed multiplier.
            0 = instant (no delay, same as bare provider).
            1 = real-time (1m bar = 60s delay).
            60 = 60x speed (1m bar = 1s delay).
        on_bar: Optional callback invoked with each bar before yield.
    """

    def __init__(
        self,
        inner: DataProvider,
        speed: float = 60,
        on_bar: Optional[Callable[[Bar], None]] = None,
    ):
        self._inner = inner
        self._speed = speed
        self._on_bar = on_bar

    def __iter__(self) -> Iterator[Bar]:
        prev_ts = None
        for bar in self._inner:
            if self._speed > 0 and prev_ts is not None:
                gap = (bar.timestamp - prev_ts).total_seconds()
                if gap > 0:
                    time.sleep(gap / self._speed)
            prev_ts = bar.timestamp
            if self._on_bar:
                self._on_bar(bar)
            yield bar

    def symbol(self) -> str:
        return self._inner.symbol()

    def timeframe(self) -> str:
        return self._inner.timeframe()

    def reset(self) -> None:
        self._inner.reset()
