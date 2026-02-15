"""BarProcessor: reusable execution loop.

Extracted from BacktestEngine._process_bar() so both BacktestEngine
(single-symbol) and MultiAssetEngine (multi-symbol) can share the
same execution logic without duplication.

Per bar:
  Phase 1: Execute pending market orders at bar OPEN + adverse slippage
  Phase 1b: Check pending limit orders for fills (incl. merge_position)
  Phase 3: Check exits (open gap FIRST, then High/Low vs SL/TP)
  Phase 3.5: Strategy-initiated exits
  Phase 4: Call strategy.on_bar() with COMPLETED bar -> sets pending for next bar
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..data.types import Bar, Fill, Position, Trade, Side
from ..indicators.base import IndicatorManager
from ..strategy.base import Strategy
from .execution import ExecutionModel
from .orders import Order, MarketOrder, LimitOrder, CancelPendingLimitsOrder
from .portfolio import Portfolio


@dataclass(slots=True)
class _PendingLimit:
    """Internal tracker for a pending limit order."""
    order: LimitOrder
    bars_elapsed: int = 0


class BarProcessor:
    """Reusable 4-phase execution loop for a single symbol.

    Manages pending orders and delegates to Portfolio, IndicatorManager,
    ExecutionModel, and Strategy.

    Args:
        portfolio: Portfolio instance for position/equity tracking.
        indicators: IndicatorManager for this symbol.
        execution: ExecutionModel for slippage/fees/gap protection.
        strategy: Strategy instance (shared across symbols in multi-asset).
        config: Engine config dict (for behavior flags).
        callbacks: Optional event callback dict.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        indicators: IndicatorManager,
        execution: ExecutionModel,
        strategy: Strategy,
        config: Optional[Dict] = None,
        callbacks: Optional[Dict[str, List[Callable]]] = None,
    ):
        self.portfolio = portfolio
        self.indicators = indicators
        self.execution = execution
        self.strategy = strategy

        config = config or {}
        self._skip_signal_on_close = config.get("skip_signal_on_close", True)
        self._same_direction_only = config.get("same_direction_only", True)
        self._callbacks = callbacks or {}

        # Pending market order from strategy (executes at next bar's open)
        self._pending_order: Optional[Order] = None

        # Pending limit orders (checked each bar until fill or timeout)
        self._pending_limits: List[_PendingLimit] = []

    def _emit(self, event: str, *args) -> None:
        for cb in self._callbacks.get(event, []):
            cb(*args)

    def _handle_follow_up(self, order) -> None:
        """Process a follow-up order returned from on_fill or on_exit."""
        if order is None:
            return
        # Sentinel: cancel all pending limits without placing a new order
        if isinstance(order, CancelPendingLimitsOrder):
            self._pending_limits.clear()
            return
        # Order-level flag: cancel pending limits then process the order
        if order.cancel_pending_limits:
            self._pending_limits.clear()
        if isinstance(order, LimitOrder):
            self._pending_limits.append(_PendingLimit(order=order))
        else:
            self._pending_order = order
        self._emit("signal", order)

    def process_bar(self, bar: Bar) -> None:
        """Process a single bar through the 4-phase loop."""

        # ============================================================
        # PHASE 1: Execute pending market orders at bar OPEN
        # ============================================================
        just_opened = False
        if self._pending_order is not None and self.portfolio.can_open():
            order = self._pending_order
            self._pending_order = None

            # For multi-position: ensure same direction (unless hedging enabled)
            if self._same_direction_only and self.portfolio.has_position:
                existing_side = self.portfolio.positions[0].side
                if order.side != existing_side:
                    order = None  # Skip conflicting direction

            if order is not None:
                fill = self.portfolio.open_position(bar, order)
                self._emit("fill", fill)
                follow_up = self.strategy.on_fill(fill)
                self._handle_follow_up(follow_up)
                just_opened = True

        # ============================================================
        # PHASE 1b: Check pending limit orders for fills
        # ============================================================
        # Snapshot: iterate over current limits only; on_fill callbacks
        # may append new limits (e.g. merge orders) which we must NOT
        # remove during this bar's cleanup.
        limits_snapshot = list(self._pending_limits)
        to_remove = set()
        for i, pending in enumerate(limits_snapshot):
            is_merge = pending.order.merge_position

            if is_merge:
                # Merge orders need an existing position to merge into
                if not self.portfolio.has_position:
                    # No position — tick timeout but don't fill
                    pending.bars_elapsed += 1
                    if (
                        pending.order.timeout_bars > 0
                        and pending.bars_elapsed >= pending.order.timeout_bars
                    ):
                        to_remove.add(id(pending))
                    continue
            else:
                if not self.portfolio.can_open():
                    break
                # Direction check (unless hedging enabled)
                if self._same_direction_only and self.portfolio.has_position:
                    existing_side = self.portfolio.positions[0].side
                    if pending.order.side != existing_side:
                        to_remove.add(id(pending))
                        continue

            pending.bars_elapsed += 1

            # min_positions guard (e.g. DCA needs at least 1 position)
            if (
                pending.order.min_positions > 0
                and len(self.portfolio.positions) < pending.order.min_positions
            ):
                continue

            if self.execution.check_limit_fill(
                pending.order.limit_price, pending.order.side, bar
            ):
                if is_merge:
                    fill = self.portfolio.merge_into_position(
                        bar, pending.order,
                        limit_price=pending.order.limit_price,
                        is_maker=pending.order.use_maker_fee,
                    )
                else:
                    fill = self.portfolio.open_position(
                        bar, pending.order,
                        apply_slippage=False,
                        limit_price=pending.order.limit_price,
                        is_maker=pending.order.use_maker_fee,
                    )
                self._emit("fill", fill)
                follow_up = self.strategy.on_fill(fill)
                self._handle_follow_up(follow_up)
                to_remove.add(id(pending))
                just_opened = True
            elif (
                pending.order.timeout_bars > 0
                and pending.bars_elapsed >= pending.order.timeout_bars
            ):
                to_remove.add(id(pending))

        # Remove filled/timed-out limit orders (by identity, safe with appends)
        if to_remove:
            self._pending_limits = [
                p for p in self._pending_limits if id(p) not in to_remove
            ]

        # ============================================================
        # PHASE 3: Check exits (gap protection + SL/TP)
        # ============================================================
        just_closed = False
        exits_to_process = []

        for idx, pos in enumerate(self.portfolio.positions):
            exit_price, reason = self.execution.check_exit(pos, bar)
            if exit_price is not None:
                exits_to_process.append((idx, exit_price, reason))

        # Process exits in reverse order (preserve indices)
        for idx, exit_price, reason in reversed(exits_to_process):
            trade = self.portfolio.close_position(idx, exit_price, bar, reason)
            self._emit("exit", trade)
            follow_up = self.strategy.on_exit(
                Fill(
                    timestamp=bar.timestamp,
                    side=trade.side,
                    price=trade.exit_price,
                    size_usd=trade.size_usd,
                    symbol=trade.symbol,
                    is_entry=False,
                    reason=reason,
                ),
                trade,
            )
            self._handle_follow_up(follow_up)
            just_closed = True

        # ============================================================
        # PHASE 3.5: Strategy-initiated exits (e.g. HTF RSI exit)
        # ============================================================
        strat_exits = self.strategy.check_exits(bar, list(self.portfolio.positions))
        for pos_idx, exit_price, reason in sorted(
            strat_exits, key=lambda x: x[0], reverse=True
        ):
            if pos_idx < len(self.portfolio.positions):
                trade = self.portfolio.close_position(
                    pos_idx, exit_price, bar, reason
                )
                self._emit("exit", trade)
                follow_up = self.strategy.on_exit(
                    Fill(
                        timestamp=bar.timestamp,
                        side=trade.side,
                        price=trade.exit_price,
                        size_usd=trade.size_usd,
                        symbol=trade.symbol,
                        is_entry=False,
                        reason=reason,
                    ),
                    trade,
                )
                self._handle_follow_up(follow_up)
                just_closed = True

        # ============================================================
        # PHASE 4: Update indicators and generate signal
        # ============================================================
        self.indicators.update(bar)
        self._emit("bar", bar)

        # Don't signal on the same bar a position just closed
        # (matches reference backtest + live bot behavior)
        if just_closed and self._skip_signal_on_close:
            return

        # Get indicator values for the strategy
        indicator_values = self.indicators.values()

        # Call strategy -- normalize result to list
        result = self.strategy.on_bar(
            bar=bar,
            indicators=indicator_values,
            positions=list(self.portfolio.positions),
        )

        if result is None:
            orders = []
        elif isinstance(result, list):
            orders = result
        else:
            orders = [result]

        for order in orders:
            self._handle_follow_up(order)

    def reset(self) -> None:
        """Reset pending order state."""
        self._pending_order = None
        self._pending_limits.clear()
