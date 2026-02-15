"""EquityPctSizer — size as a percentage of current equity."""

from __future__ import annotations

from .base import PositionSizer


class EquityPctSizer(PositionSizer):
    """Size positions as a percentage of current equity.

    Args:
        pct: Fraction of equity to allocate (e.g. 0.10 = 10%).
        min_size: Minimum position size in USD.
        max_size: Maximum position size in USD (0 = no cap).
    """

    def __init__(
        self,
        pct: float = 0.10,
        min_size: float = 100.0,
        max_size: float = 0.0,
    ):
        self.pct = pct
        self.min_size = min_size
        self.max_size = max_size

    def get_size(
        self,
        equity: float,
        side: str,
        price: float,
        symbol: str = "",
        stop_loss_pct: float = 0.0,
    ) -> float:
        size = equity * self.pct
        size = max(size, self.min_size)
        if self.max_size > 0:
            size = min(size, self.max_size)
        return size
