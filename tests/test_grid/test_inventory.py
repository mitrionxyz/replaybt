"""Tests for InventoryTracker: position tracking, equity, drawdown, skew."""

import pytest

from replaybt.grid.inventory import InventoryTracker
from replaybt.grid.types import OrderSide


class TestRecordFill:
    def test_buy_increases_base(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.BID, size=1.0, price=100.0, spread_earned=0.1)

        assert inv.state.base_position == pytest.approx(1.0)
        assert inv.state.quote_position == pytest.approx(10_000.0 - 100.0)
        assert inv.state.total_base_bought == pytest.approx(1.0)
        assert inv.state.total_quote_spent == pytest.approx(100.0)

    def test_sell_decreases_base(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.ASK, size=1.0, price=100.0, spread_earned=0.1)

        assert inv.state.base_position == pytest.approx(-1.0)
        assert inv.state.quote_position == pytest.approx(10_000.0 + 100.0)
        assert inv.state.total_base_sold == pytest.approx(1.0)
        assert inv.state.total_quote_received == pytest.approx(100.0)

    def test_spread_accumulated(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.BID, size=1.0, price=100.0, spread_earned=0.5)
        inv.record_fill(OrderSide.ASK, size=1.0, price=101.0, spread_earned=0.5)

        assert inv.state.cumulative_spread_captured == pytest.approx(1.0)


class TestEquity:
    def test_get_equity_flat(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        # No position -> equity = quote only
        assert inv.get_equity(100.0) == pytest.approx(10_000.0)

    def test_get_equity_with_position(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.BID, size=1.0, price=100.0, spread_earned=0.0)
        # quote = 10000 - 100 = 9900, base = 1 * mid
        assert inv.get_equity(100.0) == pytest.approx(10_000.0)
        assert inv.get_equity(110.0) == pytest.approx(9_900.0 + 110.0)


class TestDrawdown:
    def test_no_drawdown_initially(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        assert inv.get_drawdown(100.0) == pytest.approx(0.0)

    def test_drawdown_from_peak(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        # Update peak at current equity
        inv.update_peak_equity(100.0)  # peak = 10000
        # Buy 1 at 100, then price drops to 90
        inv.record_fill(OrderSide.BID, size=1.0, price=100.0, spread_earned=0.0)
        # equity at 90 = 9900 + 90 = 9990
        dd = inv.get_drawdown(90.0)
        expected = 1.0 - 9990.0 / 10_000.0
        assert dd == pytest.approx(expected)

    def test_peak_updates(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        inv.update_peak_equity(100.0)
        assert inv.state.peak_equity == pytest.approx(10_000.0)

        inv.record_fill(OrderSide.BID, size=1.0, price=100.0, spread_earned=5.0)
        inv.update_peak_equity(110.0)
        # equity = 9900 + 110 = 10010, peak should update
        assert inv.state.peak_equity == pytest.approx(10_010.0)


class TestInventoryLimits:
    def test_can_buy_when_below_max(self):
        inv = InventoryTracker(max_inventory_base=5.0, initial_quote=10_000.0)
        assert inv.can_buy() is True

    def test_cannot_buy_at_max(self):
        inv = InventoryTracker(max_inventory_base=1.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.BID, size=1.0, price=100.0, spread_earned=0.0)
        assert inv.can_buy() is False

    def test_can_sell_when_above_neg_max(self):
        inv = InventoryTracker(max_inventory_base=5.0, initial_quote=10_000.0)
        assert inv.can_sell() is True

    def test_cannot_sell_at_neg_max(self):
        inv = InventoryTracker(max_inventory_base=1.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.ASK, size=1.0, price=100.0, spread_earned=0.0)
        assert inv.can_sell() is False


class TestSkew:
    def test_skew_zero_when_flat(self):
        inv = InventoryTracker(
            max_inventory_base=10.0,
            skew_factor=0.001,
            max_skew=0.05,
            initial_quote=10_000.0,
        )
        assert inv.get_skew() == pytest.approx(0.0)

    def test_skew_negative_when_long(self):
        inv = InventoryTracker(
            max_inventory_base=10.0,
            skew_factor=0.001,
            max_skew=0.05,
            initial_quote=10_000.0,
        )
        inv.record_fill(OrderSide.BID, size=5.0, price=100.0, spread_earned=0.0)
        skew = inv.get_skew()
        assert skew < 0  # shift down to encourage selling

    def test_skew_positive_when_short(self):
        inv = InventoryTracker(
            max_inventory_base=10.0,
            skew_factor=0.001,
            max_skew=0.05,
            initial_quote=10_000.0,
        )
        inv.record_fill(OrderSide.ASK, size=5.0, price=100.0, spread_earned=0.0)
        skew = inv.get_skew()
        assert skew > 0  # shift up to encourage buying

    def test_skew_clamped(self):
        inv = InventoryTracker(
            max_inventory_base=1.0,
            skew_factor=1.0,
            max_skew=0.01,
            initial_quote=10_000.0,
        )
        inv.record_fill(OrderSide.BID, size=1.0, price=100.0, spread_earned=0.0)
        skew = inv.get_skew()
        assert skew >= -0.01


class TestInventoryPct:
    def test_pct_zero_when_flat(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        assert inv.get_inventory_pct() == pytest.approx(0.0)

    def test_pct_at_max(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.BID, size=10.0, price=100.0, spread_earned=0.0)
        assert inv.get_inventory_pct() == pytest.approx(100.0)

    def test_signed_inventory(self):
        inv = InventoryTracker(max_inventory_base=10.0, initial_quote=10_000.0)
        inv.record_fill(OrderSide.ASK, size=5.0, price=100.0, spread_earned=0.0)
        assert inv.get_signed_inventory_pct() == pytest.approx(-0.5)
