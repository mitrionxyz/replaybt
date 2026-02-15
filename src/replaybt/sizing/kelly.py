"""KellySizer — position sizing based on the Kelly criterion."""

from __future__ import annotations

from .base import PositionSizer


class KellySizer(PositionSizer):
    """Size positions using the Kelly criterion.

    The Kelly fraction maximizes long-term geometric growth:

        f* = (win_rate / avg_loss_ratio) - ((1 - win_rate) / avg_win_ratio)

    simplified to:

        f* = win_rate - (1 - win_rate) / payoff_ratio

    where payoff_ratio = avg_win / avg_loss.

    In practice, full Kelly is aggressive and assumes perfect parameter
    estimates. A fractional Kelly (e.g. 0.25-0.5) is standard to reduce
    variance and account for estimation error.

    Position size = equity * kelly_fraction * fraction.

    Args:
        win_rate: Historical win rate as fraction (e.g. 0.65 = 65%).
        avg_win: Average winning trade return as fraction (e.g. 0.08 = 8%).
        avg_loss: Average losing trade return as fraction (e.g. 0.035 = 3.5%).
        fraction: Kelly fraction multiplier (e.g. 0.25 = quarter Kelly).
        min_size: Minimum position size in USD.
        max_size: Maximum position size in USD (0 = no cap).
        max_equity_pct: Hard cap as fraction of equity (e.g. 0.25 = 25%).
    """

    def __init__(
        self,
        win_rate: float = 0.60,
        avg_win: float = 0.08,
        avg_loss: float = 0.035,
        fraction: float = 0.25,
        min_size: float = 100.0,
        max_size: float = 0.0,
        max_equity_pct: float = 0.25,
    ):
        if not 0 < win_rate < 1:
            raise ValueError(f"win_rate must be between 0 and 1, got {win_rate}")
        if avg_win <= 0:
            raise ValueError(f"avg_win must be positive, got {avg_win}")
        if avg_loss <= 0:
            raise ValueError(f"avg_loss must be positive, got {avg_loss}")
        if fraction <= 0:
            raise ValueError(f"fraction must be positive, got {fraction}")

        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss
        self.fraction = fraction
        self.min_size = min_size
        self.max_size = max_size
        self.max_equity_pct = max_equity_pct

    @property
    def kelly_fraction(self) -> float:
        """Raw Kelly fraction before applying the fractional multiplier.

        f* = win_rate - (1 - win_rate) / payoff_ratio
        """
        payoff_ratio = self.avg_win / self.avg_loss
        return self.win_rate - (1 - self.win_rate) / payoff_ratio

    def get_size(
        self,
        equity: float,
        side: str,
        price: float,
        symbol: str = "",
        stop_loss_pct: float = 0.0,
    ) -> float:
        f = self.kelly_fraction

        # Negative Kelly means no edge — use minimum size
        if f <= 0:
            return self.min_size

        alloc_pct = f * self.fraction

        # Cap at max equity percentage
        if self.max_equity_pct > 0:
            alloc_pct = min(alloc_pct, self.max_equity_pct)

        size = equity * alloc_pct
        size = max(size, self.min_size)
        if self.max_size > 0:
            size = min(size, self.max_size)
        return size
