"""Tests for PositionSizer implementations."""

import pytest
from replaybt.sizing import FixedSizer, EquityPctSizer, RiskPctSizer, PositionSizer


class TestFixedSizer:

    def test_returns_fixed_size(self):
        sizer = FixedSizer(size_usd=5000)
        assert sizer.get_size(equity=10000, side="LONG", price=100) == 5000

    def test_ignores_equity(self):
        sizer = FixedSizer(size_usd=10000)
        assert sizer.get_size(equity=50000, side="LONG", price=200) == 10000
        assert sizer.get_size(equity=1000, side="SHORT", price=50) == 10000

    def test_default_size(self):
        sizer = FixedSizer()
        assert sizer.get_size(equity=10000, side="LONG", price=100) == 10000


class TestEquityPctSizer:

    def test_basic_percentage(self):
        sizer = EquityPctSizer(pct=0.10)
        assert sizer.get_size(equity=50000, side="LONG", price=100) == 5000

    def test_min_size(self):
        sizer = EquityPctSizer(pct=0.01, min_size=500)
        # 1% of 10000 = 100, but min is 500
        assert sizer.get_size(equity=10000, side="LONG", price=100) == 500

    def test_max_size(self):
        sizer = EquityPctSizer(pct=0.50, max_size=20000)
        # 50% of 100000 = 50000, capped at 20000
        assert sizer.get_size(equity=100000, side="LONG", price=100) == 20000

    def test_no_max_cap(self):
        sizer = EquityPctSizer(pct=0.50, max_size=0)
        assert sizer.get_size(equity=100000, side="LONG", price=100) == 50000


class TestRiskPctSizer:

    def test_basic_risk_sizing(self):
        sizer = RiskPctSizer(risk_pct=0.01)
        # 1% of 10000 / 0.035 (default SL) = ~2857.14
        size = sizer.get_size(equity=10000, side="LONG", price=100)
        assert abs(size - 2857.14) < 1

    def test_with_explicit_sl(self):
        sizer = RiskPctSizer(risk_pct=0.02)
        # 2% of 50000 / 0.05 = 20000
        size = sizer.get_size(
            equity=50000, side="LONG", price=100, stop_loss_pct=0.05,
        )
        assert size == 20000

    def test_min_size(self):
        sizer = RiskPctSizer(risk_pct=0.001, min_size=500)
        # 0.1% of 10000 / 0.035 = ~28.57, clamped to 500
        size = sizer.get_size(equity=10000, side="LONG", price=100)
        assert size == 500

    def test_max_size(self):
        sizer = RiskPctSizer(risk_pct=0.05, max_size=10000, default_sl_pct=0.01)
        # 5% of 100000 / 0.01 = 500000, capped at 10000
        size = sizer.get_size(equity=100000, side="LONG", price=100)
        assert size == 10000

    def test_fallback_to_default_sl(self):
        sizer = RiskPctSizer(risk_pct=0.01, default_sl_pct=0.05)
        # stop_loss_pct=0 → use default 5%
        size = sizer.get_size(
            equity=10000, side="LONG", price=100, stop_loss_pct=0,
        )
        # 1% of 10000 / 0.05 = 2000
        assert size == 2000

    def test_is_position_sizer(self):
        assert issubclass(RiskPctSizer, PositionSizer)
        assert issubclass(EquityPctSizer, PositionSizer)
        assert issubclass(FixedSizer, PositionSizer)
