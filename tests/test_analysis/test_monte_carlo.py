"""Tests for Monte Carlo simulation."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from replaybt.analysis.monte_carlo import MonteCarlo, MonteCarloResult
from replaybt.data.types import Side, Trade
from replaybt.reporting.metrics import BacktestResults


def _make_trades(pnls: list[float]) -> list[Trade]:
    """Build minimal Trade objects from a list of PnL values."""
    trades = []
    for i, pnl in enumerate(pnls):
        t = datetime(2024, 1, 1) + timedelta(hours=i)
        trades.append(
            Trade(
                entry_time=t,
                exit_time=t + timedelta(minutes=30),
                side=Side.LONG,
                entry_price=100.0,
                exit_price=100.0 + pnl / 100,
                size_usd=10_000.0,
                pnl_usd=pnl,
                pnl_pct=pnl / 10_000 * 100,
                fees=1.0,
                reason="TAKE_PROFIT" if pnl > 0 else "STOP_LOSS",
            )
        )
    return trades


def _make_results(pnls: list[float], initial_equity: float = 10_000.0) -> BacktestResults:
    """Build a minimal BacktestResults from PnL list."""
    trades = _make_trades(pnls)
    total_pnl = sum(pnls)
    return BacktestResults(
        initial_equity=initial_equity,
        final_equity=initial_equity + total_pnl,
        net_pnl=total_pnl,
        total_trades=len(trades),
        trades=trades,
    )


class TestMonteCarlo:
    def test_runs_returns_result(self):
        """Basic smoke test — run completes and returns MonteCarloResult."""
        results = _make_results([100, -50, 200, -30, 150, 80, -40, 120])
        mc = MonteCarlo(results, n_simulations=500, seed=42)
        result = mc.run()

        assert isinstance(result, MonteCarloResult)
        assert result.n_simulations == 500
        assert result.n_trades == 8
        assert result.initial_equity == 10_000.0
        assert result.shuffle_max_dds is not None
        assert len(result.shuffle_max_dds) == 500
        assert result.bootstrap_final_pnls is not None
        assert len(result.bootstrap_final_pnls) == 500
        # Summary should be a non-empty string
        assert len(result.summary()) > 100

    def test_shuffle_pnl_invariant(self):
        """Shuffle mode preserves total PnL — all paths sum to the same value."""
        pnls = [100, -50, 200, -30, 150]
        expected_total = sum(pnls)
        results = _make_results(pnls)
        mc = MonteCarlo(results, n_simulations=1000, seed=123)
        result = mc.run()

        # Every percentile of shuffle final PnL should equal the total
        for p, val in result.shuffle_pnl_percentiles.items():
            assert val == pytest.approx(expected_total), (
                f"Shuffle P{p} should be {expected_total}, got {val}"
            )

    def test_bootstrap_pnl_varies(self):
        """Bootstrap mode produces different total PnLs (std > 0)."""
        results = _make_results([100, -50, 200, -30, 150, 80, -40])
        mc = MonteCarlo(results, n_simulations=2000, seed=99)
        result = mc.run()

        assert result.bootstrap_pnl_std > 0, "Bootstrap PnL should have variance"
        # P5 should be less than P95
        assert result.bootstrap_pnl_percentiles[5] < result.bootstrap_pnl_percentiles[95]

    def test_reproducibility_with_seed(self):
        """Same seed produces identical results."""
        results = _make_results([100, -50, 200, -30, 150, 80])

        r1 = MonteCarlo(results, n_simulations=500, seed=42).run()
        r2 = MonteCarlo(results, n_simulations=500, seed=42).run()

        assert r1.shuffle_max_dd_mean == pytest.approx(r2.shuffle_max_dd_mean)
        assert r1.bootstrap_pnl_mean == pytest.approx(r2.bootstrap_pnl_mean)
        assert r1.ruin_probability == pytest.approx(r2.ruin_probability)
        np.testing.assert_array_equal(r1.shuffle_max_dds, r2.shuffle_max_dds)
        np.testing.assert_array_equal(r1.bootstrap_final_pnls, r2.bootstrap_final_pnls)

    def test_empty_trades(self):
        """Zero trades returns graceful empty result."""
        results = BacktestResults(trades=[])
        mc = MonteCarlo(results, n_simulations=100, seed=1)
        result = mc.run()

        assert result.n_trades == 0
        assert result.ruin_probability == 0.0
        assert result.shuffle_max_dd_mean == 0.0
        assert result.bootstrap_pnl_mean == 0.0
        assert result.shuffle_max_dds is None

    def test_ruin_all_losses(self):
        """All-loss trades should have high ruin probability."""
        # 20 losses of $600 each = $12,000 total loss on $10k equity
        results = _make_results([-600] * 20, initial_equity=10_000.0)
        mc = MonteCarlo(
            results, n_simulations=1000, seed=7, ruin_threshold=0.0
        )
        result = mc.run()

        # With $12k total losses on $10k equity, equity always goes below 0
        assert result.ruin_probability > 0.9, (
            f"Expected high ruin prob with all losses, got {result.ruin_probability}"
        )
