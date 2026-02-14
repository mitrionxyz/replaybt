"""Tests for MACD indicator."""

import pytest
import numpy as np
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.macd import MACD


def make_bars(prices):
    return [
        Bar(datetime(2024, 1, 1) + timedelta(minutes=i),
            p, p + 0.5, p - 0.5, p, 1000)
        for i, p in enumerate(prices)
    ]


class TestMACD:
    def test_warmup(self):
        macd = MACD("test", fast_period=12, slow_period=26, signal_period=9)
        prices = [100 + i * 0.1 for i in range(20)]
        for b in make_bars(prices):
            macd.update(b)
        assert macd.ready is False

    def test_ready_after_slow_plus_signal(self):
        macd = MACD("test", fast_period=3, slow_period=5, signal_period=3)
        prices = [100 + i * 0.5 for i in range(15)]
        for b in make_bars(prices):
            macd.update(b)
        assert macd.ready is True

    def test_uptrend_positive_macd(self):
        """In an uptrend, fast EMA > slow EMA → MACD line positive."""
        macd = MACD("test", fast_period=5, slow_period=10, signal_period=3)
        prices = [100 + i * 2.0 for i in range(30)]
        for b in make_bars(prices):
            macd.update(b)
        val = macd.value()
        assert val["macd"] > 0

    def test_downtrend_negative_macd(self):
        """In a downtrend, fast EMA < slow EMA → MACD line negative."""
        macd = MACD("test", fast_period=5, slow_period=10, signal_period=3)
        prices = [200 - i * 2.0 for i in range(30)]
        for b in make_bars(prices):
            macd.update(b)
        val = macd.value()
        assert val["macd"] < 0

    def test_histogram_is_macd_minus_signal(self):
        macd = MACD("test", fast_period=5, slow_period=10, signal_period=3)
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(30)) + 100
        for b in make_bars(prices.tolist()):
            macd.update(b)
        val = macd.value()
        assert val["histogram"] == pytest.approx(
            val["macd"] - val["signal"], abs=0.0001
        )

    def test_all_keys_present(self):
        macd = MACD("test", fast_period=3, slow_period=5, signal_period=3)
        prices = [100 + i for i in range(15)]
        for b in make_bars(prices):
            macd.update(b)
        val = macd.value()
        assert "macd" in val
        assert "signal" in val
        assert "histogram" in val
