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

    # TP/SL as percentages from entry price
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None

    # Breakeven management
    breakeven_trigger_pct: Optional[float] = None  # e.g. 0.015 = +1.5%
    breakeven_lock_pct: Optional[float] = None      # e.g. 0.005 = +0.5%

    # Scale-in configuration
    scale_in_enabled: bool = False
    scale_in_dip_pct: float = 0.002       # -0.2% dip
    scale_in_size_pct: float = 0.5        # 50% of main
    scale_in_timeout: int = 48            # bars


@dataclass(slots=True)
class MarketOrder(Order):
    """Market order — fills at next bar's open + slippage."""
    pass


@dataclass(slots=True)
class LimitOrder(Order):
    """Limit order — fills when price reaches limit_price."""
    limit_price: float = 0.0
    timeout_bars: int = 0  # 0 = no timeout
