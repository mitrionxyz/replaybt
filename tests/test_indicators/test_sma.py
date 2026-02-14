"""Tests for SMA indicator."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.sma import SMA


def make_bars(prices):
    return [
        Bar(datetime(2024, 1, 1) + timedelta(minutes=i),
            p, p + 0.5, p - 0.5, p, 1000)
        for i, p in enumerate(prices)
    ]


class TestSMA:
    def test_warmup(self):
        sma = SMA("test", period=5)
        bars = make_bars([100, 101, 102, 103])
        for b in bars:
            sma.update(b)
        assert sma.ready is False

    def test_first_value_is_mean(self):
        sma = SMA("test", period=5)
        prices = [100, 101, 102, 103, 104]
        for b in make_bars(prices):
            sma.update(b)
        assert sma.ready is True
        assert sma.value() == pytest.approx(102.0)

    def test_rolling_window(self):
        sma = SMA("test", period=3)
        prices = [10, 20, 30, 40, 50]
        for b in make_bars(prices):
            sma.update(b)
        # Last 3: 30, 40, 50 → mean = 40
        assert sma.value() == pytest.approx(40.0)

    def test_matches_pandas_rolling(self):
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(100)) + 100
        period = 20

        batch = pd.Series(prices).rolling(window=period).mean()

        sma = SMA("test", period=period)
        inc_values = []
        for b in make_bars(prices.tolist()):
            sma.update(b)
            inc_values.append(sma.value())

        for i in range(period, len(prices)):
            assert inc_values[i] == pytest.approx(batch.iloc[i], abs=0.0001)
