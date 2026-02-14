"""Backtest results and metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..data.types import Trade


@dataclass
class BacktestResults:
    """Complete backtest results with all required metrics.

    Includes: net return, max drawdown, win rate, avg win/loss,
    total fees, profit factor, and trade breakdown.
    """
    symbol: str = ""
    initial_equity: float = 10_000.0
    final_equity: float = 10_000.0
    net_pnl: float = 0.0
    net_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    total_fees: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    exit_breakdown: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_portfolio(cls, portfolio, symbol: str = "") -> "BacktestResults":
        """Build results from a Portfolio instance."""
        trades = portfolio.trades
        total = len(trades)

        if total == 0:
            return cls(
                symbol=symbol,
                initial_equity=portfolio.initial_equity,
                final_equity=portfolio.equity,
                trades=[],
            )

        winners = [t for t in trades if t.pnl_usd > 0]
        losers = [t for t in trades if t.pnl_usd <= 0]
        n_win = len(winners)
        n_lose = len(losers)

        gross_profit = sum(t.pnl_usd for t in winners) if winners else 0.0
        gross_loss = abs(sum(t.pnl_usd for t in losers)) if losers else 0.0

        # Exit reason breakdown
        breakdown: Dict[str, int] = {}
        for t in trades:
            key = t.reason
            # Normalize gap variants
            if key.endswith("_GAP"):
                key = key[:-4]
            breakdown[key] = breakdown.get(key, 0) + 1

        return cls(
            symbol=symbol,
            initial_equity=portfolio.initial_equity,
            final_equity=portfolio.equity,
            net_pnl=portfolio.equity - portfolio.initial_equity,
            net_return_pct=(portfolio.equity - portfolio.initial_equity) / portfolio.initial_equity * 100,
            max_drawdown_pct=portfolio.max_drawdown * 100,
            total_trades=total,
            winning_trades=n_win,
            losing_trades=n_lose,
            win_rate=n_win / total * 100 if total else 0,
            avg_win=gross_profit / n_win if n_win else 0,
            avg_loss=gross_loss / n_lose if n_lose else 0,
            avg_win_pct=sum(t.pnl_pct for t in winners) / n_win * 100 if n_win else 0,
            avg_loss_pct=abs(sum(t.pnl_pct for t in losers)) / n_lose * 100 if n_lose else 0,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else float("inf"),
            total_fees=portfolio.total_fees,
            trades=list(trades),
            exit_breakdown=breakdown,
        )

    def summary(self) -> str:
        """Return formatted summary string."""
        lines = [
            f"{'='*60}",
            f"  Backtest Results: {self.symbol or 'N/A'}",
            f"{'='*60}",
            f"  Net PnL:          ${self.net_pnl:,.2f} ({self.net_return_pct:+.1f}%)",
            f"  Max Drawdown:     {self.max_drawdown_pct:.1f}%",
            f"  Total Trades:     {self.total_trades}",
            f"  Win Rate:         {self.win_rate:.1f}%",
            f"  Avg Win:          ${self.avg_win:,.2f} ({self.avg_win_pct:.2f}%)",
            f"  Avg Loss:         ${self.avg_loss:,.2f} ({self.avg_loss_pct:.2f}%)",
            f"  Profit Factor:    {self.profit_factor:.2f}",
            f"  Total Fees:       ${self.total_fees:,.2f}",
            f"  Initial Equity:   ${self.initial_equity:,.2f}",
            f"  Final Equity:     ${self.final_equity:,.2f}",
        ]

        if self.exit_breakdown:
            lines.append(f"  {'─'*56}")
            lines.append(f"  Exit Breakdown:")
            for reason, count in sorted(self.exit_breakdown.items()):
                pct = count / self.total_trades * 100
                lines.append(f"    {reason:<20s} {count:>4d} ({pct:.1f}%)")

        lines.append(f"{'='*60}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"BacktestResults(symbol={self.symbol!r}, net_pnl=${self.net_pnl:,.2f}, "
            f"trades={self.total_trades}, win_rate={self.win_rate:.1f}%, "
            f"max_dd={self.max_drawdown_pct:.1f}%)"
        )
