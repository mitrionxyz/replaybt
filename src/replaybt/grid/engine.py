"""GridBacktestEngine: Runs a grid market making strategy through DataProvider bars.

Port of Mitrion's BacktestKernel + MarketMakingSimulator, adapted to use
replaybt's DataProvider and return GridResults.
"""

from __future__ import annotations

from ..data.providers.base import DataProvider
from .inventory import InventoryTracker
from .manager import GridManager
from .shapes import ShapeConfig, compute_grid
from .types import (
    GridConfig,
    GridFill,
    GridResults,
    OrderSide,
    OrderStatus,
    _compute_sharpe,
)


class GridBacktestEngine:
    """Run a grid market making backtest through DataProvider bars."""

    def __init__(
        self,
        data: DataProvider,
        config: GridConfig,
    ) -> None:
        self.data = data
        self.config = config

    def run(self) -> GridResults:
        """Run grid MM backtest through all bars from data provider."""
        config = self.config
        bars = list(self.data)

        if len(bars) < 2:
            return GridResults(
                initial_capital=config.capital,
                final_equity=config.capital,
                symbol=self.data.symbol(),
            )

        initial_price = bars[0].close
        capital = config.capital

        # Initialize components
        grid_mgr = GridManager(
            spread_pct=config.spread_pct,
            slippage_pct=config.slippage_pct,
            maker_fee_pct=config.maker_fee_pct,
        )
        max_inv_base = (capital * config.max_inventory_pct) / initial_price
        inv = InventoryTracker(
            max_inventory_base=max_inv_base,
            skew_factor=config.skew_factor,
            max_skew=config.max_skew,
            initial_quote=capital,
        )

        result = GridResults(
            initial_capital=capital,
            symbol=self.data.symbol(),
        )

        # Build shape config from grid config
        shape_cfg = ShapeConfig(
            price_min=initial_price * (1 - config.range_pct),
            price_max=initial_price * (1 + config.range_pct),
            concentration=config.concentration,
            bias=config.bias,
            total_capital=capital,
            spread_pct=config.spread_pct,
            num_levels=config.num_levels,
            tick_size=config.tick_size,
            min_order_value=config.min_order_value,
        )

        # Place initial grid
        grid_levels = compute_grid(shape_cfg, initial_price)
        grid_mgr.place_grid(grid_levels, bar_index=0)
        result.recenters += 1

        grid_center = initial_price
        last_recenter_bar = 0
        is_paused = False

        # Vol guard state
        vol_guard_paused = False
        vol_guard_cooldown_remaining = 0
        true_ranges: list[float] = []

        # Inventory reduce mode
        inv_reduce_active = False

        # Main loop
        for i in range(1, len(bars)):
            bar = bars[i]
            prev_bar = bars[i - 1]
            mid_price = bar.close

            # --- Circuit breaker ---
            if inv.get_drawdown(mid_price) >= config.max_drawdown_pct:
                if not is_paused:
                    grid_mgr.cancel_all()
                    is_paused = True

            if is_paused:
                if inv.get_drawdown(mid_price) < config.max_drawdown_pct * 0.5:
                    is_paused = False
                    grid_center = mid_price
                    shape_cfg.price_min = mid_price * (1 - config.range_pct)
                    shape_cfg.price_max = mid_price * (1 + config.range_pct)
                    grid_levels = compute_grid(shape_cfg, mid_price)
                    grid_mgr.place_grid(grid_levels, bar_index=i)
                    last_recenter_bar = i
                else:
                    inv.update_peak_equity(mid_price)
                    dd = inv.get_drawdown(mid_price)
                    if dd > result.max_drawdown_pct:
                        result.max_drawdown_pct = dd
                    if i % config.snapshot_interval == 0:
                        result.equity_curve.append(
                            (bar.timestamp, inv.get_equity(mid_price))
                        )
                    continue

            # --- Volatility guard ---
            if config.vol_guard_enabled:
                tr = max(
                    bar.high - bar.low,
                    abs(bar.high - prev_bar.close),
                    abs(bar.low - prev_bar.close),
                )
                true_ranges.append(tr)
                if len(true_ranges) > config.vol_guard_atr_period:
                    true_ranges.pop(0)

                if len(true_ranges) == config.vol_guard_atr_period:
                    atr = sum(true_ranges) / len(true_ranges)
                    atr_pct = (atr / mid_price) * 100 if mid_price > 0 else 0

                    if atr_pct >= config.vol_guard_threshold_pct:
                        if not vol_guard_paused:
                            grid_mgr.cancel_all()
                            vol_guard_paused = True
                            result.vol_guard_triggers += 1
                        vol_guard_cooldown_remaining = config.vol_guard_cooldown
                    elif vol_guard_paused:
                        vol_guard_cooldown_remaining -= 1
                        if vol_guard_cooldown_remaining <= 0:
                            vol_guard_paused = False
                            grid_center = mid_price
                            shape_cfg.price_min = mid_price * (1 - config.range_pct)
                            shape_cfg.price_max = mid_price * (1 + config.range_pct)
                            grid_levels = compute_grid(shape_cfg, mid_price)
                            grid_mgr.place_grid(grid_levels, bar_index=i)
                            last_recenter_bar = i
                            result.recenters += 1

                if vol_guard_paused:
                    result.vol_guard_bars_paused += 1
                    inv.update_peak_equity(mid_price)
                    dd = inv.get_drawdown(mid_price)
                    if dd > result.max_drawdown_pct:
                        result.max_drawdown_pct = dd
                    if i % config.snapshot_interval == 0:
                        result.equity_curve.append(
                            (bar.timestamp, inv.get_equity(mid_price))
                        )
                    continue

            # --- Check fills ---
            new_fills = grid_mgr.check_fills(
                candle_low=bar.low,
                candle_high=bar.high,
                candle_open=bar.open,
                bar_index=i,
                timestamp=bar.timestamp,
            )

            # Filter and record fills
            recorded_fills: list[GridFill] = []
            for fill in new_fills:
                if fill.side == OrderSide.BID and not inv.can_buy():
                    continue
                if fill.side == OrderSide.ASK and not inv.can_sell():
                    continue

                inv.record_fill(fill.side, fill.size, fill.price, fill.spread_earned)
                recorded_fills.append(fill)
                result.fill_log.append(fill)
                result.total_fills += 1
                if fill.side == OrderSide.BID:
                    result.bid_fills += 1
                else:
                    result.ask_fills += 1

            # --- Place ping-pong orders ---
            for fill in recorded_fills:
                if fill.side == OrderSide.BID and inv.can_sell():
                    grid_mgr.place_pingpong(fill, mid_price, bar_index=i)
                elif fill.side == OrderSide.ASK and inv.can_buy():
                    grid_mgr.place_pingpong(fill, mid_price, bar_index=i)

            # --- Inventory limit enforcement ---
            if not inv.can_buy():
                for order in grid_mgr.get_open_orders(OrderSide.BID):
                    if not order.is_pingpong:
                        grid_mgr.orders[order.id].status = OrderStatus.CANCELLED
                        grid_mgr._open_ids.discard(order.id)

            if not inv.can_sell():
                for order in grid_mgr.get_open_orders(OrderSide.ASK):
                    if not order.is_pingpong:
                        grid_mgr.orders[order.id].status = OrderStatus.CANCELLED
                        grid_mgr._open_ids.discard(order.id)

            # --- Inventory reduce mode ---
            if config.inventory_reduce_pct > 0:
                inv_pct_abs = abs(inv.get_signed_inventory_pct())
                if inv_pct_abs > config.inventory_reduce_pct and not inv_reduce_active:
                    inv_reduce_active = True
                    result.inv_reduce_activations += 1
                    # Cancel accumulating side
                    if inv.state.base_position > 0:
                        grid_mgr.cancel_side(OrderSide.BID)
                    else:
                        grid_mgr.cancel_side(OrderSide.ASK)
                elif (
                    inv_pct_abs <= config.inventory_reduce_pct * 0.5
                    and inv_reduce_active
                ):
                    inv_reduce_active = False

            if inv_reduce_active:
                result.inv_reduce_bars += 1

            # --- Re-centering check ---
            price_deviation = (
                abs(mid_price - grid_center) / grid_center if grid_center > 0 else 0.0
            )
            bars_since_recenter = i - last_recenter_bar

            if (
                price_deviation >= config.recenter_threshold
                and bars_since_recenter >= config.recenter_min_bars
            ):
                grid_mgr.cancel_non_pingpong()

                # Apply recenter skew (either/or: quadratic replaces linear)
                inv_pct = inv.get_signed_inventory_pct()
                if config.recenter_skew_pct > 0 and inv_pct != 0:
                    skew = -inv_pct * abs(inv_pct) * config.recenter_skew_pct
                else:
                    skew = inv.get_skew()

                skewed_price = mid_price * (1 + skew)

                shape_cfg.price_min = skewed_price * (1 - config.range_pct)
                shape_cfg.price_max = skewed_price * (1 + config.range_pct)
                grid_levels = compute_grid(shape_cfg, skewed_price)

                # Filter by inventory limits (match agent compute_grid)
                filtered = []
                can_buy = inv.can_buy()
                can_sell = inv.can_sell()
                for lv in grid_levels:
                    if lv.side == "bid" and not can_buy:
                        continue
                    if lv.side == "ask" and not can_sell:
                        continue
                    filtered.append(lv)
                grid_levels = filtered

                # Filter by inv_reduce mode (remove accumulating side)
                if inv_reduce_active:
                    accum = "bid" if inv.state.base_position > 0 else "ask"
                    grid_levels = [lv for lv in grid_levels if lv.side != accum]

                grid_mgr.place_grid(grid_levels, bar_index=i)
                grid_center = mid_price
                last_recenter_bar = i
                result.recenters += 1

            # --- Track equity ---
            inv.update_peak_equity(mid_price)
            dd = inv.get_drawdown(mid_price)
            if dd > result.max_drawdown_pct:
                result.max_drawdown_pct = dd

            if i % config.snapshot_interval == 0:
                result.equity_curve.append((bar.timestamp, inv.get_equity(mid_price)))

        # --- Final ---
        final_price = bars[-1].close
        result.final_equity = inv.get_equity(final_price)
        result.total_pnl = result.final_equity - capital
        result.spread_pnl = inv.state.cumulative_spread_captured
        result.inventory_pnl = result.total_pnl - result.spread_pnl
        result.total_bars = len(bars)
        result.sharpe_ratio = _compute_sharpe(result.equity_curve)

        return result
