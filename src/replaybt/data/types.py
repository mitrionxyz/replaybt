"""Core data types used throughout replaybt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_GAP = "STOP_LOSS_GAP"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_GAP = "TAKE_PROFIT_GAP"
    BREAKEVEN = "BREAKEVEN"
    BREAKEVEN_GAP = "BREAKEVEN_GAP"
    TRAILING_STOP = "TRAILING_STOP"
    TRAILING_STOP_GAP = "TRAILING_STOP_GAP"
    PARTIAL_TP = "PARTIAL_TP"
    SIGNAL = "SIGNAL"


@dataclass(frozen=True, slots=True)
class Bar:
    """Universal OHLCV data unit."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""
    timeframe: str = "1m"


@dataclass(slots=True)
class Position:
    """An open position tracked by the portfolio."""
    side: Side
    entry_price: float
    entry_time: datetime
    size_usd: float
    stop_loss: float
    take_profit: float
    symbol: str = ""
    breakeven_activated: bool = False
    breakeven_trigger: float = 0.0
    breakeven_lock: float = 0.0
    # Trailing stop
    trailing_stop_pct: float = 0.0
    trailing_stop_activation_pct: float = 0.0
    position_high: float = 0.0
    position_low: float = 0.0
    trailing_stop_activated: bool = False
    # Partial take profit
    partial_tp_pct: float = 0.0
    partial_tp_new_tp_pct: float = 0.0
    partial_tp_done: bool = False
    group: Optional[str] = None

    @property
    def is_long(self) -> bool:
        return self.side == Side.LONG


@dataclass(frozen=True, slots=True)
class Fill:
    """A completed fill (entry or exit)."""
    timestamp: datetime
    side: Side
    price: float
    size_usd: float
    symbol: str = ""
    fees: float = 0.0
    slippage_cost: float = 0.0
    is_entry: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Trade:
    """A completed round-trip trade (entry + exit)."""
    entry_time: datetime
    exit_time: datetime
    side: Side
    entry_price: float
    exit_price: float
    size_usd: float
    pnl_usd: float
    pnl_pct: float
    fees: float
    reason: str
    symbol: str = ""
    is_partial: bool = False
    group: Optional[str] = None


@dataclass(slots=True)
class PendingOrder:
    """An order waiting to execute at the next bar's open."""
    side: Side
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    size_usd: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    symbol: str = ""
    # For limit orders: timeout tracking
    bars_elapsed: int = 0
    max_bars: int = 0


