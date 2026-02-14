"""Tests for VWAP and OBV indicators."""

import pytest
from datetime import datetime, timedelta

from replaybt.data.types import Bar
from replaybt.indicators.vwap import VWAP
from replaybt.indicators.obv import OBV


class TestVWAP:
    def test_single_bar(self):
        vwap = VWAP("test")
        bar = Bar(datetime(2024, 1, 1, 10, 0), 100, 102, 98, 101, 1000)
        vwap.update(bar)
        assert vwap.ready is True
        # TP = (102 + 98 + 101) / 3 = 100.333...
        assert vwap.value() == pytest.approx(100.333, abs=0.01)

    def test_volume_weighted(self):
        vwap = VWAP("test")
        # High volume bar at high price should pull VWAP up
        vwap.update(Bar(datetime(2024, 1, 1, 10, 0), 100, 102, 98, 100, 100))
        vwap.update(Bar(datetime(2024, 1, 1, 10, 1), 100, 110, 100, 108, 10000))
        # Second bar has 100x volume at higher price — VWAP should be near it
        assert vwap.value() > 105

    def test_daily_reset(self):
        vwap = VWAP("test")
        # Day 1
        vwap.update(Bar(datetime(2024, 1, 1, 23, 59), 100, 102, 98, 100, 1000))
        v1 = vwap.value()
        # Day 2 — different price level
        vwap.update(Bar(datetime(2024, 1, 2, 0, 0), 200, 202, 198, 200, 1000))
        v2 = vwap.value()
        # After reset, VWAP should be near day 2 price, not blended with day 1
        assert v2 > 195


class TestOBV:
    def test_up_close_adds_volume(self):
        obv = OBV("test")
        obv.update(Bar(datetime(2024, 1, 1, 0, 0), 100, 101, 99, 100, 1000))
        obv.update(Bar(datetime(2024, 1, 1, 0, 1), 100, 102, 99, 101, 500))
        # Close went up (100→101) → add volume
        assert obv.value() == 500

    def test_down_close_subtracts_volume(self):
        obv = OBV("test")
        obv.update(Bar(datetime(2024, 1, 1, 0, 0), 100, 101, 99, 100, 1000))
        obv.update(Bar(datetime(2024, 1, 1, 0, 1), 100, 101, 98, 99, 500))
        # Close went down (100→99) → subtract volume
        assert obv.value() == -500

    def test_flat_close_no_change(self):
        obv = OBV("test")
        obv.update(Bar(datetime(2024, 1, 1, 0, 0), 100, 101, 99, 100, 1000))
        obv.update(Bar(datetime(2024, 1, 1, 0, 1), 100, 101, 99, 100, 500))
        # Close unchanged → no volume change
        assert obv.value() == 0

    def test_cumulative(self):
        obv = OBV("test")
        obv.update(Bar(datetime(2024, 1, 1, 0, 0), 100, 101, 99, 100, 1000))
        obv.update(Bar(datetime(2024, 1, 1, 0, 1), 100, 102, 99, 101, 500))  # +500
        obv.update(Bar(datetime(2024, 1, 1, 0, 2), 101, 103, 100, 102, 300))  # +300
        obv.update(Bar(datetime(2024, 1, 1, 0, 3), 102, 103, 100, 99, 200))   # -200
        assert obv.value() == 600  # 500 + 300 - 200
