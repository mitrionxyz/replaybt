"""RiskPctSizer — size based on risk percentage and stop loss distance."""

from __future__ import annotations

from .base import PositionSizer


class RiskPctSizer(PositionSizer):
    """Size positions so that a stop loss hit loses at most risk_pct of equity.

    Formula: size = (equity * risk_pct) / stop_loss_pct

    Args:
        risk_pct: Max fraction of equity to risk per trade (e.g. 0.01 = 1%).
        min_size: Minimum position size in USD.
        max_size: Maximum position size in USD (0 = no cap).
        default_sl_pct: Fallback SL% when order has no stop_loss_pct.
    """

    def __init__(
        self,
        risk_pct: float = 0.01,
        min_size: float = 100.0,
        max_size: float = 0.0,
        default_sl_pct: float = 0.035,
    ):
        self.risk_pct = risk_pct
        self.min_size = min_size
        self.max_size = max_size
        self.default_sl_pct = default_sl_pct

    def get_size(
        self,
        equity: float,
        side: str,
        price: float,
        symbol: str = "",
        stop_loss_pct: float = 0.0,
    ) -> float:
        sl = stop_loss_pct if stop_loss_pct > 0 else self.default_sl_pct
        size = (equity * self.risk_pct) / sl
        size = max(size, self.min_size)
        if self.max_size > 0:
            size = min(size, self.max_size)
        return size
