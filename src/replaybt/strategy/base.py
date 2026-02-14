"""Strategy abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..data.types import Bar, Fill, Position, Trade
from ..engine.orders import Order


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
    """

    @abstractmethod
    def on_bar(
        self,
        bar: Bar,
        indicators: Dict[str, Any],
        positions: List[Position],
    ) -> Optional[Order]:
        """Called with each COMPLETED bar.

        Args:
            bar: The completed bar.
            indicators: Current indicator values from IndicatorManager.
            positions: List of open positions.

        Returns:
            An Order to execute at NEXT bar's open, or None.
        """
        ...

    def configure(self, config: dict) -> None:
        """Called once before the backtest starts.

        Override to set up strategy-specific state from config.
        """
        pass

    def on_fill(self, fill: Fill) -> None:
        """Called when an order fills (entry or scale-in).

        Override to track fills.
        """
        pass

    def on_exit(self, fill: Fill, trade: Trade) -> None:
        """Called when a position closes.

        Override to track exits or implement post-exit logic.
        """
        pass

    def warmup_periods(self) -> Dict[str, int]:
        """Return required warmup bars per timeframe.

        Override to specify how many bars each indicator needs.
        Example: {'1h': 35, '30m': 35} for EMA(35) on each TF.
        """
        return {}
