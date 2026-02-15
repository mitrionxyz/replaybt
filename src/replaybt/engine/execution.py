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

        # Trailing stop: ratchet SL toward price (based on extremes seen so far)
        if pos.trailing_stop_pct > 0:
            if pos.is_long:
                profit_pct = (pos.position_high - pos.entry_price) / pos.entry_price
                if profit_pct >= pos.trailing_stop_activation_pct:
                    pos.trailing_stop_activated = True
                    trail_sl = pos.position_high * (1 - pos.trailing_stop_pct)
                    pos.stop_loss = max(pos.stop_loss, trail_sl)
            else:
                profit_pct = (pos.entry_price - pos.position_low) / pos.entry_price
                if profit_pct >= pos.trailing_stop_activation_pct:
                    pos.trailing_stop_activated = True
                    trail_sl = pos.position_low * (1 + pos.trailing_stop_pct)
                    pos.stop_loss = min(pos.stop_loss, trail_sl) if pos.stop_loss > 0 else trail_sl

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
                if pos.trailing_stop_activated:
                    reason = "TRAILING_STOP_GAP"
                elif pos.breakeven_activated:
                    reason = "BREAKEVEN_GAP"
                else:
                    reason = "STOP_LOSS_GAP"
                return open_price, reason
            # Intra-bar SL
            if low <= pos.stop_loss:
                if pos.trailing_stop_activated:
                    reason = "TRAILING_STOP"
                elif pos.breakeven_activated:
                    reason = "BREAKEVEN"
                else:
                    reason = "STOP_LOSS"
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
                if pos.trailing_stop_activated:
                    reason = "TRAILING_STOP_GAP"
                elif pos.breakeven_activated:
                    reason = "BREAKEVEN_GAP"
                else:
                    reason = "STOP_LOSS_GAP"
                return open_price, reason
            # Intra-bar SL
            if high >= pos.stop_loss:
                if pos.trailing_stop_activated:
                    reason = "TRAILING_STOP"
                elif pos.breakeven_activated:
                    reason = "BREAKEVEN"
                else:
                    reason = "STOP_LOSS"
                return pos.stop_loss, reason
            # GAP PROTECTION: open gapped below TP
            if open_price <= pos.take_profit:
                return open_price, "TAKE_PROFIT_GAP"
            # Intra-bar TP
            if low <= pos.take_profit:
                return pos.take_profit, "TAKE_PROFIT"

        # Track position extremes for next bar's trailing stop
        pos.position_high = max(pos.position_high, high)
        pos.position_low = min(pos.position_low, low)

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

    def check_stop_fill(
        self, stop_price: float, side: Side, bar: Bar
    ) -> Tuple[bool, float]:
        """Check if a stop order would fill on this bar.

        LONG stop: fills when bar.high >= stop_price (breakout above).
        SHORT stop: fills when bar.low <= stop_price (breakdown below).
        Gap-through: if bar opens past stop_price, fill at open (worse).

        Returns:
            (filled, fill_price). fill_price is 0.0 if not filled.
        """
        if side == Side.LONG:
            if bar.open >= stop_price:
                return True, bar.open  # gap through
            if bar.high >= stop_price:
                return True, stop_price
        else:
            if bar.open <= stop_price:
                return True, bar.open  # gap through
            if bar.low <= stop_price:
                return True, stop_price
        return False, 0.0
