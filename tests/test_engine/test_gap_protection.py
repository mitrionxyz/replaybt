"""Dedicated gap protection tests with synthetic data."""

import pytest
from datetime import datetime, timedelta

from replaybt.data.types import Bar, Position, Side
from replaybt.engine.execution import ExecutionModel


@pytest.fixture
def exec_model():
    return ExecutionModel(slippage=0.0002, taker_fee=0.00015)


class TestLongGapProtection:
    """LONG positions: verify gap-through behavior on open."""

    def test_sl_gap_through_returns_open_not_sl_level(self, exec_model):
        """If open gaps below SL, exit at open (worse fill), not SL level."""
        pos = Position(
            side=Side.LONG, entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000, stop_loss=97.0, take_profit=108.0,
        )
        # Open at 95 — well below SL of 97
        bar = Bar(datetime(2024, 1, 1, 0, 1), 95.0, 96.0, 94.0, 95.5, 1000)
        exit_price, reason = exec_model.check_exit(pos, bar)

        assert exit_price == 95.0  # Open, NOT 97
        assert "GAP" in reason

    def test_tp_gap_through_returns_open_not_tp_level(self, exec_model):
        """If open gaps above TP, exit at open (better fill)."""
        pos = Position(
            side=Side.LONG, entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000, stop_loss=97.0, take_profit=108.0,
        )
        # Open at 110 — above TP of 108
        bar = Bar(datetime(2024, 1, 1, 0, 1), 110.0, 112.0, 109.0, 111.0, 1000)
        exit_price, reason = exec_model.check_exit(pos, bar)

        assert exit_price == 110.0  # Open, not 108
        assert "TAKE_PROFIT_GAP" == reason

    def test_sl_hit_intrabar_returns_sl_level(self, exec_model):
        """Normal SL hit (low touches SL) exits at exact SL level."""
        pos = Position(
            side=Side.LONG, entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000, stop_loss=97.0, take_profit=108.0,
        )
        bar = Bar(datetime(2024, 1, 1, 0, 1), 98.0, 99.0, 96.5, 97.5, 1000)
        exit_price, reason = exec_model.check_exit(pos, bar)

        assert exit_price == 97.0  # Exact SL level
        assert reason == "STOP_LOSS"


class TestShortGapProtection:
    """SHORT positions: verify gap-through behavior on open."""

    def test_sl_gap_through_returns_open_not_sl_level(self, exec_model):
        """SHORT: open gaps above SL → exit at open."""
        pos = Position(
            side=Side.SHORT, entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000, stop_loss=103.0, take_profit=92.0,
        )
        bar = Bar(datetime(2024, 1, 1, 0, 1), 105.0, 106.0, 104.0, 105.5, 1000)
        exit_price, reason = exec_model.check_exit(pos, bar)

        assert exit_price == 105.0
        assert "GAP" in reason

    def test_tp_gap_through_returns_open_not_tp_level(self, exec_model):
        """SHORT: open gaps below TP → exit at open (better fill)."""
        pos = Position(
            side=Side.SHORT, entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000, stop_loss=103.0, take_profit=92.0,
        )
        bar = Bar(datetime(2024, 1, 1, 0, 1), 90.0, 91.0, 89.0, 90.5, 1000)
        exit_price, reason = exec_model.check_exit(pos, bar)

        assert exit_price == 90.0
        assert reason == "TAKE_PROFIT_GAP"

    def test_sl_hit_intrabar_returns_sl_level(self, exec_model):
        """SHORT: high touches SL → exit at SL level."""
        pos = Position(
            side=Side.SHORT, entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000, stop_loss=103.0, take_profit=92.0,
        )
        bar = Bar(datetime(2024, 1, 1, 0, 1), 102.0, 103.5, 101.0, 102.5, 1000)
        exit_price, reason = exec_model.check_exit(pos, bar)

        assert exit_price == 103.0
        assert reason == "STOP_LOSS"


class TestSLBeforeTP:
    """When both SL and TP could trigger, SL (checked first on open) wins."""

    def test_long_open_hits_both_sl_wins(self, exec_model):
        """LONG: open below SL (also below TP check) → SL gap takes priority."""
        pos = Position(
            side=Side.LONG, entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000, stop_loss=97.0, take_profit=108.0,
        )
        # Open well below SL
        bar = Bar(datetime(2024, 1, 1, 0, 1), 90.0, 91.0, 89.0, 90.5, 1000)
        exit_price, reason = exec_model.check_exit(pos, bar)

        assert exit_price == 90.0
        assert "STOP_LOSS" in reason
