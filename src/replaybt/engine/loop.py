"""BacktestEngine: the execution loop.

This is the core of replaybt. The engine enforces realistic execution:

Per bar:
  Phase 1: Execute pending market orders at bar OPEN + adverse slippage
  Phase 1b: Check pending limit orders for fills (incl. merge_position)
  Phase 3: Check exits (open gap FIRST, then High/Low vs SL/TP)
  Phase 3.5: Strategy-initiated exits
  Phase 4: Call strategy.on_bar() with COMPLETED bar → sets pending for next bar

The strategy NEVER sees current-bar data during signal generation.
The strategy CANNOT bypass the execution loop.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from ..data.types import Bar, Fill, Position, Trade, Side
from ..data.providers.base import DataProvider
from ..indicators.base import IndicatorManager
from ..strategy.base import Strategy
from ..reporting.metrics import BacktestResults
from .execution import ExecutionModel
from .orders import Order, MarketOrder, LimitOrder, CancelPendingLimitsOrder
from .portfolio import Portfolio
from .processor import BarProcessor, _PendingLimit, _PendingStop  # noqa: F401 — re-export for StepEngine


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

        # Build processor (delegates the 4-phase loop)
        self._processor = BarProcessor(
            portfolio=self.portfolio,
            indicators=self.indicators,
            execution=self.execution,
            strategy=self.strategy,
            config=self.config,
            callbacks=self._callbacks,
        )

        # Configure strategy
        self.strategy.configure(self.config)

    # ------------------------------------------------------------------
    # Property delegation for StepEngine compatibility
    # StepEngine accesses _pending_order and _pending_limits directly.
    # ------------------------------------------------------------------

    @property
    def _pending_order(self):
        return self._processor._pending_order

    @_pending_order.setter
    def _pending_order(self, value):
        self._processor._pending_order = value

    @property
    def _pending_limits(self):
        return self._processor._pending_limits

    @_pending_limits.setter
    def _pending_limits(self, value):
        self._processor._pending_limits = value

    @property
    def _pending_stops(self):
        return self._processor._pending_stops

    @_pending_stops.setter
    def _pending_stops(self, value):
        self._processor._pending_stops = value

    # Behavior flags (read-only, exposed for tests/introspection)
    @property
    def _skip_signal_on_close(self):
        return self._processor._skip_signal_on_close

    @property
    def _same_direction_only(self):
        return self._processor._same_direction_only

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
        self._processor.reset()
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
        self._processor.reset()
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

    def _process_bar(self, bar: Bar) -> None:
        """Process a single bar through the 4-phase loop."""
        self._bar_count += 1
        self._processor.process_bar(bar)
