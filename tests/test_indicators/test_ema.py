"""Tests for EMA indicator — incremental vs batch."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.ema import EMA
from replaybt.indicators.base import Indicator


def make_close_bars(prices):
    """Create bars from a list of close prices."""
    return [
        Bar(
            timestamp=datetime(2024, 1, 1) + timedelta(minutes=i),
            open=p, high=p + 0.5, low=p - 0.5, close=p,
            volume=1000,
        )
        for i, p in enumerate(prices)
    ]


class TestEMAIncremental:
    def test_ema_warmup(self):
        """EMA should not be ready until period bars are processed."""
        ema = EMA("test", period=5)
        bars = make_close_bars([100, 101, 102, 103])  # Only 4 bars
        for b in bars:
            ema.update(b)
        assert ema.ready is False
        # Value is tracked internally but not "ready" for strategy use
        # (matches pandas ewm which computes from bar 0)

    def test_ema_ready_after_period(self):
        """EMA becomes ready after exactly period bars."""
        ema = EMA("test", period=5)
        bars = make_close_bars([100, 101, 102, 103, 104])
        for b in bars:
            ema.update(b)
        assert ema.ready is True
        assert ema.value() is not None
        # Value should be close to the mean (pandas ewm style seeding)
        assert 100 < ema.value() < 105

    def test_ema_tracks_trend(self):
        """EMA should follow an uptrend."""
        ema = EMA("test", period=5)
        prices = [100 + i * 0.5 for i in range(20)]
        bars = make_close_bars(prices)
        for b in bars:
            ema.update(b)
        # EMA should be close to but lagging behind the last price
        assert ema.value() < prices[-1]
        assert ema.value() > prices[0]


class TestEMABatchVsIncremental:
    """Verify incremental EMA matches pandas ewm batch calculation."""

    def test_matches_pandas_ewm(self):
        """Incremental EMA must produce same values as pandas ewm."""
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(100)) + 100
        period = 14

        # Batch (pandas)
        series = pd.Series(prices)
        batch_ema = series.ewm(span=period, adjust=False).mean()

        # Incremental
        ema = EMA("test", period=period)
        bars = make_close_bars(prices.tolist())
        incremental_values = []
        for b in bars:
            ema.update(b)
            incremental_values.append(ema.value())

        # Compare from period onward (where both are valid)
        for i in range(period, len(prices)):
            assert incremental_values[i] == pytest.approx(
                batch_ema.iloc[i], abs=0.0001
            ), f"Mismatch at index {i}"

    def test_reset_works(self):
        """After reset, EMA should start fresh."""
        ema = EMA("test", period=5)
        bars = make_close_bars([100, 101, 102, 103, 104, 105])
        for b in bars:
            ema.update(b)
        v1 = ema.value()

        ema.reset()
        assert ema.ready is False
        assert ema.value() is None

        for b in bars:
            ema.update(b)
        assert ema.value() == pytest.approx(v1, abs=0.0001)
