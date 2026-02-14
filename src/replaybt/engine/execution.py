"""Execution model: slippage, fees, gap protection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..data.types import Bar, Fill, Position, Side


@dataclass(slots=True)
class ExecutionModel:
    """Handles realistic order execution.

    Applies:
    - Adverse slippage on market orders
    - Taker/maker fees
    - Gap protection on exits (open gapped past SL/TP)

    Args:
        slippage: Slippage per side as decimal (0.0002 = 0.02%).
        taker_fee: Taker fee per side as decimal (0.00015 = 0.015%).
        maker_fee: Maker fee per side as decimal (0.0 for limit orders).
    """
    slippage: float = 0.0002
    taker_fee: float = 0.00015
    maker_fee: float = 0.0

    def apply_entry_slippage(self, price: float, side: Side) -> float:
        """Apply adverse slippage to entry price.

        LONG: price goes UP (you pay more).
        SHORT: price goes DOWN (you receive less).
        """
        if side == Side.LONG:
            return price * (1 + self.slippage)
        else:
            return price * (1 - self.slippage)

    def apply_exit_slippage(self, price: float, side: Side) -> float:
        """Apply adverse slippage to exit price.

        LONG exit: price goes DOWN (you receive less).
        SHORT exit: price goes UP (you pay more).
        """
        if side == Side.LONG:
            return price * (1 - self.slippage)
        else:
            return price * (1 + self.slippage)

    def calc_fees(self, size_usd: float, is_maker: bool = False) -> float:
        """Calculate fee for one side of a trade."""
        rate = self.maker_fee if is_maker else self.taker_fee
        return size_usd * rate

    def check_exit(
        self, pos: Position, bar: Bar
    ) -> Tuple[Optional[float], Optional[str]]:
        """Check if a position should exit on this bar.

        Checks in order:
        1. Breakeven trigger (updates SL if activated)
        2. Open gap past SL → exit at open (gap protection)
        3. Intra-bar SL hit → exit at SL level
        4. Open gap past TP → exit at open (gap protection)
        5. Intra-bar TP hit → exit at TP level

        Returns:
            (exit_price, reason) or (None, None) if no exit.
            exit_price is the RAW price before slippage.
        """
        open_price = bar.open
        high = bar.high
        low = bar.low

        # Update breakeven if triggered
        if not pos.breakeven_activated and pos.breakeven_trigger > 0:
            if pos.is_long:
                move_pct = (high - pos.entry_price) / pos.entry_price
                if move_pct >= pos.breakeven_trigger:
                    pos.stop_loss = pos.entry_price * (1 + pos.breakeven_lock)
                    pos.breakeven_activated = True
            else:
                move_pct = (pos.entry_price - low) / pos.entry_price
                if move_pct >= pos.breakeven_trigger:
                    pos.stop_loss = pos.entry_price * (1 - pos.breakeven_lock)
                    pos.breakeven_activated = True

        if pos.is_long:
            # GAP PROTECTION: open gapped below SL
            if open_price <= pos.stop_loss:
                reason = "BREAKEVEN_GAP" if pos.breakeven_activated else "STOP_LOSS_GAP"
                return open_price, reason
            # Intra-bar SL
            if low <= pos.stop_loss:
                reason = "BREAKEVEN" if pos.breakeven_activated else "STOP_LOSS"
                return pos.stop_loss, reason
            # GAP PROTECTION: open gapped above TP
            if open_price >= pos.take_profit:
                return open_price, "TAKE_PROFIT_GAP"
            # Intra-bar TP
            if high >= pos.take_profit:
                return pos.take_profit, "TAKE_PROFIT"
        else:
            # GAP PROTECTION: open gapped above SL
            if open_price >= pos.stop_loss:
                reason = "BREAKEVEN_GAP" if pos.breakeven_activated else "STOP_LOSS_GAP"
                return open_price, reason
            # Intra-bar SL
            if high >= pos.stop_loss:
                reason = "BREAKEVEN" if pos.breakeven_activated else "STOP_LOSS"
                return pos.stop_loss, reason
            # GAP PROTECTION: open gapped below TP
            if open_price <= pos.take_profit:
                return open_price, "TAKE_PROFIT_GAP"
            # Intra-bar TP
            if low <= pos.take_profit:
                return pos.take_profit, "TAKE_PROFIT"

        return None, None

    def check_limit_fill(
        self, limit_price: float, side: Side, bar: Bar
    ) -> bool:
        """Check if a limit order would fill on this bar.

        LONG limit: fills when low <= limit_price.
        SHORT limit: fills when high >= limit_price.
        """
        if side == Side.LONG:
            return bar.low <= limit_price
        else:
            return bar.high >= limit_price
