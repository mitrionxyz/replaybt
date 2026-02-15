"""PositionSizer ABC — pluggable position sizing."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PositionSizer(ABC):
    """Abstract base for position sizing strategies.

    Subclass and implement get_size() to control how the engine
    determines USD size for new positions.
    """

    @abstractmethod
    def get_size(
        self,
        equity: float,
        side: str,
        price: float,
        symbol: str = "",
        stop_loss_pct: float = 0.0,
    ) -> float:
        """Return position size in USD.

        Args:
            equity: Current portfolio equity.
            side: "LONG" or "SHORT".
            price: Entry price.
            symbol: Asset symbol.
            stop_loss_pct: Stop loss as fraction (e.g. 0.035 = 3.5%).

        Returns:
            Position size in USD.
        """
        ...
