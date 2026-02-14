"""Tests for execution model: slippage, fees, gap protection."""

import pytest
from datetime import datetime

from replaybt.data.types import Bar, Position, Side
from replaybt.engine.execution import ExecutionModel


@pytest.fixture
def execution():
    return ExecutionModel(slippage=0.0002, taker_fee=0.00015, maker_fee=0.0)


class TestSlippage:
    def test_long_entry_slippage_is_adverse(self, execution):
        """LONG entry: price goes UP (you pay more)."""
        price = execution.apply_entry_slippage(100.0, Side.LONG)
        assert price > 100.0
        assert price == pytest.approx(100.02, abs=0.001)

    def test_short_entry_slippage_is_adverse(self, execution):
        """SHORT entry: price goes DOWN (you receive less)."""
        price = execution.apply_entry_slippage(100.0, Side.SHORT)
        assert price < 100.0
        assert price == pytest.approx(99.98, abs=0.001)

    def test_long_exit_slippage_is_adverse(self, execution):
        """LONG exit: price goes DOWN (you receive less)."""
        price = execution.apply_exit_slippage(100.0, Side.LONG)
        assert price < 100.0
        assert price == pytest.approx(99.98, abs=0.001)

    def test_short_exit_slippage_is_adverse(self, execution):
        """SHORT exit: price goes UP (you pay more)."""
        price = execution.apply_exit_slippage(100.0, Side.SHORT)
        assert price > 100.0
        assert price == pytest.approx(100.02, abs=0.001)


class TestFees:
    def test_taker_fee(self, execution):
        fee = execution.calc_fees(10_000.0, is_maker=False)
        assert fee == pytest.approx(1.50, abs=0.01)

    def test_maker_fee_is_zero(self, execution):
        fee = execution.calc_fees(10_000.0, is_maker=True)
        assert fee == 0.0


class TestGapProtection:
    """Test that exits use open price when it gaps past SL/TP."""

    def _make_position(self, side, entry=100.0, sl=None, tp=None):
        if side == Side.LONG:
            sl = sl or 95.0
            tp = tp or 110.0
        else:
            sl = sl or 105.0
            tp = tp or 90.0
        return Position(
            side=side,
            entry_price=entry,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000,
            stop_loss=sl,
            take_profit=tp,
        )

    def test_long_open_gaps_below_sl(self, execution):
        """LONG: open at 93 < SL at 95 → exit at open (93), not SL level."""
        pos = self._make_position(Side.LONG, sl=95.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=93.0, high=94.0, low=92.0, close=93.5,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 93.0  # Open price, NOT SL level
        assert reason == "STOP_LOSS_GAP"

    def test_long_intrabar_sl_hit(self, execution):
        """LONG: low touches SL but open is above → exit at SL level."""
        pos = self._make_position(Side.LONG, sl=95.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=96.0, high=97.0, low=94.5, close=95.5,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 95.0  # SL level
        assert reason == "STOP_LOSS"

    def test_long_open_gaps_above_tp(self, execution):
        """LONG: open at 112 > TP at 110 → exit at open (112)."""
        pos = self._make_position(Side.LONG, tp=110.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=112.0, high=113.0, low=111.0, close=112.5,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 112.0  # Open price, favorable gap
        assert reason == "TAKE_PROFIT_GAP"

    def test_long_intrabar_tp_hit(self, execution):
        """LONG: high touches TP but open is below → exit at TP level."""
        pos = self._make_position(Side.LONG, tp=110.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=109.0, high=110.5, low=108.0, close=110.0,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 110.0  # TP level
        assert reason == "TAKE_PROFIT"

    def test_short_open_gaps_above_sl(self, execution):
        """SHORT: open at 107 > SL at 105 → exit at open (107)."""
        pos = self._make_position(Side.SHORT, sl=105.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=107.0, high=108.0, low=106.0, close=107.5,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 107.0  # Open price
        assert reason == "STOP_LOSS_GAP"

    def test_short_intrabar_sl_hit(self, execution):
        """SHORT: high touches SL but open is below → exit at SL level."""
        pos = self._make_position(Side.SHORT, sl=105.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=104.0, high=105.5, low=103.0, close=104.5,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 105.0
        assert reason == "STOP_LOSS"

    def test_short_open_gaps_below_tp(self, execution):
        """SHORT: open at 88 < TP at 90 → exit at open (88)."""
        pos = self._make_position(Side.SHORT, tp=90.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=88.0, high=89.0, low=87.0, close=88.5,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 88.0
        assert reason == "TAKE_PROFIT_GAP"

    def test_no_exit_when_price_in_range(self, execution):
        """No exit when price stays between SL and TP."""
        pos = self._make_position(Side.LONG, sl=95.0, tp=110.0)
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=100.0, high=102.0, low=98.0, close=101.0,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price is None
        assert reason is None


class TestBreakeven:
    """Test breakeven trigger and lock."""

    def test_breakeven_activates_and_locks_sl(self, execution):
        """When price moves +1.5%, SL moves to entry + 0.5%."""
        pos = Position(
            side=Side.LONG,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000,
            stop_loss=96.5,
            take_profit=108.0,
            breakeven_trigger=0.015,
            breakeven_lock=0.005,
        )
        # Bar where high reaches +1.5%
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 1),
            open=101.0, high=101.6, low=100.8, close=101.2,
            volume=1000,
        )
        execution.check_exit(pos, bar)
        assert pos.breakeven_activated is True
        assert pos.stop_loss == pytest.approx(100.5, abs=0.01)

    def test_breakeven_gap_reason(self, execution):
        """After breakeven, gap below new SL → BREAKEVEN_GAP reason."""
        pos = Position(
            side=Side.LONG,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
            size_usd=10000,
            stop_loss=100.5,  # Already moved to breakeven
            take_profit=108.0,
            breakeven_activated=True,
            breakeven_trigger=0.015,
            breakeven_lock=0.005,
        )
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 0, 2),
            open=100.0, high=100.3, low=99.8, close=100.1,
            volume=1000,
        )
        exit_price, reason = execution.check_exit(pos, bar)
        assert exit_price == 100.0
        assert reason == "BREAKEVEN_GAP"
