"""Tests for GridManager: fill logic, ping-pong, cancel, _open_ids tracking."""

from datetime import datetime

import pytest

from replaybt.grid.manager import GridLevel, GridManager
from replaybt.grid.types import OrderSide, OrderStatus


def _make_levels(mid: float, spread: float, n: int = 3) -> list[GridLevel]:
    """Create n bid + n ask levels symmetrically around mid."""
    levels = []
    step = spread * mid
    for i in range(1, n + 1):
        bid_price = mid - step * i
        ask_price = mid + step * i
        levels.append(GridLevel(price=bid_price, size=0.1, side="bid"))
        levels.append(GridLevel(price=ask_price, size=0.1, side="ask"))
    return levels


class TestPlaceGrid:
    def test_place_grid_counts(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = _make_levels(100.0, 0.001, n=5)
        mgr.place_grid(levels, bar_index=0)

        counts = mgr.count_open()
        assert counts["bid"] == 5
        assert counts["ask"] == 5
        assert len(mgr._open_ids) == 10

    def test_place_grid_prices(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = _make_levels(100.0, 0.001, n=3)
        mgr.place_grid(levels, bar_index=0)

        bid_prices = mgr.get_open_order_prices(OrderSide.BID)
        ask_prices = mgr.get_open_order_prices(OrderSide.ASK)
        # Bids should be descending
        assert bid_prices == sorted(bid_prices, reverse=True)
        # Asks should be ascending
        assert ask_prices == sorted(ask_prices)
        # All bids below mid, all asks above mid
        assert all(p < 100.0 for p in bid_prices)
        assert all(p > 100.0 for p in ask_prices)


class TestCheckFills:
    def test_bid_fill(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=99.0, size=0.1, side="bid")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=98.5, candle_high=100.0, candle_open=99.5, bar_index=1
        )
        assert len(fills) == 1
        assert fills[0].side == OrderSide.BID
        assert fills[0].price == 99.0
        assert fills[0].size == 0.1

    def test_ask_fill(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=101.0, size=0.1, side="ask")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=99.0, candle_high=101.5, candle_open=100.0, bar_index=1
        )
        assert len(fills) == 1
        assert fills[0].side == OrderSide.ASK
        assert fills[0].price == 101.0

    def test_no_fill_when_not_touched(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=95.0, size=0.1, side="bid")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=99.0, candle_high=101.0, candle_open=100.0, bar_index=1
        )
        assert len(fills) == 0

    def test_gap_protection_bid(self):
        """Open gaps below bid -> fill at open (worse for buyer)."""
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=99.0, size=0.1, side="bid")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=97.0, candle_high=98.5, candle_open=98.0, bar_index=1
        )
        assert len(fills) == 1
        assert fills[0].price == 98.0  # filled at open, not at order price

    def test_gap_protection_ask(self):
        """Open gaps above ask -> fill at open."""
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=101.0, size=0.1, side="ask")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=101.5, candle_high=103.0, candle_open=102.0, bar_index=1
        )
        assert len(fills) == 1
        assert fills[0].price == 102.0

    def test_slippage_applied(self):
        mgr = GridManager(
            spread_pct=0.001, slippage_pct=0.01
        )  # 1% slippage for clarity
        levels = [GridLevel(price=100.0, size=0.1, side="bid")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=99.0, candle_high=101.0, candle_open=100.5, bar_index=1
        )
        assert len(fills) == 1
        expected = 100.0 - 100.0 * 0.01
        assert fills[0].price == pytest.approx(expected)

    def test_spread_earned(self):
        mgr = GridManager(spread_pct=0.002, slippage_pct=0.0, maker_fee_pct=0.0)
        levels = [GridLevel(price=100.0, size=1.0, side="bid")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=99.0, candle_high=101.0, candle_open=100.5, bar_index=1
        )
        # spread_earned = half_spread * size = (100 * 0.002) * 1.0 = 0.2
        assert fills[0].spread_earned == pytest.approx(0.2)

    def test_filled_order_removed_from_open(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=99.0, size=0.1, side="bid")]
        mgr.place_grid(levels)
        assert len(mgr._open_ids) == 1

        mgr.check_fills(
            candle_low=98.0, candle_high=100.0, candle_open=99.5, bar_index=1
        )
        assert len(mgr._open_ids) == 0
        assert mgr.orders[0].status == OrderStatus.FILLED

    def test_timestamp_passed_through(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=99.0, size=0.1, side="bid")]
        mgr.place_grid(levels)

        ts = datetime(2024, 6, 15, 12, 0)
        fills = mgr.check_fills(
            candle_low=98.0,
            candle_high=100.0,
            candle_open=99.5,
            bar_index=1,
            timestamp=ts,
        )
        assert fills[0].timestamp == ts


