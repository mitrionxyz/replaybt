"""Tests for Stochastic Oscillator."""

import pytest
import numpy as np
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.stochastic import Stochastic


def make_ohlc_bars(n, base=100, volatility=2.0):
    np.random.seed(42)
    bars = []
    price = base
    for i in range(n):
        move = np.random.randn() * volatility
        o = price
        c = price + move
        h = max(o, c) + abs(np.random.randn()) * volatility * 0.5
        l = min(o, c) - abs(np.random.randn()) * volatility * 0.5
        bars.append(Bar(
            datetime(2024, 1, 1) + timedelta(minutes=i),
            o, h, l, c, 1000,
        ))
        price = c
    return bars


class TestStochastic:
    def test_warmup(self):
        stoch = Stochastic("test", k_period=14, d_period=3, smooth_k=3)
        bars = make_ohlc_bars(10)
        for b in bars:
            stoch.update(b)
        assert stoch.ready is False

    def test_ready_after_enough_bars(self):
        stoch = Stochastic("test", k_period=5, d_period=3, smooth_k=1)
        bars = make_ohlc_bars(20)
        for b in bars:
            stoch.update(b)
        assert stoch.ready is True

    def test_range_0_to_100(self):
        """Stochastic %K should be between 0 and 100."""
        stoch = Stochastic("test", k_period=14, d_period=3, smooth_k=3)
        bars = make_ohlc_bars(50)
        for b in bars:
            stoch.update(b)
        assert 0 <= stoch.k <= 100
        assert 0 <= stoch.d <= 100

    def test_all_up_gives_high_k(self):
        """Monotonic uptrend → %K near 100."""
        stoch = Stochastic("test", k_period=5, d_period=3, smooth_k=1)
        prices_up = [100 + i * 3.0 for i in range(20)]
        bars = [
            Bar(datetime(2024, 1, 1) + timedelta(minutes=i),
                p, p + 1, p - 0.1, p + 0.5, 1000)
            for i, p in enumerate(prices_up)
        ]
        for b in bars:
            stoch.update(b)
        assert stoch.k > 80

    def test_keys_present(self):
        stoch = Stochastic("test", k_period=5, d_period=3, smooth_k=1)
        bars = make_ohlc_bars(20)
        for b in bars:
            stoch.update(b)
        val = stoch.value()
        assert "k" in val
        assert "d" in val
