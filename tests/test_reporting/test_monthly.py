"""Tests for monthly breakdown reporting."""

import pytest
from datetime import datetime

from replaybt.data.types import Trade, Side
from replaybt.reporting.monthly import monthly_breakdown, format_monthly_table, MonthStats


def make_trade(exit_month, pnl_usd, exit_year=2024, reason="TAKE_PROFIT"):
    return Trade(
        entry_time=datetime(exit_year, exit_month, 1, 10, 0),
        exit_time=datetime(exit_year, exit_month, 15, 14, 0),
        side=Side.LONG,
        entry_price=100.0,
        exit_price=100.0 + pnl_usd / 100,
        size_usd=10000.0,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_usd / 10000,
        fees=3.0,
        reason=reason,
    )


class TestMonthlyBreakdown:
    def test_empty_trades(self):
        result = monthly_breakdown([])
        assert result == []

    def test_single_month(self):
        trades = [
            make_trade(3, 500),
            make_trade(3, -200),
            make_trade(3, 300),
        ]
        months = monthly_breakdown(trades)
        assert len(months) == 1
        m = months[0]
        assert m.year == 2024
        assert m.month == 3
        assert m.trades == 3
        assert m.wins == 2
        assert m.losses == 1
        assert m.net_pnl == 600.0
        assert m.win_rate == pytest.approx(66.67, abs=0.01)

    def test_multiple_months_sorted(self):
        trades = [
            make_trade(6, 100),
            make_trade(1, 200),
            make_trade(3, -50),
            make_trade(6, 150),
        ]
        months = monthly_breakdown(trades)
        assert len(months) == 3
        assert months[0].label == "2024-01"
        assert months[1].label == "2024-03"
        assert months[2].label == "2024-06"

    def test_cross_year(self):
        trades = [
            make_trade(12, 500, exit_year=2024),
            make_trade(1, 300, exit_year=2025),
        ]
        months = monthly_breakdown(trades)
        assert len(months) == 2
        assert months[0].label == "2024-12"
        assert months[1].label == "2025-01"

    def test_max_win_max_loss(self):
        trades = [
            make_trade(5, 1000),
            make_trade(5, 200),
            make_trade(5, -500),
            make_trade(5, -100),
        ]
        months = monthly_breakdown(trades)
        m = months[0]
        assert m.max_win == 1000.0
        assert m.max_loss == -500.0

    def test_fees_accumulated(self):
        trades = [make_trade(2, 100) for _ in range(5)]
        months = monthly_breakdown(trades)
        assert months[0].fees == 15.0  # 5 * 3.0

    def test_all_wins(self):
        trades = [make_trade(7, 100), make_trade(7, 200)]
        months = monthly_breakdown(trades)
        assert months[0].win_rate == 100.0
        assert months[0].losses == 0

    def test_all_losses(self):
        trades = [make_trade(7, -100), make_trade(7, -200)]
        months = monthly_breakdown(trades)
        assert months[0].win_rate == 0.0
        assert months[0].wins == 0


class TestFormatMonthlyTable:
    def test_empty_returns_message(self):
        result = format_monthly_table([])
        assert "No trades" in result

    def test_table_has_header(self):
        months = [MonthStats(year=2024, month=1, trades=5, wins=3, losses=2, net_pnl=500)]
        table = format_monthly_table(months)
        assert "Month" in table
        assert "Trades" in table
        assert "WR%" in table

    def test_table_has_total_row(self):
        months = [
            MonthStats(year=2024, month=1, trades=5, wins=3, losses=2, net_pnl=500),
            MonthStats(year=2024, month=2, trades=3, wins=2, losses=1, net_pnl=300),
        ]
        table = format_monthly_table(months)
        assert "TOTAL" in table

    def test_monthly_table_from_results(self):
        """BacktestResults.monthly_table() returns formatted output."""
        from replaybt.reporting.metrics import BacktestResults

        trades = [
            make_trade(1, 500),
            make_trade(2, -200),
            make_trade(3, 800),
        ]
        results = BacktestResults(
            trades=trades,
            monthly=monthly_breakdown(trades),
        )
        table = results.monthly_table()
        assert "2024-01" in table
        assert "2024-02" in table
        assert "2024-03" in table
