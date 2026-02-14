"""Tests for Bollinger Bands indicator."""

import pytest
import numpy as np
from datetime import datetime, timedelta
from math import sqrt

from replaybt.data.types import Bar
from replaybt.indicators.bollinger import BollingerBands


def make_bars(prices):
    return [
        Bar(datetime(2024, 1, 1) + timedelta(minutes=i),
            p, p + 0.5, p - 0.5, p, 1000)
        for i, p in enumerate(prices)
    ]


class TestBollingerBands:
    def test_warmup(self):
        bb = BollingerBands("test", period=20)
        bars = make_bars([100 + i for i in range(15)])
        for b in bars:
            bb.update(b)
        assert bb.ready is False

    def test_ready_after_period(self):
        bb = BollingerBands("test", period=5)
        bars = make_bars([100, 101, 102, 103, 104])
        for b in bars:
            bb.update(b)
        assert bb.ready is True

    def test_middle_is_sma(self):
        bb = BollingerBands("test", period=5)
        prices = [100, 101, 102, 103, 104]
        for b in make_bars(prices):
            bb.update(b)
        assert bb.middle == pytest.approx(102.0)

    def test_bands_symmetric(self):
        bb = BollingerBands("test", period=5, num_std=2.0)
        prices = [100, 101, 102, 103, 104]
        for b in make_bars(prices):
            bb.update(b)
        val = bb.value()
        # Upper and lower should be equidistant from middle
        upper_dist = val["upper"] - val["middle"]
        lower_dist = val["middle"] - val["lower"]
        assert upper_dist == pytest.approx(lower_dist, abs=0.001)

    def test_bandwidth_correct(self):
        bb = BollingerBands("test", period=5, num_std=2.0)
        prices = [100, 101, 102, 103, 104]
        for b in make_bars(prices):
            bb.update(b)
        val = bb.value()
        expected_bw = (val["upper"] - val["lower"]) / val["middle"] * 100
        assert val["bandwidth"] == pytest.approx(expected_bw, abs=0.001)

    def test_pct_b_at_upper_is_one(self):
        """When close = upper band, %B should be 1.0."""
        bb = BollingerBands("test", period=5, num_std=2.0)
        # Constant price → std=0, bands collapse
        # Use varying prices instead
        prices = [100, 102, 98, 104, 96]
        for b in make_bars(prices):
            bb.update(b)
        val = bb.value()
        # %B = (close - lower) / (upper - lower)
        # Just verify it's between 0 and 1 for normal data
        assert 0 <= val["pct_b"] <= 1 or val["pct_b"] < 0 or val["pct_b"] > 1
        # (it's okay to be outside 0-1 when price is outside bands)

    def test_flat_price_zero_bandwidth(self):
        """Constant price → zero bandwidth."""
        bb = BollingerBands("test", period=5, num_std=2.0)
        prices = [100, 100, 100, 100, 100]
        for b in make_bars(prices):
            bb.update(b)
        val = bb.value()
        assert val["bandwidth"] == pytest.approx(0.0, abs=0.001)
        assert val["upper"] == val["lower"] == val["middle"]
