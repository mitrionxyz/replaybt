"""Tests for RSI — Wilder's vs Simple, incremental vs batch."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.rsi import RSI
from replaybt.indicators.base import Indicator


def make_close_bars(prices):
    return [
        Bar(
            timestamp=datetime(2024, 1, 1) + timedelta(minutes=i),
            open=p, high=p + 0.5, low=p - 0.5, close=p,
            volume=1000,
        )
        for i, p in enumerate(prices)
    ]


class TestRSIWilder:
    def test_warmup(self):
        """RSI should not be ready until enough bars processed."""
        rsi = RSI("test", period=7, mode="wilder")
        # 6 bars = 5 deltas, need period-1=6 deltas to be ready
        bars = make_close_bars([100 + i for i in range(6)])
        for b in bars:
            rsi.update(b)
        assert rsi.ready is False

    def test_ready_after_warmup(self):
        """RSI becomes ready after period+1 bars."""
        rsi = RSI("test", period=7, mode="wilder")
        bars = make_close_bars([100 + i * 0.5 for i in range(9)])
        for b in bars:
            rsi.update(b)
        assert rsi.ready is True
        # In an uptrend, RSI should be > 50
        assert rsi.value() > 50

    def test_overbought_in_strong_uptrend(self):
        """Strong uptrend → RSI close to 100."""
        rsi = RSI("test", period=7, mode="wilder")
        prices = [100 + i * 2.0 for i in range(30)]
        bars = make_close_bars(prices)
        for b in bars:
            rsi.update(b)
        assert rsi.value() > 90

    def test_oversold_in_strong_downtrend(self):
        """Strong downtrend → RSI close to 0."""
        rsi = RSI("test", period=7, mode="wilder")
        prices = [200 - i * 2.0 for i in range(30)]
        bars = make_close_bars(prices)
        for b in bars:
            rsi.update(b)
        assert rsi.value() < 10

    def test_matches_batch_wilder(self):
        """Incremental Wilder RSI must match batch calculation."""
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(200)) + 100
        period = 7

        # Batch (same formula as backtest_combined_clean.py)
        series = pd.Series(prices)
        delta = series.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss
        batch_rsi = 100 - (100 / (1 + rs))

        # Incremental
        rsi = RSI("test", period=period, mode="wilder")
        bars = make_close_bars(prices.tolist())
        inc_values = []
        for b in bars:
            rsi.update(b)
            inc_values.append(rsi.value())

        # Compare from period+1 onward (where both are valid)
        # Note: batch RSI has period NaN values at start, then becomes valid
        for i in range(period + 1, len(prices)):
            if inc_values[i] is not None and pd.notna(batch_rsi.iloc[i]):
                assert inc_values[i] == pytest.approx(
                    batch_rsi.iloc[i], abs=0.5
                ), f"Mismatch at index {i}: inc={inc_values[i]}, batch={batch_rsi.iloc[i]}"


class TestRSISimple:
    def test_simple_rsi_matches_batch(self):
        """Incremental Simple RSI must match batch rolling calculation."""
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(100)) + 100
        period = 7

        # Batch
        series = pd.Series(prices)
        delta = series.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        batch_rsi = 100 - (100 / (1 + rs))

        # Incremental
        rsi = RSI("test", period=period, mode="simple")
        bars = make_close_bars(prices.tolist())
        inc_values = []
        for b in bars:
            rsi.update(b)
            inc_values.append(rsi.value())

        # Compare where both are valid
        for i in range(period + 2, len(prices)):
            if inc_values[i] is not None and pd.notna(batch_rsi.iloc[i]):
                assert inc_values[i] == pytest.approx(
                    batch_rsi.iloc[i], abs=0.5
                ), f"Mismatch at index {i}"


class TestRSIModes:
    def test_wilder_and_simple_differ(self):
        """Wilder's and Simple RSI should produce different values."""
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(50)) + 100

        rsi_w = RSI("wilder", period=7, mode="wilder")
        rsi_s = RSI("simple", period=7, mode="simple")

        bars = make_close_bars(prices.tolist())
        for b in bars:
            rsi_w.update(b)
            rsi_s.update(b)

        # Both should be ready and produce different values
        assert rsi_w.ready and rsi_s.ready
        assert rsi_w.value() != rsi_s.value()
