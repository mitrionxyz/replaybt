"""Tests for PositionSizer implementations."""

import pytest
from replaybt.sizing import FixedSizer, EquityPctSizer, RiskPctSizer, KellySizer, PositionSizer


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
        assert issubclass(KellySizer, PositionSizer)


class TestKellySizer:

    def test_basic_kelly(self):
        # 65% WR, 8% avg win, 3.5% avg loss
        # payoff_ratio = 0.08 / 0.035 = 2.2857
        # kelly = 0.65 - 0.35 / 2.2857 = 0.65 - 0.1531 = 0.4969
        # quarter kelly = 0.4969 * 0.25 = 0.1242
        # size = 10000 * 0.1242 = 1242.35
        sizer = KellySizer(win_rate=0.65, avg_win=0.08, avg_loss=0.035, fraction=0.25)
        size = sizer.get_size(equity=10000, side="LONG", price=100)
        assert abs(size - 1242.35) < 1

    def test_kelly_fraction_property(self):
        sizer = KellySizer(win_rate=0.60, avg_win=0.10, avg_loss=0.05)
        # payoff_ratio = 0.10 / 0.05 = 2.0
        # kelly = 0.60 - 0.40 / 2.0 = 0.60 - 0.20 = 0.40
        assert abs(sizer.kelly_fraction - 0.40) < 0.001

    def test_half_kelly(self):
        # f* = 0.40, half kelly = 0.20
        # size = 50000 * 0.20 = 10000
        sizer = KellySizer(win_rate=0.60, avg_win=0.10, avg_loss=0.05, fraction=0.50)
        size = sizer.get_size(equity=50000, side="LONG", price=100)
        assert size == 10000

    def test_no_edge_returns_min_size(self):
        # 40% WR, 5% avg win, 5% avg loss
        # payoff_ratio = 1.0
        # kelly = 0.40 - 0.60 / 1.0 = -0.20  (negative = no edge)
        sizer = KellySizer(win_rate=0.40, avg_win=0.05, avg_loss=0.05, min_size=200)
        size = sizer.get_size(equity=10000, side="LONG", price=100)
        assert size == 200

    def test_max_equity_pct_cap(self):
        # Strong edge: 80% WR, 10% win, 5% loss
        # kelly = 0.80 - 0.20 / 2.0 = 0.70
        # full kelly size = 50000 * 0.70 = 35000
        # but max_equity_pct=0.25 → 50000 * 0.25 = 12500
        sizer = KellySizer(
            win_rate=0.80, avg_win=0.10, avg_loss=0.05,
            fraction=1.0, max_equity_pct=0.25,
        )
        size = sizer.get_size(equity=50000, side="LONG", price=100)
        assert size == 12500

    def test_max_size_cap(self):
        sizer = KellySizer(
            win_rate=0.65, avg_win=0.08, avg_loss=0.035,
            fraction=0.50, max_size=3000,
        )
        size = sizer.get_size(equity=100000, side="LONG", price=100)
        assert size == 3000

    def test_min_size_floor(self):
        sizer = KellySizer(
            win_rate=0.55, avg_win=0.02, avg_loss=0.01,
            fraction=0.10, min_size=500,
        )
        # Small kelly, small fraction, small equity → clamped to min
        size = sizer.get_size(equity=1000, side="LONG", price=100)
        assert size == 500

    def test_scales_with_equity(self):
        sizer = KellySizer(win_rate=0.65, avg_win=0.08, avg_loss=0.035, fraction=0.25)
        size_10k = sizer.get_size(equity=10000, side="LONG", price=100)
        size_20k = sizer.get_size(equity=20000, side="LONG", price=100)
        assert abs(size_20k - 2 * size_10k) < 1

    def test_invalid_win_rate(self):
        with pytest.raises(ValueError, match="win_rate"):
            KellySizer(win_rate=0.0)
        with pytest.raises(ValueError, match="win_rate"):
            KellySizer(win_rate=1.0)

    def test_invalid_avg_win(self):
        with pytest.raises(ValueError, match="avg_win"):
            KellySizer(avg_win=0.0)

    def test_invalid_avg_loss(self):
        with pytest.raises(ValueError, match="avg_loss"):
            KellySizer(avg_loss=-0.01)
