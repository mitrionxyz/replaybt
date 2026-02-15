"""Multi-asset backtest results and combined metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..data.types import Bar, Trade
from .metrics import BacktestResults
from .monthly import MonthStats, monthly_breakdown, format_monthly_table


@dataclass
class MultiAssetResults:
    """Combined results from a multi-asset backtest.

    Provides both per-symbol results and portfolio-level metrics.
    The combined equity curve sums all per-symbol equities at each
    timestamp, correctly capturing correlated drawdowns.
    """
    per_symbol: Dict[str, BacktestResults] = field(default_factory=dict)

    # Combined portfolio metrics
    combined_equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    combined_max_drawdown_pct: float = 0.0
    combined_net_pnl: float = 0.0
    combined_return_pct: float = 0.0
    combined_total_trades: int = 0
    combined_win_rate: float = 0.0
    combined_total_fees: float = 0.0
    combined_profit_factor: float = 0.0
    total_initial_equity: float = 0.0

    # Monthly breakdown
    combined_monthly: List[MonthStats] = field(default_factory=list)

    @classmethod
    def from_portfolios(
        cls,
        portfolios: Dict[str, "Portfolio"],
        first_bars: Dict[str, Optional[Bar]],
        last_bars: Dict[str, Optional[Bar]],
        config: Optional[Dict] = None,
    ) -> "MultiAssetResults":
        """Build combined results from per-symbol portfolios.

        Args:
            portfolios: {symbol: Portfolio} mapping.
            first_bars: {symbol: first_bar} for buy-and-hold comparison.
            last_bars: {symbol: last_bar} for buy-and-hold comparison.
            config: Engine config (for initial_equity).
        """
        config = config or {}

        # Build per-symbol BacktestResults
        per_symbol = {}
        for sym, portfolio in portfolios.items():
            per_symbol[sym] = BacktestResults.from_portfolio(
                portfolio,
                symbol=sym,
                first_bar=first_bars.get(sym),
                last_bar=last_bars.get(sym),
            )

        # Combined equity curve via timeline merge
        # Collect all equity events across symbols with running latest values
        total_initial = sum(p.initial_equity for p in portfolios.values())

        # Build combined equity curve: at each trade close from any symbol,
        # sum all symbols' latest equity
        all_events: List[Tuple[datetime, str, float]] = []
        for sym, portfolio in portfolios.items():
            for ts, equity in portfolio.equity_curve:
                all_events.append((ts, sym, equity))

        # Sort by timestamp
        all_events.sort(key=lambda x: x[0])

        # Track latest equity per symbol (start at initial_equity)
        latest_equity: Dict[str, float] = {
            sym: p.initial_equity for sym, p in portfolios.items()
        }

        combined_curve: List[Tuple[datetime, float]] = []
        for ts, sym, equity in all_events:
            latest_equity[sym] = equity
            combined_eq = sum(latest_equity.values())
            combined_curve.append((ts, combined_eq))

        # Combined max drawdown from the combined curve
        combined_dd = 0.0
        if combined_curve:
            peak = total_initial
            for _, eq in combined_curve:
                peak = max(peak, eq)
                dd = (peak - eq) / peak if peak > 0 else 0.0
                combined_dd = max(combined_dd, dd)

        # Aggregate trade-level metrics
        all_trades: List[Trade] = []
        total_fees = 0.0
        for res in per_symbol.values():
            all_trades.extend(res.trades)
            total_fees += res.total_fees

        total_trades = len(all_trades)
        winning = [t for t in all_trades if t.pnl_usd > 0]
        losing = [t for t in all_trades if t.pnl_usd <= 0]
        n_win = len(winning)

        gross_profit = sum(t.pnl_usd for t in winning) if winning else 0.0
        gross_loss = abs(sum(t.pnl_usd for t in losing)) if losing else 0.0

        net_pnl = sum(res.net_pnl for res in per_symbol.values())

        return cls(
            per_symbol=per_symbol,
            combined_equity_curve=combined_curve,
            combined_max_drawdown_pct=combined_dd * 100,
            combined_net_pnl=net_pnl,
            combined_return_pct=(net_pnl / total_initial * 100) if total_initial else 0.0,
            combined_total_trades=total_trades,
            combined_win_rate=(n_win / total_trades * 100) if total_trades else 0.0,
            combined_total_fees=total_fees,
            combined_profit_factor=(
                gross_profit / gross_loss if gross_loss > 0 else float("inf")
            ),
            total_initial_equity=total_initial,
            combined_monthly=monthly_breakdown(all_trades),
        )

    def summary(self) -> str:
        """Return formatted combined + per-symbol summary."""
        lines = [
            f"{'='*60}",
            f"  Multi-Asset Backtest Results",
            f"{'='*60}",
            f"  Symbols:          {', '.join(sorted(self.per_symbol.keys()))}",
            f"  Net PnL:          ${self.combined_net_pnl:,.2f} ({self.combined_return_pct:+.1f}%)",
            f"  Max Drawdown:     {self.combined_max_drawdown_pct:.1f}%",
            f"  Total Trades:     {self.combined_total_trades}",
            f"  Win Rate:         {self.combined_win_rate:.1f}%",
            f"  Profit Factor:    {self.combined_profit_factor:.2f}",
            f"  Total Fees:       ${self.combined_total_fees:,.2f}",
            f"  Initial Equity:   ${self.total_initial_equity:,.2f}",
            f"  Final Equity:     ${self.total_initial_equity + self.combined_net_pnl:,.2f}",
            f"  {'─'*56}",
            f"  Per-Symbol Breakdown:",
        ]

        # Per-symbol table
        header = (
            f"    {'Symbol':<8s} {'Net PnL':>10s} {'Return%':>8s} "
            f"{'MaxDD':>6s} {'Trades':>6s} {'WR%':>6s}"
        )
        lines.append(header)
        lines.append(f"    {'─'*50}")

        for sym in sorted(self.per_symbol.keys()):
            res = self.per_symbol[sym]
            lines.append(
                f"    {sym:<8s} ${res.net_pnl:>+9,.0f} {res.net_return_pct:>+7.1f}% "
                f"{res.max_drawdown_pct:>5.1f}% {res.total_trades:>6d} "
                f"{res.win_rate:>5.1f}%"
            )

        lines.append(f"{'='*60}")
        return "\n".join(lines)

    def monthly_table(self) -> str:
        """Return formatted combined monthly breakdown."""
        return format_monthly_table(self.combined_monthly, self.total_initial_equity)

    def __repr__(self) -> str:
        symbols = ", ".join(sorted(self.per_symbol.keys()))
        return (
            f"MultiAssetResults(symbols=[{symbols}], "
            f"net_pnl=${self.combined_net_pnl:,.2f}, "
            f"trades={self.combined_total_trades}, "
            f"max_dd={self.combined_max_drawdown_pct:.1f}%)"
        )
