"""Tests for CHOP indicator."""

import pytest
import numpy as np
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.chop import CHOP


def make_ohlc_bars(n, base=100, volatility=2.0):
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


class TestCHOP:
    def test_warmup(self):
        chop = CHOP("test", period=14)
        np.random.seed(42)
        bars = make_ohlc_bars(10)
        for b in bars:
            chop.update(b)
        assert chop.ready is False

    def test_ready_and_positive(self):
        chop = CHOP("test", period=14)
        np.random.seed(42)
        bars = make_ohlc_bars(20)
        for b in bars:
            chop.update(b)
        assert chop.ready is True
        assert chop.value() > 0

    def test_is_atr_over_price(self):
        """CHOP = ATR/Close * 100."""
        chop = CHOP("test", period=14)
        np.random.seed(42)
        bars = make_ohlc_bars(20)
        last_bar = None
        for b in bars:
            chop.update(b)
            last_bar = b

        atr_val = chop.atr_value
        expected = (atr_val / last_bar.close) * 100
        assert chop.value() == pytest.approx(expected, abs=0.001)

    def test_high_vol_gives_high_chop(self):
        """High volatility bars should produce higher CHOP."""
        np.random.seed(42)
        chop_low = CHOP("low_vol", period=5)
        chop_high = CHOP("high_vol", period=5)

        low_vol_bars = make_ohlc_bars(20, volatility=0.5)
        high_vol_bars = make_ohlc_bars(20, volatility=10.0)

        for b in low_vol_bars:
            chop_low.update(b)
        for b in high_vol_bars:
            chop_high.update(b)

        assert chop_high.value() > chop_low.value()
