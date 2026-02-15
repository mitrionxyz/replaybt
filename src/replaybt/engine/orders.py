"""Order types for the engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..data.types import Side, OrderType


@dataclass(slots=True)
class Order:
    """Base order. Strategy returns these from on_bar()."""
    side: Side
    size_usd: Optional[float] = None  # None = use default from config
    symbol: str = ""
    group: Optional[str] = None  # position group for independent tracking

    # TP/SL as percentages from entry price
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None

    # Breakeven management
    breakeven_trigger_pct: Optional[float] = None  # e.g. 0.015 = +1.5%
    breakeven_lock_pct: Optional[float] = None      # e.g. 0.005 = +0.5%

    # Trailing stop
    trailing_stop_pct: Optional[float] = None       # distance from peak/trough (e.g. 0.05 = 5%)
    trailing_stop_activation_pct: Optional[float] = None  # min profit to activate (None/0 = immediate)

    # Partial take profit
    partial_tp_pct: Optional[float] = None        # fraction to close at TP (0.5 = 50%)
    partial_tp_new_tp_pct: Optional[float] = None  # new TP% for remainder after partial

    # Cancel pending limit orders when this order is processed
    cancel_pending_limits: bool = False


@dataclass(slots=True)
class MarketOrder(Order):
    """Market order — fills at next bar's open + slippage."""
    pass


@dataclass(slots=True)
class LimitOrder(Order):
    """Limit order — fills when price reaches limit_price."""
    limit_price: float = 0.0
    timeout_bars: int = 0  # 0 = no timeout
    use_maker_fee: bool = True  # False = use taker fee (e.g. DCA fills)
    min_positions: int = 0  # only fill when >= N positions exist (e.g. DCA needs 1)
    merge_position: bool = False  # merge into existing position instead of opening new


@dataclass(slots=True)
class StopOrder(Order):
    """Stop order — fills when price breaks through stop_price.

    LONG stop: fills when bar.high >= stop_price (breakout above).
    SHORT stop: fills when bar.low <= stop_price (breakdown below).
    Becomes market order on trigger: taker fee + slippage.
    Gap-through: if bar opens past stop_price, fill at open (worse).
    """
    stop_price: float = 0.0
    timeout_bars: int = 0


class CancelPendingLimitsOrder:
    """Sentinel: return from on_exit/on_fill to cancel all pending limit orders.

    Use when you need to clear pending limits without placing a new order.
    For clearing limits AND placing an order, set cancel_pending_limits=True
    on the Order instead.
    """
    pass
