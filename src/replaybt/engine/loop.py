"""BacktestEngine: the 4-phase execution loop.

This is the core of replaybt. The engine enforces realistic execution:

Per bar:
  Phase 1: Execute pending market orders at bar OPEN + adverse slippage
  Phase 1b: Check pending limit orders for fills
  Phase 2: Check scale-in limit orders
  Phase 3: Check exits (open gap FIRST, then High/Low vs SL/TP)
  Phase 4: Call strategy.on_bar() with COMPLETED bar → sets pending for next bar

The strategy NEVER sees current-bar data during signal generation.
The strategy CANNOT bypass the 4-phase loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..data.types import Bar, Fill, Position, Trade, Side
from ..data.providers.base import DataProvider
from ..indicators.base import IndicatorManager
from ..strategy.base import Strategy
from ..reporting.metrics import BacktestResults
from .execution import ExecutionModel
from .orders import Order, MarketOrder, LimitOrder, CancelPendingLimitsOrder
from .portfolio import Portfolio


@dataclass(slots=True)
class _PendingLimit:
    """Internal tracker for a pending limit order."""
    order: LimitOrder
    bars_elapsed: int = 0


class BacktestEngine:
    """Run a strategy against historical data with realistic execution.

    Args:
        strategy: Strategy instance implementing on_bar().
        data: DataProvider yielding 1m bars.
        config: Engine configuration dict.

    Config keys:
        initial_equity: Starting equity (default 10000).
        default_size_usd: Default position size (default 10000).
        max_positions: Max concurrent positions (default 1).
        slippage: Per-side slippage (default 0.0002).
        taker_fee: Per-side taker fee (default 0.00015).
        maker_fee: Per-side maker fee (default 0.0).
        indicators: Dict of indicator configs for IndicatorManager.
        skip_signal_on_close: Skip on_bar on bars where a position closed
            (default True). Set False for mean-reversion re-entry.
        same_direction_only: Reject orders in opposite direction to existing
            positions (default True). Set False to allow hedging.
    """

    def __init__(
        self,
        strategy: Strategy,
        data: DataProvider,
        config: Optional[Dict] = None,
    ):
        self.strategy = strategy
        self.data = data
        self.config = config or {}

        # Build execution model
        self.execution = ExecutionModel(
            slippage=self.config.get("slippage", 0.0002),
            taker_fee=self.config.get("taker_fee", 0.00015),
            maker_fee=self.config.get("maker_fee", 0.0),
        )

        # Build portfolio
        self.portfolio = Portfolio(
            initial_equity=self.config.get("initial_equity", 10_000.0),
            default_size_usd=self.config.get("default_size_usd", 10_000.0),
            execution=self.execution,
            max_positions=self.config.get("max_positions", 1),
        )

        # Build indicator manager
        self.indicators = IndicatorManager(
            self.config.get("indicators", {})
        )

        # Pending market order from strategy (executes at next bar's open)
        self._pending_order: Optional[Order] = None

        # Pending limit orders (checked each bar until fill or timeout)
        self._pending_limits: List[_PendingLimit] = []

        # Event callbacks
        self._callbacks: Dict[str, List[Callable]] = {
            "bar": [],
            "fill": [],
            "exit": [],
            "signal": [],
        }

        # Bar counter
        self._bar_count = 0

        # Track first/last bar for buy-and-hold comparison
        self._first_bar: Optional[Bar] = None
        self._last_bar: Optional[Bar] = None

        # Behavior flags (backwards-compatible defaults)
        self._skip_signal_on_close = self.config.get("skip_signal_on_close", True)
        self._same_direction_only = self.config.get("same_direction_only", True)

        # Configure strategy
        self.strategy.configure(self.config)

    def on(self, event: str, callback: Callable) -> "BacktestEngine":
        """Register an event callback.

        Events: 'bar', 'fill', 'exit', 'signal'
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
        return self

    def _emit(self, event: str, *args) -> None:
        for cb in self._callbacks.get(event, []):
            cb(*args)

    async def run_async(self, data) -> BacktestResults:
        """Run with async data source (live/paper trading).

        Same 4-phase execution as run(), but consumes bars from an
        AsyncDataProvider via ``async for``. Strategy.on_bar() stays
        synchronous -- only data delivery is async.

        Args:
            data: AsyncDataProvider yielding bars.
                  Warmup should be called before run_async().

        Returns:
            BacktestResults (same as run()).
        """
        self.portfolio.reset()
        self.indicators.reset()
        self._pending_order = None
        self._pending_limits.clear()
        self._bar_count = 0
        self._first_bar = None
        self._last_bar = None

        async for bar in data:
            if self._first_bar is None:
                self._first_bar = bar
            self._last_bar = bar
            self._process_bar(bar)

        return BacktestResults.from_portfolio(
            self.portfolio,
            symbol=data.symbol(),
            first_bar=self._first_bar,
            last_bar=self._last_bar,
        )

    def run(self) -> BacktestResults:
        """Execute the backtest. Returns results with all metrics."""
        self.portfolio.reset()
        self.indicators.reset()
        self._pending_order = None
        self._pending_limits.clear()
        self._bar_count = 0
        self._first_bar = None
        self._last_bar = None

        for bar in self.data:
            if self._first_bar is None:
                self._first_bar = bar
            self._last_bar = bar
            self._process_bar(bar)

        return BacktestResults.from_portfolio(
            self.portfolio,
            symbol=self.data.symbol(),
            first_bar=self._first_bar,
            last_bar=self._last_bar,
        )

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

    def _process_bar(self, bar: Bar) -> None:
        """Process a single bar through the 4-phase loop."""
        self._bar_count += 1

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
        filled_indices = []
        for i, pending in enumerate(self._pending_limits):
            if not self.portfolio.can_open():
                break
            # Direction check (unless hedging enabled)
            if self._same_direction_only and self.portfolio.has_position:
                existing_side = self.portfolio.positions[0].side
                if pending.order.side != existing_side:
                    filled_indices.append(i)  # Remove conflicting
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
                fill = self.portfolio.open_position(
                    bar, pending.order,
                    apply_slippage=False,
                    limit_price=pending.order.limit_price,
                    is_maker=pending.order.use_maker_fee,
                )
                self._emit("fill", fill)
                follow_up = self.strategy.on_fill(fill)
                self._handle_follow_up(follow_up)
                filled_indices.append(i)
                just_opened = True
            elif (
                pending.order.timeout_bars > 0
                and pending.bars_elapsed >= pending.order.timeout_bars
            ):
                filled_indices.append(i)  # Timed out

        # Remove filled/timed-out limit orders (reverse to preserve indices)
        for i in reversed(filled_indices):
            self._pending_limits.pop(i)

        # ============================================================
        # PHASE 2: Check scale-in limit orders
        # ============================================================
        scale_fill = self.portfolio.check_scale_in(bar)
        if scale_fill:
            self._emit("fill", scale_fill)
            follow_up = self.strategy.on_fill(scale_fill)
            self._handle_follow_up(follow_up)

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

        # Call strategy — normalize result to list
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
