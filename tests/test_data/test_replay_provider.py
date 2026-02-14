"""Tests for ReplayProvider."""

import time
from datetime import datetime, timedelta
from typing import Iterator, List
from unittest.mock import MagicMock

import pytest

from replaybt.data.types import Bar
from replaybt.data.providers.base import DataProvider
from replaybt.data.providers.replay import ReplayProvider


class _FakeProvider(DataProvider):
    """Minimal provider yielding N bars with configurable gaps."""

    def __init__(
        self,
        n: int = 10,
        gap_minutes: int = 1,
        symbol: str = "TEST",
        timeframe: str = "1m",
    ):
        self._n = n
        self._gap = gap_minutes
        self._symbol = symbol
        self._timeframe = timeframe

    def __iter__(self) -> Iterator[Bar]:
        base = datetime(2025, 1, 1)
        for i in range(self._n):
            yield Bar(
                timestamp=base + timedelta(minutes=i * self._gap),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1000.0,
                symbol=self._symbol,
                timeframe=self._timeframe,
            )

    def symbol(self) -> str:
        return self._symbol

    def timeframe(self) -> str:
        return self._timeframe


class TestReplayProvider:
    def test_speed_zero_no_delay(self):
        """speed=0 yields all bars with <0.1s total time."""
        inner = _FakeProvider(n=10, gap_minutes=1)
        provider = ReplayProvider(inner, speed=0)

        start = time.monotonic()
        bars = list(provider)
        elapsed = time.monotonic() - start

        assert len(bars) == 10
        assert elapsed < 0.1

    def test_speed_positive_delay(self):
        """speed=600 with 1m gaps: 10 bars take ~0.9s (9 gaps of 0.1s each)."""
        inner = _FakeProvider(n=10, gap_minutes=1)
        provider = ReplayProvider(inner, speed=600)

        start = time.monotonic()
        bars = list(provider)
        elapsed = time.monotonic() - start

        assert len(bars) == 10
        # 9 gaps * (60s / 600) = 9 * 0.1s = 0.9s
        assert 0.5 < elapsed < 2.0

    def test_first_bar_immediate(self):
        """First bar yields with no sleep."""
        inner = _FakeProvider(n=2, gap_minutes=1)
        provider = ReplayProvider(inner, speed=600)

        start = time.monotonic()
        it = iter(provider)
        first = next(it)
        first_elapsed = time.monotonic() - start

        assert first_elapsed < 0.05
        assert first.open == 100.0

    def test_gap_handling(self):
        """5-min gap at speed=300: sleeps ~1s (not 0.2s)."""
        inner = _FakeProvider(n=2, gap_minutes=5)
        provider = ReplayProvider(inner, speed=300)

        start = time.monotonic()
        bars = list(provider)
        elapsed = time.monotonic() - start

        assert len(bars) == 2
        # 1 gap * (300s / 300) = 1.0s
        assert 0.7 < elapsed < 1.5

    def test_delegates_symbol_timeframe(self):
        """Passes through to inner provider."""
        inner = _FakeProvider(symbol="ETH", timeframe="5m")
        provider = ReplayProvider(inner, speed=0)

        assert provider.symbol() == "ETH"
        assert provider.timeframe() == "5m"

    def test_on_bar_callback(self):
        """Callback invoked with each bar."""
        inner = _FakeProvider(n=5)
        received: List[Bar] = []
        provider = ReplayProvider(inner, speed=0, on_bar=received.append)

        bars = list(provider)

        assert len(received) == 5
        assert received == bars

    def test_wraps_csv_provider_interface(self):
        """Works with any DataProvider transparently (via _FakeProvider)."""
        inner = _FakeProvider(n=3)
        provider = ReplayProvider(inner, speed=0)

        bars = list(provider)
        assert len(bars) == 3
        # Verify bars come through unmodified
        assert bars[0].open == 100.0
        assert bars[1].open == 101.0
        assert bars[2].open == 102.0

    def test_reset_delegates(self):
        """reset() calls inner provider's reset()."""
        inner = _FakeProvider(n=3)
        inner.reset = MagicMock()
        provider = ReplayProvider(inner, speed=0)

        provider.reset()
        inner.reset.assert_called_once()
