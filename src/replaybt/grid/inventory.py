"""Inventory Tracker: Tracks net position, calculates skew adjustments,
and enforces inventory limits.

Port of Mitrion's inventory_manager.py with replaybt types.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import OrderSide


@dataclass
class InventoryState:
    """Internal state for inventory tracking."""

    base_position: float = 0.0  # net base (e.g., ETH). Positive = long
    quote_position: float = 0.0  # net quote (e.g., USDC)
    total_base_bought: float = 0.0
    total_base_sold: float = 0.0
    total_quote_spent: float = 0.0
    total_quote_received: float = 0.0
    peak_equity: float = 0.0
    cumulative_spread_captured: float = 0.0


class InventoryTracker:
    """Tracks inventory and computes skew/limit adjustments."""

    def __init__(
        self,
        max_inventory_base: float,
        skew_factor: float = 0.0005,
        max_skew: float = 0.01,
        initial_quote: float = 0.0,
    ) -> None:
        self.max_inventory_base = max_inventory_base
        self.skew_factor = skew_factor
        self.max_skew = max_skew
        self.state = InventoryState(quote_position=initial_quote)
        self.state.peak_equity = initial_quote

    def record_fill(
        self, side: OrderSide, size: float, price: float, spread_earned: float
    ) -> None:
        """Record a fill and update inventory."""
        if side == OrderSide.BID:
            self.state.base_position += size
            self.state.quote_position -= size * price
            self.state.total_base_bought += size
            self.state.total_quote_spent += size * price
        else:
            self.state.base_position -= size
            self.state.quote_position += size * price
            self.state.total_base_sold += size
            self.state.total_quote_received += size * price

        self.state.cumulative_spread_captured += spread_earned

    def get_equity(self, mid_price: float) -> float:
        """Calculate total equity (mark-to-market) in quote currency."""
        return self.state.quote_position + self.state.base_position * mid_price

    def update_peak_equity(self, mid_price: float) -> None:
        """Update peak equity for drawdown tracking."""
        equity = self.get_equity(mid_price)
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity

    def get_drawdown(self, mid_price: float) -> float:
        """Current drawdown as a fraction (0.0 = none, 0.1 = 10% from peak)."""
        equity = self.get_equity(mid_price)
        if self.state.peak_equity <= 0:
            return 0.0
        return max(0.0, 1.0 - equity / self.state.peak_equity)

    def get_skew(self) -> float:
        """Calculate price skew based on current inventory.

        Returns a fraction to shift prices by.
        Negative = shift down (encourage selling when long).
        """
        if self.max_inventory_base <= 0:
            return 0.0
        inv_ratio = self.state.base_position / self.max_inventory_base
        skew = -inv_ratio * self.skew_factor * self.max_inventory_base
        return max(-self.max_skew, min(self.max_skew, skew))

    def can_buy(self) -> bool:
        """Check if we're allowed to place new bids (not at max long inventory)."""
        return self.state.base_position < self.max_inventory_base

    def can_sell(self) -> bool:
        """Check if we're allowed to place new asks (not at max short inventory)."""
        return self.state.base_position > -self.max_inventory_base

    def inventory_pnl(self, mid_price: float) -> float:
        """Unrealized PnL from holding inventory."""
        if abs(self.state.base_position) < 1e-12:
            return 0.0
        if self.state.total_base_bought > 0:
            avg_buy = self.state.total_quote_spent / self.state.total_base_bought
        else:
            avg_buy = mid_price
        return self.state.base_position * (mid_price - avg_buy)

    def get_inventory_pct(self) -> float:
        """Current inventory as percentage of max. 0% = flat, 100% = at limit."""
        if self.max_inventory_base <= 0:
            return 0.0
        return abs(self.state.base_position) / self.max_inventory_base * 100

    def get_signed_inventory_pct(self) -> float:
        """Signed inventory as fraction of max. -1.0 to 1.0."""
        if self.max_inventory_base <= 0:
            return 0.0
        return self.state.base_position / self.max_inventory_base
