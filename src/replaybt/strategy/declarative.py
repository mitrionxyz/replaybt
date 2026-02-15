"""DeclarativeStrategy: JSON config to Strategy for AI agents.

Converts a JSON configuration into a fully functional Strategy instance.
Targets TrendMaster-class patterns (multi-TF crossover + filter + threshold).

Usage:
    strategy = DeclarativeStrategy.from_json('trendmaster_eth.json')
    engine = BacktestEngine(strategy=strategy, data=provider, config={...})
    results = engine.run()
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from ..data.types import Bar, Fill, Position, Side, Trade
from ..engine.orders import MarketOrder, LimitOrder, Order, CancelPendingLimitsOrder
from .base import Strategy


# ── Typed condition dataclasses ──────────────────────────────────────────


@dataclass(frozen=True)
class CrossoverCondition:
    """fast crosses above slow (or vice versa for crossunder)."""
    fast: str
    slow: str
    is_crossunder: bool = False


@dataclass(frozen=True)
class CompareCondition:
    """left > right (above) or left < right (below)."""
    left: str
    right: str
    op: str  # "above" or "below"


@dataclass(frozen=True)
class ThresholdCondition:
    """indicator vs fixed value with various operators."""
    indicator: str
    value: float
    op: str  # "above_threshold", "below_threshold", "crosses_above", "crosses_below"


Condition = Union[CrossoverCondition, CompareCondition, ThresholdCondition]


# ── Standalone evaluation functions ──────────────────────────────────────


def resolve_operand(
    name: str, bar: Bar, indicators: Dict[str, Any],
) -> Optional[float]:
    """Resolve 'bar.close' or indicator name to float.

    Returns None if the indicator doesn't exist or hasn't warmed up.
    """
    if name.startswith("bar."):
        attr = name[4:]
        return getattr(bar, attr, None)
    return indicators.get(name)


def evaluate_condition(
    cond: Condition,
    bar: Bar,
    indicators: Dict[str, Any],
    prev_indicators: Dict[str, Any],
) -> bool:
    """Evaluate one condition. Returns False if any operand is None."""
    if isinstance(cond, CrossoverCondition):
        fast_now = resolve_operand(cond.fast, bar, indicators)
        slow_now = resolve_operand(cond.slow, bar, indicators)
        fast_prev = resolve_operand(cond.fast, bar, prev_indicators)
        slow_prev = resolve_operand(cond.slow, bar, prev_indicators)

        if any(v is None for v in (fast_now, slow_now, fast_prev, slow_prev)):
            return False

        if cond.is_crossunder:
            return fast_now < slow_now and fast_prev >= slow_prev
        return fast_now > slow_now and fast_prev <= slow_prev

    elif isinstance(cond, CompareCondition):
        left = resolve_operand(cond.left, bar, indicators)
        right = resolve_operand(cond.right, bar, indicators)

        if left is None or right is None:
            return False

        if cond.op == "above":
            return left > right
        return left < right  # "below"

    elif isinstance(cond, ThresholdCondition):
        curr = resolve_operand(cond.indicator, bar, indicators)
        if curr is None:
            return False

        if cond.op == "above_threshold":
            return curr > cond.value
        elif cond.op == "below_threshold":
            return curr <= cond.value
        elif cond.op == "crosses_above":
            prev = resolve_operand(cond.indicator, bar, prev_indicators)
            if prev is None:
                return False
            return curr > cond.value and prev <= cond.value
        elif cond.op == "crosses_below":
            prev = resolve_operand(cond.indicator, bar, prev_indicators)
            if prev is None:
                return False
            return curr < cond.value and prev >= cond.value

    return False


def evaluate_all(
    conditions: List[Condition],
    bar: Bar,
    indicators: Dict[str, Any],
    prev_indicators: Dict[str, Any],
) -> bool:
    """AND-chain: all conditions must pass."""
    if not conditions:
        return False
    return all(
        evaluate_condition(c, bar, indicators, prev_indicators)
        for c in conditions
    )


# ── Parsing ──────────────────────────────────────────────────────────────


def parse_condition(raw: dict) -> Condition:
    """Parse a single JSON condition dict into a typed dataclass."""
    ctype = raw["type"]

    if ctype == "crossover":
        return CrossoverCondition(fast=raw["fast"], slow=raw["slow"])
    elif ctype == "crossunder":
        return CrossoverCondition(
            fast=raw["fast"], slow=raw["slow"], is_crossunder=True,
        )
    elif ctype in ("above", "below"):
        return CompareCondition(
            left=raw["left"], right=raw["right"], op=ctype,
        )
    elif ctype in ("above_threshold", "below_threshold",
                    "crosses_above", "crosses_below"):
        return ThresholdCondition(
            indicator=raw["indicator"], value=raw["value"], op=ctype,
        )
    else:
        raise ValueError(f"Unknown condition type: {ctype}")


def parse_conditions(raw_list: List[dict]) -> List[Condition]:
    """Parse a list of JSON condition dicts into typed dataclasses."""
    return [parse_condition(r) for r in raw_list]


# ── DeclarativeStrategy ─────────────────────────────────────────────────


class DeclarativeStrategy(Strategy):
    """JSON config to Strategy. No code required.

    Parses conditions once at init into typed dataclasses. Evaluates
    them each bar using standalone functions. Builds orders from the
    exit/scale_in config sections.

    Args:
        config: Parsed JSON configuration dict.
    """

    def __init__(self, config: dict):
        self._config = config
        self._name = config.get("name", "DeclarativeStrategy")

        # Parse entry conditions
        entry = config.get("entry", {})
        long_raw = entry.get("long", {}).get("conditions", [])
        short_raw = entry.get("short", {}).get("conditions", [])
        self._long_conds = parse_conditions(long_raw)
        self._short_conds = parse_conditions(short_raw)

        # Exit config
        self._exit = config.get("exit", {})

        # Scale-in config
        self._scale_in = config.get("scale_in", {})

        # Previous indicator values for crossover detection
        self._prev_values: Dict[str, Any] = {}

    def indicator_config(self) -> dict:
        """Return indicator config for IndicatorManager."""
        return self._config.get("indicators", {})

    def on_bar(
        self,
        bar: Bar,
        indicators: Dict[str, Any],
        positions: List[Position],
    ) -> Optional[Order]:
        # Skip if already in a position
        if positions:
            self._prev_values = dict(indicators)
            return None

        order = None

        if evaluate_all(self._long_conds, bar, indicators, self._prev_values):
            order = self._build_order(Side.LONG)
        elif evaluate_all(self._short_conds, bar, indicators, self._prev_values):
            order = self._build_order(Side.SHORT)

        self._prev_values = dict(indicators)
        return order

    def _build_order(self, side: Side) -> MarketOrder:
        """Build a MarketOrder from exit config."""
        kwargs: Dict[str, Any] = {"side": side}

        # TP/SL
        if "take_profit_pct" in self._exit:
            kwargs["take_profit_pct"] = self._exit["take_profit_pct"]
        if "stop_loss_pct" in self._exit:
            kwargs["stop_loss_pct"] = self._exit["stop_loss_pct"]

        # Breakeven
        if "breakeven_trigger_pct" in self._exit:
            kwargs["breakeven_trigger_pct"] = self._exit["breakeven_trigger_pct"]
        if "breakeven_lock_pct" in self._exit:
            kwargs["breakeven_lock_pct"] = self._exit["breakeven_lock_pct"]

        return MarketOrder(**kwargs)

    def on_fill(self, fill: Fill):
        """Set up scale-in limit order on entry fill."""
        if not fill.is_entry or fill.reason == "MERGE":
            return None
        si = self._scale_in
        if not si.get("enabled", False):
            return None
        dip = si.get("dip_pct", 0.002)
        if fill.side == Side.LONG:
            limit_price = fill.price * (1 - dip)
        else:
            limit_price = fill.price * (1 + dip)
        return LimitOrder(
            side=fill.side,
            limit_price=limit_price,
            timeout_bars=si.get("timeout", 48),
            size_usd=fill.size_usd * si.get("size_pct", 0.5),
            use_maker_fee=True,
            merge_position=True,
            cancel_pending_limits=True,
        )

    def on_exit(self, fill: Fill, trade: Trade):
        """Cancel pending scale-in on take profit."""
        if self._scale_in.get("enabled", False) and "TAKE_PROFIT" in trade.reason:
            return CancelPendingLimitsOrder()
        return None

    @classmethod
    def from_json(cls, path: str) -> "DeclarativeStrategy":
        """Load from a JSON file."""
        with open(path) as f:
            return cls(json.load(f))

    @classmethod
    def from_dict(cls, config: dict) -> "DeclarativeStrategy":
        """Create from a dict (alias for constructor)."""
        return cls(config)