class TestPingPong:
    def test_bid_fill_places_ask(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=99.0, size=0.1, side="bid")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=98.0, candle_high=100.0, candle_open=99.5, bar_index=1
        )
        pp = mgr.place_pingpong(fills[0], mid_price=100.0, bar_index=1)

        assert pp is not None
        assert pp.side == OrderSide.ASK
        assert pp.is_pingpong is True
        assert pp.size == 0.1
        # Ask at fill_price + full_spread = 99.0 + 2*100*0.001 = 99.0 + 0.2 = 99.2
        assert pp.price == pytest.approx(99.0 + 100.0 * 0.001 * 2)

    def test_ask_fill_places_bid(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        levels = [GridLevel(price=101.0, size=0.1, side="ask")]
        mgr.place_grid(levels)

        fills = mgr.check_fills(
            candle_low=99.0, candle_high=102.0, candle_open=100.5, bar_index=1
        )
        pp = mgr.place_pingpong(fills[0], mid_price=100.0, bar_index=1)

        assert pp is not None
        assert pp.side == OrderSide.BID
        assert pp.is_pingpong is True


class TestCancel:
    def test_cancel_all(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        mgr.place_grid(_make_levels(100.0, 0.001, n=5))
        assert len(mgr._open_ids) == 10

        mgr.cancel_all()
        assert len(mgr._open_ids) == 0
        for order in mgr.orders.values():
            assert order.status == OrderStatus.CANCELLED

    def test_cancel_side(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        mgr.place_grid(_make_levels(100.0, 0.001, n=3))

        mgr.cancel_side(OrderSide.BID)
        counts = mgr.count_open()
        assert counts["bid"] == 0
        assert counts["ask"] == 3

    def test_cancel_non_pingpong(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        mgr.place_grid(_make_levels(100.0, 0.001, n=3))

        # Create a fill and place a ping-pong
        fills = mgr.check_fills(
            candle_low=99.5, candle_high=100.5, candle_open=100.0, bar_index=1
        )
        for f in fills:
            mgr.place_pingpong(f, mid_price=100.0, bar_index=1)

        pp_before = sum(1 for oid in mgr._open_ids if mgr.orders[oid].is_pingpong)

        mgr.cancel_non_pingpong()

        # Only ping-pongs remain
        assert len(mgr._open_ids) == pp_before
        for oid in mgr._open_ids:
            assert mgr.orders[oid].is_pingpong is True


class TestOpenIdsTracking:
    def test_ids_stay_in_sync(self):
        mgr = GridManager(spread_pct=0.001, slippage_pct=0.0)
        mgr.place_grid(_make_levels(100.0, 0.001, n=5))

        # Fill some
        mgr.check_fills(
            candle_low=99.5, candle_high=100.5, candle_open=100.0, bar_index=1
        )

        # _open_ids should match actual open orders
        actual_open = {
            oid for oid, o in mgr.orders.items() if o.status == OrderStatus.OPEN
        }
        assert mgr._open_ids == actual_open

        # Cancel some
        mgr.cancel_side(OrderSide.BID)
        actual_open = {
            oid for oid, o in mgr.orders.items() if o.status == OrderStatus.OPEN
        }
        assert mgr._open_ids == actual_open
