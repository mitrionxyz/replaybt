"""Tests for ATR indicator."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.atr import ATR


def make_ohlc_bars(n, base=100, volatility=2.0):
    """Generate bars with realistic OHLC relationships."""
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


class TestATR:
    def test_warmup(self):
        atr = ATR("test", period=14)
        np.random.seed(42)
        bars = make_ohlc_bars(10)
        for b in bars:
            atr.update(b)
        assert atr.ready is False

    def test_ready_after_period(self):
        atr = ATR("test", period=14)
        np.random.seed(42)
        bars = make_ohlc_bars(20)
        for b in bars:
            atr.update(b)
        assert atr.ready is True
        assert atr.value() > 0

    def test_atr_positive(self):
        atr = ATR("test", period=5)
        np.random.seed(42)
        bars = make_ohlc_bars(20)
        for b in bars:
            atr.update(b)
        assert atr.value() > 0

    def test_sma_matches_pandas(self):
        """SMA ATR should match pandas rolling TR mean."""
        np.random.seed(42)
        bars = make_ohlc_bars(50)
        period = 14

        # Batch: compute TR and rolling mean
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]

        tr_list = [highs[0] - lows[0]]  # First bar
        for i in range(1, len(bars)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_list.append(tr)

        batch_atr = pd.Series(tr_list).rolling(window=period).mean()

        # Incremental
        atr = ATR("test", period=period, mode="sma")
        inc_values = []
        for b in bars:
            atr.update(b)
            inc_values.append(atr.value())

        for i in range(period, len(bars)):
            assert inc_values[i] == pytest.approx(batch_atr.iloc[i], abs=0.001)

    def test_wilder_mode(self):
        atr = ATR("test", period=14, mode="wilder")
        np.random.seed(42)
        bars = make_ohlc_bars(30)
        for b in bars:
            atr.update(b)
        assert atr.ready is True
        assert atr.value() > 0
