"""BacktestEngine: the 4-phase execution loop.

This is the core of replaybt. The engine enforces realistic execution:

Per bar:
  Phase 1: Execute pending orders at bar OPEN + adverse slippage
  Phase 2: Check scale-in limit orders
  Phase 3: Check exits (open gap FIRST, then High/Low vs SL/TP)
  Phase 4: Call strategy.on_bar() with COMPLETED bar → sets pending for next bar

The strategy NEVER sees current-bar data during signal generation.
The strategy CANNOT bypass the 4-phase loop.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from ..data.types import Bar, Fill, Position, Trade, Side
from ..data.providers.base import DataProvider
from ..indicators.base import IndicatorManager
from ..strategy.base import Strategy
from ..reporting.metrics import BacktestResults
from .execution import ExecutionModel
from .orders import Order, MarketOrder
from .portfolio import Portfolio


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

        # Pending order from strategy (executes at next bar's open)
        self._pending_order: Optional[Order] = None

        # Event callbacks
        self._callbacks: Dict[str, List[Callable]] = {
            "bar": [],
            "fill": [],
            "exit": [],
            "signal": [],
        }

        # Bar counter
        self._bar_count = 0

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

    def run(self) -> BacktestResults:
        """Execute the backtest. Returns results with all metrics."""
        self.portfolio.reset()
        self.indicators.reset()
        self._pending_order = None
        self._bar_count = 0

        for bar in self.data:
            self._process_bar(bar)

        return BacktestResults.from_portfolio(
            self.portfolio,
            symbol=self.data.symbol(),
        )

    def _process_bar(self, bar: Bar) -> None:
        """Process a single bar through the 4-phase loop."""
        self._bar_count += 1

        # ============================================================
        # PHASE 1: Execute pending orders at bar OPEN
        # ============================================================
        just_opened = False
        if self._pending_order is not None and self.portfolio.can_open():
            order = self._pending_order
            self._pending_order = None

            # For multi-position: ensure same direction
            if self.portfolio.has_position:
                existing_side = self.portfolio.positions[0].side
                if order.side != existing_side:
                    order = None  # Skip conflicting direction

            if order is not None:
                fill = self.portfolio.open_position(bar, order)
                self._emit("fill", fill)
                self.strategy.on_fill(fill)
                just_opened = True

        # ============================================================
        # PHASE 2: Check scale-in limit orders
        # ============================================================
        scale_fill = self.portfolio.check_scale_in(bar)
        if scale_fill:
            self._emit("fill", scale_fill)
            self.strategy.on_fill(scale_fill)

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
            self.strategy.on_exit(
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
            just_closed = True

        # ============================================================
        # PHASE 4: Update indicators and generate signal
        # ============================================================
        self.indicators.update(bar)
        self._emit("bar", bar)

        # Don't signal on the same bar a position just closed
        # (matches live bot: can't close + signal in same tick)
        if just_closed:
            return

        # Get indicator values for the strategy
        indicator_values = self.indicators.values()

        # Call strategy
        order = self.strategy.on_bar(
            bar=bar,
            indicators=indicator_values,
            positions=list(self.portfolio.positions),
        )

        if order is not None:
            self._pending_order = order
            self._emit("signal", order)
