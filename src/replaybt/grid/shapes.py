"""Shape Engine: Translates user controls (Range, Concentration, Bias) into a grid
of (price, size) pairs for bid and ask sides.

Concentration mapping:
  0.0 -> Flat (uniform distribution)
  0.5 -> Gaussian (bell curve)
  1.0 -> Exponential (Laplace, sharp peak)
  Values between anchors are interpolated.

Port of Mitrion's shape_engine.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .manager import GridLevel


@dataclass
class ShapeConfig:
    """Configuration for grid shape computation."""

    price_min: float
    price_max: float
    concentration: float  # 0.0 to 1.0
    bias: float  # -1.0 to 1.0
    total_capital: float  # in quote currency
    spread_pct: float = 0.001  # 0.1% half-spread
    num_levels: int = 20  # per side
    tick_size: float = 0.01  # price rounding
    min_order_value: float = 10.0  # minimum notional per order


def _flat_weights(prices: list[float], mu: float) -> list[float]:
    """Uniform distribution: equal weight everywhere."""
    return [1.0] * len(prices)


def _gaussian_weights(prices: list[float], mu: float, sigma: float) -> list[float]:
    """Gaussian (bell curve) distribution centered on mu."""
    if sigma <= 0:
        return [
            1.0 if abs(p - mu) == min(abs(p - mu) for p in prices) else 0.0
            for p in prices
        ]
    return [math.exp(-0.5 * ((p - mu) / sigma) ** 2) for p in prices]


def _exponential_weights(prices: list[float], mu: float, lam: float) -> list[float]:
    """Laplace (exponential decay) distribution centered on mu."""
    if lam <= 0:
        return [1.0] * len(prices)
    return [math.exp(-lam * abs(p - mu)) for p in prices]


def _normalize_weights(weights: list[float]) -> list[float]:
    """Normalize weights to sum to 1.0."""
    total = sum(weights)
    if total <= 0:
        n = len(weights)
        return [1.0 / n] * n if n > 0 else []
    return [w / total for w in weights]


def _compute_weights(
    prices: list[float], concentration: float, mu: float, price_range: float
) -> list[float]:
    """Compute distribution weights for a list of prices.

    Concentration 0.0 -> flat, 0.5 -> gaussian, 1.0 -> exponential.
    Intermediate values interpolate between adjacent anchors.
    """
    sigma = price_range / 4.0
    lam = 6.0 / price_range if price_range > 0 else 1.0

    if concentration <= 0.0:
        return _normalize_weights(_flat_weights(prices, mu))
    elif concentration <= 0.5:
        t = concentration / 0.5
        w_flat = _flat_weights(prices, mu)
        w_gauss = _gaussian_weights(prices, mu, sigma)
        blended = [(1 - t) * f + t * g for f, g in zip(w_flat, w_gauss)]
        return _normalize_weights(blended)
    elif concentration < 1.0:
        t = (concentration - 0.5) / 0.5
        w_gauss = _gaussian_weights(prices, mu, sigma)
        w_exp = _exponential_weights(prices, mu, lam)
        blended = [(1 - t) * g + t * e for g, e in zip(w_gauss, w_exp)]
        return _normalize_weights(blended)
    else:
        return _normalize_weights(_exponential_weights(prices, mu, lam))


def _round_price(price: float, tick_size: float) -> float:
    """Round price to nearest tick."""
    if tick_size <= 0:
        return price
    return round(round(price / tick_size) * tick_size, 10)


def compute_grid(config: ShapeConfig, mid_price: float) -> list[GridLevel]:
    """Generate a full grid of bid and ask orders.

    Returns a list of GridLevel objects with price, size (in base), and side.
    """
    price_range = config.price_max - config.price_min
    mid_range = (config.price_min + config.price_max) / 2.0

    # Bias shifts the distribution center
    bias_alpha = 0.3
    mu = mid_range + config.bias * (price_range / 2.0) * bias_alpha

    # Inner edge of the grid: mid_price +/- spread
    bid_inner = mid_price * (1 - config.spread_pct)
    ask_inner = mid_price * (1 + config.spread_pct)

    # Generate bid prices: from bid_inner down to price_min
    bid_prices: list[float] = []
    p = _round_price(bid_inner, config.tick_size)
    while p >= config.price_min and len(bid_prices) < config.num_levels:
        if p < mid_price:
            bid_prices.append(p)
        step = (bid_inner - config.price_min) / max(config.num_levels, 1)
        p = _round_price(p - max(step, config.tick_size), config.tick_size)

    # Generate ask prices: from ask_inner up to price_max
    ask_prices: list[float] = []
    p = _round_price(ask_inner, config.tick_size)
    while p <= config.price_max and len(ask_prices) < config.num_levels:
        if p > mid_price:
            ask_prices.append(p)
        step = (config.price_max - ask_inner) / max(config.num_levels, 1)
        p = _round_price(p + max(step, config.tick_size), config.tick_size)

    if not bid_prices and not ask_prices:
        return []

    # Allocate capital: 50/50 between bid and ask sides
    bid_capital = config.total_capital / 2.0
    ask_capital = config.total_capital / 2.0

    grid: list[GridLevel] = []

    # Bid side
    if bid_prices:
        bid_weights = _compute_weights(
            bid_prices, config.concentration, mu, price_range
        )
        for price, weight in zip(bid_prices, bid_weights):
            quote_for_level = bid_capital * weight
            base_size = quote_for_level / price if price > 0 else 0
            if quote_for_level >= config.min_order_value:
                grid.append(GridLevel(price=price, size=base_size, side="bid"))

    # Ask side
    if ask_prices:
        ask_weights = _compute_weights(
            ask_prices, config.concentration, mu, price_range
        )
        for price, weight in zip(ask_prices, ask_weights):
            quote_for_level = ask_capital * weight
            base_size = quote_for_level / price if price > 0 else 0
            if quote_for_level >= config.min_order_value:
                grid.append(GridLevel(price=price, size=base_size, side="ask"))

    return grid
