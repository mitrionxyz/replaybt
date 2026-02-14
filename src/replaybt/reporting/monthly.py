"""Monthly breakdown table for backtest results."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..data.types import Trade


@dataclass
class MonthStats:
    """Stats for a single month."""
    year: int
    month: int
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_pnl: float = 0.0
    fees: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades * 100) if self.trades else 0.0

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


def monthly_breakdown(trades: List[Trade]) -> List[MonthStats]:
    """Compute per-month statistics from a list of trades.

    Groups trades by exit month (since that's when PnL is realized).

    Returns:
        List of MonthStats sorted chronologically.
    """
    if not trades:
        return []

    months: Dict[Tuple[int, int], MonthStats] = {}

    for t in trades:
        key = (t.exit_time.year, t.exit_time.month)
        if key not in months:
            months[key] = MonthStats(year=key[0], month=key[1])
        m = months[key]

        m.trades += 1
        m.fees += t.fees
        m.net_pnl += t.pnl_usd

        if t.pnl_usd > 0:
            m.wins += 1
            m.gross_profit += t.pnl_usd
            m.max_win = max(m.max_win, t.pnl_usd)
        else:
            m.losses += 1
            m.gross_loss += abs(t.pnl_usd)
            m.max_loss = min(m.max_loss, t.pnl_usd)

    return sorted(months.values(), key=lambda m: (m.year, m.month))


def format_monthly_table(
    months: List[MonthStats],
    initial_equity: float = 10_000.0,
) -> str:
    """Format monthly breakdown as an ASCII table.

    Args:
        months: List of MonthStats from monthly_breakdown().
        initial_equity: Starting equity (for return % calculation).

    Returns:
        Formatted table string.
    """
    if not months:
        return "  No trades to display."

    lines = []
    header = (
        f"  {'Month':<10s} {'Trades':>6s} {'WR%':>6s} "
        f"{'Net PnL':>10s} {'Return%':>8s} {'MaxWin':>9s} {'MaxLoss':>9s}"
    )
    lines.append(f"  {'─' * 62}")
    lines.append(header)
    lines.append(f"  {'─' * 62}")

    running_equity = initial_equity
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0

    for m in months:
        ret_pct = (m.net_pnl / running_equity * 100) if running_equity else 0
        running_equity += m.net_pnl
        total_trades += m.trades
        total_wins += m.wins
        total_pnl += m.net_pnl

        lines.append(
            f"  {m.label:<10s} {m.trades:>6d} {m.win_rate:>5.1f}% "
            f"  ${m.net_pnl:>+8,.0f} {ret_pct:>+7.1f}% "
            f"  ${m.max_win:>7,.0f} ${m.max_loss:>+7,.0f}"
        )

    lines.append(f"  {'─' * 62}")
    total_wr = (total_wins / total_trades * 100) if total_trades else 0
    total_ret = (total_pnl / initial_equity * 100)
    lines.append(
        f"  {'TOTAL':<10s} {total_trades:>6d} {total_wr:>5.1f}% "
        f"  ${total_pnl:>+8,.0f} {total_ret:>+7.1f}%"
    )
    lines.append(f"  {'─' * 62}")

    return "\n".join(lines)
