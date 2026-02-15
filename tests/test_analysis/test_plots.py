"""Tests for visualization functions.

Skipped if matplotlib is not installed.
"""

from datetime import datetime, timedelta

import pytest

mpl = pytest.importorskip("matplotlib")
mpl.use("Agg")  # Non-interactive backend

from replaybt.analysis.plots import (
    plot_drawdown,
    plot_equity,
    plot_exit_breakdown,
    plot_monthly_heatmap,
    plot_multi_equity,
    plot_sweep_heatmap,
    plot_trades,
)
from replaybt.data.types import Side, Trade
from replaybt.optimize.results import SweepResults
from replaybt.reporting.metrics import BacktestResults
from replaybt.reporting.monthly import MonthStats
from replaybt.reporting.multi import MultiAssetResults


def _make_results(n_trades: int = 10) -> BacktestResults:
    """Build a minimal BacktestResults for testing."""
    trades = []
    equity_curve = [(datetime(2024, 1, 1), 10_000.0)]
    equity = 10_000.0

    for i in range(n_trades):
        pnl = 100 if i % 3 != 0 else -50
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
        equity += pnl
        equity_curve.append((t + timedelta(minutes=30), equity))

    return BacktestResults(
        symbol="TEST",
        initial_equity=10_000.0,
        final_equity=equity,
        net_pnl=equity - 10_000.0,
        total_trades=n_trades,
        trades=trades,
        equity_curve=equity_curve,
        exit_breakdown={"TAKE_PROFIT": 7, "STOP_LOSS": 3},
        monthly=[
            MonthStats(year=2024, month=1, trades=n_trades, wins=7, losses=3,
                       net_pnl=500, gross_profit=700, gross_loss=200),
        ],
    )


class TestPlotEquity:
    def test_returns_figure(self):
        results = _make_results()
        fig = plot_equity(results)
        assert isinstance(fig, mpl.figure.Figure)

    def test_empty_data(self):
        results = BacktestResults(equity_curve=[])
        fig = plot_equity(results)
        assert isinstance(fig, mpl.figure.Figure)


class TestPlotDrawdown:
    def test_returns_figure(self):
        results = _make_results()
        fig = plot_drawdown(results)
        assert isinstance(fig, mpl.figure.Figure)


class TestPlotTrades:
    def test_returns_figure(self):
        results = _make_results()
        fig = plot_trades(results)
        assert isinstance(fig, mpl.figure.Figure)


class TestPlotMonthlyHeatmap:
    def test_returns_figure(self):
        results = _make_results()
        fig = plot_monthly_heatmap(results)
        assert isinstance(fig, mpl.figure.Figure)


class TestPlotExitBreakdown:
    def test_returns_figure_bar(self):
        results = _make_results()
        fig = plot_exit_breakdown(results, kind="bar")
        assert isinstance(fig, mpl.figure.Figure)

    def test_returns_figure_pie(self):
        results = _make_results()
        fig = plot_exit_breakdown(results, kind="pie")
        assert isinstance(fig, mpl.figure.Figure)


class TestPlotMultiEquity:
    def test_returns_figure(self):
        r1 = _make_results()
        r1.symbol = "ETH"
        r2 = _make_results()
        r2.symbol = "SOL"

        multi = MultiAssetResults(
            per_symbol={"ETH": r1, "SOL": r2},
            combined_equity_curve=r1.equity_curve,
        )
        fig = plot_multi_equity(multi)
        assert isinstance(fig, mpl.figure.Figure)


class TestPlotSweepHeatmap:
    def test_returns_figure(self):
        combos = []
        for tp in [4, 6, 8]:
            for sl in [2, 3]:
                combos.append({
                    "tp_pct": tp, "sl_pct": sl,
                    "net_pnl": tp * 100 - sl * 50,
                    "win_rate": 60 + tp,
                })
        sr = SweepResults(combos=combos)
        fig = plot_sweep_heatmap(sr, x_param="tp_pct", y_param="sl_pct")
        assert isinstance(fig, mpl.figure.Figure)
