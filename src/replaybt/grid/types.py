"""Data types for the grid market making module."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple

from ..data.types import Trade, Side
from ..reporting.metrics import BacktestResults


class OrderSide(str, Enum):
    BID = "bid"
    ASK = "ask"


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class GridConfig:
    """Configuration for a grid market making backtest."""

    capital: float = 10_000.0
    spread_pct: float = 0.001  # half-spread (0.1%)
    concentration: float = 0.5  # 0=flat, 0.5=gaussian, 1.0=exponential
    bias: float = 0.0  # -1 to 1, shifts distribution center
    range_pct: float = 0.15  # price range as fraction of mid
    num_levels: int = 20  # per side
    tick_size: float = 0.01  # price rounding
    min_order_value: float = 10.0  # minimum notional per level
    max_inventory_pct: float = 0.5  # max inventory as fraction of capital
    slippage_pct: float = 0.0002  # per-fill slippage
    maker_fee_pct: float = 0.0  # maker fee (Lighter = 0%)
    # Recenter
    recenter_threshold: float = 0.02  # re-center when price deviates this much
    recenter_min_bars: int = 30  # minimum bars between re-centers
    # Vol guard
    vol_guard_enabled: bool = False
    vol_guard_atr_period: int = 5
    vol_guard_threshold_pct: float = 1.0
    vol_guard_cooldown: int = 15
    # Circuit breaker
    max_drawdown_pct: float = 0.15
    # Skew
    skew_factor: float = 0.0005
    max_skew: float = 0.01
    recenter_skew_pct: float = 0.0
    # Inventory reduce
    inventory_reduce_pct: float = 0.0
    # Snapshot interval
    snapshot_interval: int = 60


@dataclass(slots=True)
class GridOrder:
    """A virtual limit order on the grid."""

    id: int
    price: float
    size: float  # base currency
    side: OrderSide
    status: OrderStatus = OrderStatus.OPEN
    is_pingpong: bool = False
    placed_at_bar: int = 0


@dataclass(slots=True, frozen=True)
class GridFill:
    """A completed fill on a grid order."""

    order_id: int
    price: float
    size: float
    side: OrderSide
    bar_index: int
    timestamp: datetime = datetime(2000, 1, 1)
    spread_earned: float = 0.0


@dataclass
class GridResults:
    """Complete results from a grid market making backtest."""

    initial_capital: float = 0.0
    final_equity: float = 0.0
    total_pnl: float = 0.0
    spread_pnl: float = 0.0
    inventory_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    total_fills: int = 0
    bid_fills: int = 0
    ask_fills: int = 0
    recenters: int = 0
    total_bars: int = 0
    vol_guard_triggers: int = 0
    vol_guard_bars_paused: int = 0
    inv_reduce_activations: int = 0
    inv_reduce_bars: int = 0
    symbol: str = ""
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    fill_log: List[GridFill] = field(default_factory=list)

    def summary(self) -> str:
        """Return formatted summary string."""
        ret_pct = (
            (self.total_pnl / self.initial_capital * 100) if self.initial_capital else 0
        )
        lines = [
            f"{'=' * 60}",
            f"  Grid MM Results: {self.symbol or 'N/A'}",
            f"{'=' * 60}",
            f"  Net PnL:          ${self.total_pnl:,.2f} ({ret_pct:+.1f}%)",
            f"    Spread PnL:     ${self.spread_pnl:,.2f}",
            f"    Inventory PnL:  ${self.inventory_pnl:,.2f}",
            f"  Max Drawdown:     {self.max_drawdown_pct * 100:.1f}%",
            f"  Sharpe Ratio:     {self.sharpe_ratio:.2f}",
            f"  {'─' * 56}",
            f"  Total Fills:      {self.total_fills}",
            f"    Bid Fills:      {self.bid_fills}",
            f"    Ask Fills:      {self.ask_fills}",
            f"  Re-centers:       {self.recenters}",
            f"  Total Bars:       {self.total_bars}",
        ]
        if self.vol_guard_triggers > 0:
            lines.append(f"  {'─' * 56}")
            lines.append(f"  Vol Guard Triggers: {self.vol_guard_triggers}")
            lines.append(f"  Vol Guard Paused:   {self.vol_guard_bars_paused} bars")
        lines.extend(
            [
                f"  {'─' * 56}",
                f"  Initial Capital:  ${self.initial_capital:,.2f}",
                f"  Final Equity:     ${self.final_equity:,.2f}",
                f"{'=' * 60}",
            ]
        )
        return "\n".join(lines)

    def to_backtest_results(self) -> BacktestResults:
        """Convert to replaybt's standard BacktestResults for reporting.

        Maps consecutive bid/ask fill pairs to Trade objects.
        """
        trades: List[Trade] = []
        pending_bid: Optional[GridFill] = None
        pending_ask: Optional[GridFill] = None

        for fill in self.fill_log:
            if fill.side == OrderSide.BID:
                if pending_bid is None:
                    pending_bid = fill
                elif pending_ask is not None:
                    # Close the ask→bid round trip (short)
                    pnl = (pending_ask.price - fill.price) * fill.size
                    entry_p = pending_ask.price
                    pnl_pct = (pnl / (entry_p * fill.size)) if entry_p else 0
                    trades.append(
                        Trade(
                            entry_time=pending_ask.timestamp,
                            exit_time=fill.timestamp,
                            side=Side.SHORT,
                            entry_price=pending_ask.price,
                            exit_price=fill.price,
                            size_usd=fill.size * fill.price,
                            pnl_usd=pnl,
                            pnl_pct=pnl_pct,
                            fees=0.0,
                            reason="GRID_FILL",
                            symbol=self.symbol,
                        )
                    )
                    pending_ask = None
                else:
                    pending_bid = fill
            else:  # ASK
                if pending_ask is None:
                    pending_ask = fill
                elif pending_bid is not None:
                    # Close the bid→ask round trip (long)
                    pnl = (fill.price - pending_bid.price) * fill.size
                    entry_p = pending_bid.price
                    pnl_pct = (pnl / (entry_p * fill.size)) if entry_p else 0
                    trades.append(
                        Trade(
                            entry_time=pending_bid.timestamp,
                            exit_time=fill.timestamp,
                            side=Side.LONG,
                            entry_price=pending_bid.price,
                            exit_price=fill.price,
                            size_usd=fill.size * fill.price,
                            pnl_usd=pnl,
                            pnl_pct=pnl_pct,
                            fees=0.0,
                            reason="GRID_FILL",
                            symbol=self.symbol,
                        )
                    )
                    pending_bid = None
                else:
                    pending_ask = fill

        ret_pct = (
            (self.total_pnl / self.initial_capital * 100) if self.initial_capital else 0
        )

        winners = [t for t in trades if t.pnl_usd > 0]
        losers = [t for t in trades if t.pnl_usd <= 0]
        n_win = len(winners)
        n_lose = len(losers)
        total = len(trades)

        gross_profit = sum(t.pnl_usd for t in winners) if winners else 0.0
        gross_loss = abs(sum(t.pnl_usd for t in losers)) if losers else 0.0

        return BacktestResults(
            symbol=self.symbol,
            initial_equity=self.initial_capital,
            final_equity=self.final_equity,
            net_pnl=self.total_pnl,
            net_return_pct=ret_pct,
            max_drawdown_pct=self.max_drawdown_pct * 100,
            total_trades=total,
            winning_trades=n_win,
            losing_trades=n_lose,
            win_rate=(n_win / total * 100) if total else 0,
            avg_win=(gross_profit / n_win) if n_win else 0,
            avg_loss=(gross_loss / n_lose) if n_lose else 0,
            avg_win_pct=(sum(t.pnl_pct for t in winners) / n_win * 100) if n_win else 0,
            avg_loss_pct=(abs(sum(t.pnl_pct for t in losers)) / n_lose * 100)
            if n_lose
            else 0,
            profit_factor=(gross_profit / gross_loss)
            if gross_loss > 0
            else float("inf"),
            trades=trades,
            equity_curve=list(self.equity_curve),
        )


def _compute_sharpe(
    equity_curve: List[Tuple[datetime, float]], annualization: float = 8760.0
) -> float:
    """Compute annualized Sharpe ratio from equity curve snapshots.

    Assumes snapshots are hourly (60 1m bars apart).
    annualization = 8760 hours/year.
    """
    if len(equity_curve) < 10:
        return 0.0

    returns = []
    for i in range(1, len(equity_curve)):
        prev_eq = equity_curve[i - 1][1]
        curr_eq = equity_curve[i][1]
        if prev_eq > 0:
            returns.append((curr_eq - prev_eq) / prev_eq)

    if not returns:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_ret = math.sqrt(variance) if variance > 0 else 0.0

    if std_ret == 0:
        return 0.0

    return (mean_ret / std_ret) * math.sqrt(annualization)
