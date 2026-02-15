"""FixedSizer — constant USD position size."""

from __future__ import annotations

from .base import PositionSizer


class FixedSizer(PositionSizer):
    """Always returns the same fixed USD size.

    This is the default behavior when no sizer is configured.

    Args:
        size_usd: Fixed position size in USD.
    """

    def __init__(self, size_usd: float = 10_000.0):
        self.size_usd = size_usd

    def get_size(
        self,
        equity: float,
        side: str,
        price: float,
        symbol: str = "",
        stop_loss_pct: float = 0.0,
    ) -> float:
        return self.size_usd
