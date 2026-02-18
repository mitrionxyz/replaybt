"""Tests for grid shape computation: distributions and capital allocation."""

import pytest

from replaybt.grid.shapes import (
    ShapeConfig,
    compute_grid,
    _round_price,
    _compute_weights,
)


def _make_config(**overrides) -> ShapeConfig:
    """Create a ShapeConfig with reasonable defaults."""
    defaults = dict(
        price_min=90.0,
        price_max=110.0,
        concentration=0.0,
        bias=0.0,
        total_capital=10_000.0,
        spread_pct=0.001,
        num_levels=5,
        tick_size=0.01,
        min_order_value=10.0,
    )
    defaults.update(overrides)
    return ShapeConfig(**defaults)


class TestFlatDistribution:
    def test_equal_sizes(self):
        cfg = _make_config(concentration=0.0)
        grid = compute_grid(cfg, mid_price=100.0)

        bids = [g for g in grid if g.side == "bid"]
        asks = [g for g in grid if g.side == "ask"]

        assert len(bids) > 0
        assert len(asks) > 0

        # Flat -> all sizes on one side should be roughly equal
        if len(bids) > 1:
            sizes = [b.size for b in bids]
            avg = sum(sizes) / len(sizes)
            for s in sizes:
                assert s == pytest.approx(avg, rel=0.05)


class TestGaussianDistribution:
    def test_more_capital_near_mid(self):
        cfg = _make_config(concentration=0.5, num_levels=10)
        grid = compute_grid(cfg, mid_price=100.0)

        bids = sorted([g for g in grid if g.side == "bid"], key=lambda g: -g.price)
        if len(bids) >= 2:
            # Closest to mid should have more capital than farthest
            assert bids[0].size >= bids[-1].size


class TestExponentialDistribution:
    def test_sharp_peak_at_mid(self):
        cfg = _make_config(concentration=1.0, num_levels=10)
        grid = compute_grid(cfg, mid_price=100.0)

        bids = sorted([g for g in grid if g.side == "bid"], key=lambda g: -g.price)
        if len(bids) >= 2:
            # Much more capital near mid
            assert bids[0].size > bids[-1].size * 1.5


class TestBidAskSymmetry:
    def test_equal_capital_both_sides(self):
        cfg = _make_config(concentration=0.0, num_levels=5, bias=0.0)
        grid = compute_grid(cfg, mid_price=100.0)

        bid_capital = sum(g.size * g.price for g in grid if g.side == "bid")
        ask_capital = sum(g.size * g.price for g in grid if g.side == "ask")

        # Should be roughly 50/50
        total = bid_capital + ask_capital
        if total > 0:
            assert bid_capital / total == pytest.approx(0.5, abs=0.05)


class TestTickRounding:
    def test_prices_snap_to_tick(self):
        cfg = _make_config(tick_size=0.50)
        grid = compute_grid(cfg, mid_price=100.0)

        for level in grid:
            remainder = level.price % 0.50
            assert remainder == pytest.approx(
                0.0, abs=1e-8
            ) or remainder == pytest.approx(0.50, abs=1e-8)

    def test_round_price_function(self):
        assert _round_price(99.97, 0.05) == pytest.approx(99.95)
        assert _round_price(100.03, 0.05) == pytest.approx(100.05)
        assert _round_price(100.0, 0.01) == pytest.approx(100.0)


class TestMinOrderValue:
    def test_levels_below_minimum_filtered(self):
        # Very high min_order_value should filter most levels
        cfg = _make_config(min_order_value=9_000.0, num_levels=5)
        grid = compute_grid(cfg, mid_price=100.0)

        # With 10K capital / 2 sides = 5K per side, min 9K -> at most 0-1 level per side
        for level in grid:
            notional = level.size * level.price
            assert notional >= 9_000.0 or len(grid) == 0


class TestComputeWeights:
    def test_weights_sum_to_one(self):
        prices = [95.0, 96.0, 97.0, 98.0, 99.0]
        for conc in [0.0, 0.25, 0.5, 0.75, 1.0]:
            weights = _compute_weights(prices, conc, mu=97.0, price_range=10.0)
            assert sum(weights) == pytest.approx(1.0)

    def test_empty_prices(self):
        weights = _compute_weights([], 0.5, mu=100.0, price_range=10.0)
        assert weights == []
