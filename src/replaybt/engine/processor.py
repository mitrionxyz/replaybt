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
from .orders import Order, MarketOrder, LimitOrder, StopOrder, CancelPendingLimitsOrder
from .portfolio import Portfolio


@dataclass(slots=True)
class _PendingLimit:
    """Internal tracker for a pending limit order."""
    order: LimitOrder
    bars_elapsed: int = 0


@dataclass(slots=True)
class _PendingStop:
    """Internal tracker for a pending stop order."""
    order: StopOrder
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

        # Pending stop orders (checked each bar until fill or timeout)
        self._pending_stops: List[_PendingStop] = []

    def _emit(self, event: str, *args) -> None:
        for cb in self._callbacks.get(event, []):
            cb(*args)

    def _handle_follow_up(self, order) -> None:
        """Process a follow-up order returned from on_fill or on_exit."""
        if order is None:
            return
        # Sentinel: cancel all pending limits/stops without placing a new order
        if isinstance(order, CancelPendingLimitsOrder):
            self._pending_limits.clear()
            self._pending_stops.clear()
            return
        # Order-level flag: cancel pending limits/stops then process the order
        if order.cancel_pending_limits:
            self._pending_limits.clear()
            self._pending_stops.clear()
        # StopOrder check must come before LimitOrder (StopOrder is an Order subclass)
        if isinstance(order, StopOrder):
            self._pending_stops.append(_PendingStop(order=order))
        elif isinstance(order, LimitOrder):
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
        if self._pending_order is not None and self.portfolio.can_open(self._pending_order.group):
            order = self._pending_order
            self._pending_order = None

            # For multi-position: ensure same direction within group
            if self._same_direction_only:
                group_positions = self.portfolio.positions_in_group(order.group)
                if group_positions:
                    existing_side = group_positions[0].side
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
                # Merge orders need an existing position in the same group
                group_positions = self.portfolio.positions_in_group(pending.order.group)
                if not group_positions:
                    # No position in group — tick timeout but don't fill
                    pending.bars_elapsed += 1
                    if (
                        pending.order.timeout_bars > 0
                        and pending.bars_elapsed >= pending.order.timeout_bars
                    ):
                        to_remove.add(id(pending))
                    continue
            else:
                if not self.portfolio.can_open(pending.order.group):
                    break
                # Direction check within group
                if self._same_direction_only:
                    group_positions = self.portfolio.positions_in_group(pending.order.group)
                    if group_positions:
                        existing_side = group_positions[0].side
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
        # PHASE 1c: Check pending stop orders for fills
        # ============================================================
        stops_snapshot = list(self._pending_stops)
        stops_to_remove = set()
        for pending in stops_snapshot:
            if not self.portfolio.can_open(pending.order.group):
                break
            # Direction check within group
            if self._same_direction_only:
                group_positions = self.portfolio.positions_in_group(pending.order.group)
                if group_positions:
                    existing_side = group_positions[0].side
                    if pending.order.side != existing_side:
                        stops_to_remove.add(id(pending))
                        continue

            pending.bars_elapsed += 1

            filled, fill_price = self.execution.check_stop_fill(
                pending.order.stop_price, pending.order.side, bar
            )
            if filled:
                # Stop orders become market orders: apply entry slippage, taker fee
                fill_price = self.execution.apply_entry_slippage(
                    fill_price, pending.order.side
                )
                fill = self.portfolio.open_position(
                    bar, pending.order,
                    apply_slippage=False,
                    limit_price=fill_price,
                    is_maker=False,
                )
                self._emit("fill", fill)
                follow_up = self.strategy.on_fill(fill)
                self._handle_follow_up(follow_up)
                stops_to_remove.add(id(pending))
                just_opened = True
            elif (
                pending.order.timeout_bars > 0
                and pending.bars_elapsed >= pending.order.timeout_bars
            ):
                stops_to_remove.add(id(pending))

        if stops_to_remove:
            self._pending_stops = [
                p for p in self._pending_stops if id(p) not in stops_to_remove
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
            pos = self.portfolio.positions[idx]
            is_tp = "TAKE_PROFIT" in reason

            # Partial TP: close fraction, keep remainder open
            if (
                is_tp
                and pos.partial_tp_pct > 0
                and not pos.partial_tp_done
            ):
                trade = self.portfolio.close_position(
                    idx, exit_price, bar, "PARTIAL_TP",
                    close_pct=pos.partial_tp_pct,
                )
                pos.partial_tp_done = True
                # Update TP for remainder if configured
                if pos.partial_tp_new_tp_pct > 0:
                    if pos.is_long:
                        pos.take_profit = pos.entry_price * (1 + pos.partial_tp_new_tp_pct)
                    else:
                        pos.take_profit = pos.entry_price * (1 - pos.partial_tp_new_tp_pct)
                self._emit("exit", trade)
                follow_up = self.strategy.on_exit(
                    Fill(
                        timestamp=bar.timestamp,
                        side=trade.side,
                        price=trade.exit_price,
                        size_usd=trade.size_usd,
                        symbol=trade.symbol,
                        is_entry=False,
                        reason="PARTIAL_TP",
                    ),
                    trade,
                )
                self._handle_follow_up(follow_up)
                # Position still open — don't set just_closed
            else:
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
        for exit_tuple in sorted(
            strat_exits, key=lambda x: x[0], reverse=True
        ):
            pos_idx = exit_tuple[0]
            exit_price = exit_tuple[1]
            reason = exit_tuple[2]
            close_pct = exit_tuple[3] if len(exit_tuple) > 3 else 1.0

            if pos_idx < len(self.portfolio.positions):
                trade = self.portfolio.close_position(
                    pos_idx, exit_price, bar, reason,
                    close_pct=close_pct,
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
                if close_pct >= 1.0:
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
        self._pending_stops.clear()
