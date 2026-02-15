"""Portfolio: position tracking, equity, drawdown."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from ..data.types import Bar, Fill, Position, Trade, Side
from .execution import ExecutionModel
from .orders import Order


class Portfolio:
    """Tracks positions, equity, and computes drawdown.

    Enforces single-symbol, single-direction positions by default.
    Multi-position mode (e.g. scalper with max_positions=2) is configurable.
    """

    def __init__(
        self,
        initial_equity: float = 10_000.0,
        default_size_usd: float = 10_000.0,
        execution: Optional[ExecutionModel] = None,
        max_positions: int = 1,
    ):
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.peak_equity = initial_equity
        self.max_drawdown = 0.0
        self.default_size_usd = default_size_usd
        self.execution = execution or ExecutionModel()
        self.max_positions = max_positions

        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.fills: List[Fill] = []
        self.total_fees = 0.0

        # Equity curve: list of (timestamp, equity) after each trade close
        self.equity_curve: List[Tuple[datetime, float]] = []

    @property
    def has_position(self) -> bool:
        return len(self.positions) > 0

    @property
    def position(self) -> Optional[Position]:
        """Convenience: return first position (for single-position strategies)."""
        return self.positions[0] if self.positions else None

    @property
    def position_count(self) -> int:
        return len(self.positions)

    def can_open(self) -> bool:
        return len(self.positions) < self.max_positions

    def open_position(
        self,
        bar: Bar,
        order: Order,
        apply_slippage: bool = True,
        limit_price: Optional[float] = None,
        is_maker: bool = False,
    ) -> Fill:
        """Open a new position at bar's open price (or limit price).

        Args:
            bar: Current bar (position opens at bar.open for market orders).
            order: The order to execute.
            apply_slippage: Whether to apply adverse slippage.
            limit_price: Override entry price (for limit order fills).
            is_maker: If True, charge maker_fee instead of taker_fee.

        Returns:
            Fill object for the entry.
        """
        price = limit_price if limit_price is not None else bar.open
        if apply_slippage:
            price = self.execution.apply_entry_slippage(price, order.side)

        size_usd = order.size_usd or self.default_size_usd

        # Calculate TP/SL levels
        tp_pct = order.take_profit_pct or 0.0
        sl_pct = order.stop_loss_pct or 0.0

        if order.side == Side.LONG:
            tp = price * (1 + tp_pct) if tp_pct else 0.0
            sl = price * (1 - sl_pct) if sl_pct else 0.0
        else:
            tp = price * (1 - tp_pct) if tp_pct else 0.0
            sl = price * (1 + sl_pct) if sl_pct else 0.0

        pos = Position(
            side=order.side,
            entry_price=price,
            entry_time=bar.timestamp,
            size_usd=size_usd,
            stop_loss=sl,
            take_profit=tp,
            symbol=order.symbol or bar.symbol,
            breakeven_trigger=order.breakeven_trigger_pct or 0.0,
            breakeven_lock=order.breakeven_lock_pct or 0.0,
        )
        self.positions.append(pos)

        # Entry fees
        fees = self.execution.calc_fees(size_usd, is_maker=is_maker)
        self.total_fees += fees

        fill = Fill(
            timestamp=bar.timestamp,
            side=order.side,
            price=price,
            size_usd=size_usd,
            symbol=pos.symbol,
            fees=fees,
            is_entry=True,
        )
        self.fills.append(fill)

        return fill

    def merge_into_position(
        self,
        bar: Bar,
        order,
        limit_price: float,
        is_maker: bool = True,
    ) -> Fill:
        """Merge a fill into the first existing position.

        Averages entry price by size-weighted mean and increases position size.

        Args:
            bar: Current bar.
            order: The LimitOrder being merged.
            limit_price: Fill price for the merge.
            is_maker: If True, charge maker_fee.

        Returns:
            Fill object for the merge entry.
        """
        pos = self.positions[0]
        old_size = pos.size_usd
        new_size = order.size_usd or self.default_size_usd
        total_size = old_size + new_size

        # Average entry price
        pos.entry_price = (
            pos.entry_price * old_size + limit_price * new_size
        ) / total_size
        pos.size_usd = total_size

        fees = self.execution.calc_fees(new_size, is_maker=is_maker)
        self.total_fees += fees

        fill = Fill(
            timestamp=bar.timestamp,
            side=order.side,
            price=limit_price,
            size_usd=new_size,
            symbol=pos.symbol,
            fees=fees,
            is_entry=True,
            reason="MERGE",
        )
        self.fills.append(fill)
        return fill

    def close_position(
        self,
        index: int,
        exit_price: float,
        bar: Bar,
        reason: str,
        apply_slippage: bool = True,
    ) -> Trade:
        """Close position at index and record the trade.

        Args:
            index: Index into self.positions.
            exit_price: Raw exit price (before slippage).
            bar: Current bar.
            reason: Exit reason string.
            apply_slippage: Whether to apply adverse slippage.

        Returns:
            Completed Trade object.
        """
        pos = self.positions.pop(index)

        if apply_slippage:
            exit_price = self.execution.apply_exit_slippage(exit_price, pos.side)

        # PnL calculation
        if pos.is_long:
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price

        # Fees: entry + exit
        fees = self.execution.calc_fees(pos.size_usd) * 2
        pnl_usd = (pos.size_usd * pnl_pct) - fees
        self.total_fees += self.execution.calc_fees(pos.size_usd)  # exit fee

        # Update equity
        self.equity += pnl_usd
        self.peak_equity = max(self.peak_equity, self.equity)
        drawdown = (self.peak_equity - self.equity) / self.peak_equity
        self.max_drawdown = max(self.max_drawdown, drawdown)

        trade = Trade(
            entry_time=pos.entry_time,
            exit_time=bar.timestamp,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            size_usd=pos.size_usd,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            fees=fees,
            reason=reason,
            symbol=pos.symbol,
        )
        self.trades.append(trade)

        # Track equity curve
        self.equity_curve.append((bar.timestamp, self.equity))

        fill = Fill(
            timestamp=bar.timestamp,
            side=pos.side,
            price=exit_price,
            size_usd=pos.size_usd,
            symbol=pos.symbol,
            fees=self.execution.calc_fees(pos.size_usd),
            is_entry=False,
            reason=reason,
        )
        self.fills.append(fill)

        return trade

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.equity = self.initial_equity
        self.peak_equity = self.initial_equity
        self.max_drawdown = 0.0
        self.positions.clear()
        self.trades.clear()
        self.fills.clear()
        self.total_fees = 0.0
        self.equity_curve.clear()
