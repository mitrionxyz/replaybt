"""Strategy abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from ..data.types import Bar, Fill, Position, Trade
from ..engine.orders import Order, CancelPendingLimitsOrder


class Strategy(ABC):
    """Abstract base for all strategies.

    The engine calls on_bar() once per COMPLETED bar. Any Order
    returned will execute at the NEXT bar's open. The strategy
    cannot bypass this — the engine owns execution.

    Lifecycle:
        1. configure(config) — called once before run
        2. on_bar(bar, indicators, positions) — called per bar
        3. on_fill(fill) — called when an order fills
        4. on_exit(fill, trade) — called when a position closes

    Strategy-initiated closes:
        Override check_exits() for indicator-driven exits (e.g. HTF RSI).
        The engine calls it between Phase 3 (SL/TP) and Phase 4 (on_bar).
    """

    @abstractmethod
    def on_bar(
        self,
        bar: Bar,
        indicators: Dict[str, Any],
        positions: List[Position],
    ) -> Union[None, Order, List[Order]]:
        """Called with each COMPLETED bar.

        Args:
            bar: The completed bar.
            indicators: Current indicator values from IndicatorManager.
            positions: List of open positions.

        Returns:
            An Order, a list of Orders, or None.
            Last MarketOrder wins (overwrites pending). Multiple LimitOrders
            all append to pending limits.
        """
        ...

    def configure(self, config: dict) -> None:
        """Called once before the backtest starts.

        Override to set up strategy-specific state from config.
        """
        pass

    def on_fill(self, fill: Fill) -> Optional[Order]:
        """Called when an order fills (entry or scale-in).

        Override to track fills. Can return a follow-up Order:
        - LimitOrder: added to pending limits (e.g. DCA scale-in)
        - MarketOrder: set as pending for next bar
        """
        return None

    def on_exit(
        self, fill: Fill, trade: Trade,
    ) -> Union[None, Order, CancelPendingLimitsOrder]:
        """Called when a position closes.

        Override to track exits. Can return:
        - MarketOrder: set as pending for next bar (e.g. post-TP flip)
        - LimitOrder: added to pending limits
        - CancelPendingLimitsOrder: cancel all pending limit orders
        - None: no action
        """
        return None

    def check_exits(
        self, bar: Bar, positions: List[Position],
    ) -> List:
        """Called before on_bar to check for strategy-initiated exits.

        Override to implement indicator-driven exits (e.g. HTF RSI exit).
        Runs after engine SL/TP checks (Phase 3) but before signal
        generation (Phase 4). If any exits are returned, on_bar is skipped
        (matches reference backtest behavior).

        Args:
            bar: The current bar.
            positions: List of open positions.

        Returns:
            List of (position_idx, exit_price, reason) tuples to close.
        """
        return []

    def warmup_periods(self) -> Dict[str, int]:
        """Return required warmup bars per timeframe.

        Override to specify how many bars each indicator needs.
        Example: {'1h': 35, '30m': 35} for EMA(35) on each TF.
        """
        return {}
