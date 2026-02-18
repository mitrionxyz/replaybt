"""Grid Manager: Maintains the virtual grid of orders, handles ping-pong fills,
and computes diffs when re-centering.

Port of Mitrion's grid_manager.py with replaybt types.
"""

from __future__ import annotations

from datetime import datetime

from .types import GridFill, GridOrder, OrderSide, OrderStatus


class GridLevel:
    """A single level from the shape engine (price + size + side)."""

    __slots__ = ("price", "size", "side")

    def __init__(self, price: float, size: float, side: str) -> None:
        self.price = price
        self.size = size
        self.side = side


class GridManager:
    """Manages the virtual grid of bid/ask orders with ping-pong logic.

    Critical optimization: ``_open_ids`` set for O(1) open-order checks.
    """

    def __init__(
        self,
        spread_pct: float,
        slippage_pct: float = 0.0002,
        maker_fee_pct: float = 0.0,
    ) -> None:
        self.spread_pct = spread_pct
        self.slippage_pct = slippage_pct
        self.maker_fee_pct = maker_fee_pct
        self.orders: dict[int, GridOrder] = {}
        self._open_ids: set[int] = set()
        self.fills: list[GridFill] = []
        self._next_id = 0

    def place_grid(self, grid_levels: list[GridLevel], bar_index: int = 0) -> None:
        """Place a full grid of orders (initial placement or after re-center)."""
        for level in grid_levels:
            side = OrderSide.BID if level.side == "bid" else OrderSide.ASK
            self._place_order(
                level.price, level.size, side, bar_index, is_pingpong=False
            )

    def cancel_all(self) -> None:
        """Cancel all open orders."""
        for oid in list(self._open_ids):
            self.orders[oid].status = OrderStatus.CANCELLED
        self._open_ids.clear()

    def cancel_side(self, side: OrderSide) -> None:
        """Cancel all open orders on one side."""
        to_cancel = [oid for oid in self._open_ids if self.orders[oid].side == side]
        for oid in to_cancel:
            self.orders[oid].status = OrderStatus.CANCELLED
            self._open_ids.discard(oid)

    def cancel_non_pingpong(self) -> None:
        """Cancel grid orders but keep ping-pongs (used for re-center)."""
        to_cancel = [oid for oid in self._open_ids if not self.orders[oid].is_pingpong]
        for oid in to_cancel:
            self.orders[oid].status = OrderStatus.CANCELLED
            self._open_ids.discard(oid)

    def get_open_orders(self, side: OrderSide | None = None) -> list[GridOrder]:
        """Get all open orders, optionally filtered by side."""
        orders = [self.orders[oid] for oid in self._open_ids]
        if side is not None:
            orders = [o for o in orders if o.side == side]
        return orders

    def check_fills(
        self,
        candle_low: float,
        candle_high: float,
        candle_open: float,
        bar_index: int,
        timestamp: datetime | None = None,
    ) -> list[GridFill]:
        """Check which open orders would have been filled by this candle.

        Fill logic:
        - Bid fills if candle_low <= bid_price
        - Ask fills if candle_high >= ask_price

        Gap protection: if open gaps past an order, fill at open (worse price).
        """
        ts = timestamp or datetime(2000, 1, 1)
        new_fills: list[GridFill] = []
        filled_ids: list[int] = []

        for oid in list(self._open_ids):
            order = self.orders[oid]
            filled = False
            fill_price = order.price

            if order.side == OrderSide.BID:
                if candle_low <= order.price:
                    filled = True
                    if candle_open < order.price:
                        fill_price = candle_open
                    fill_price -= fill_price * self.slippage_pct
            elif order.side == OrderSide.ASK:
                if candle_high >= order.price:
                    filled = True
                    if candle_open > order.price:
                        fill_price = candle_open
                    fill_price -= fill_price * self.slippage_pct

            if filled:
                order.status = OrderStatus.FILLED
                filled_ids.append(oid)
                half_spread = order.price * self.spread_pct
                fee = fill_price * order.size * self.maker_fee_pct

                grid_fill = GridFill(
                    order_id=order.id,
                    price=fill_price,
                    size=order.size,
                    side=order.side,
                    bar_index=bar_index,
                    timestamp=ts,
                    spread_earned=half_spread * order.size - fee,
                )
                self.fills.append(grid_fill)
                new_fills.append(grid_fill)

        for oid in filled_ids:
            self._open_ids.discard(oid)

        return new_fills

    def place_pingpong(
        self, fill: GridFill, mid_price: float, bar_index: int
    ) -> GridOrder | None:
        """After a fill, place the opposite order at fill_price +/- spread.

        Bid fill -> place ask at fill_price + full_spread
        Ask fill -> place bid at fill_price - full_spread
        """
        full_spread = mid_price * self.spread_pct * 2

        if fill.side == OrderSide.BID:
            ask_price = fill.price + full_spread
            return self._place_order(
                ask_price, fill.size, OrderSide.ASK, bar_index, is_pingpong=True
            )
        else:
            bid_price = fill.price - full_spread
            return self._place_order(
                bid_price, fill.size, OrderSide.BID, bar_index, is_pingpong=True
            )

    def get_open_order_prices(self, side: OrderSide) -> list[float]:
        """Get sorted list of open order prices for a side."""
        prices = [
            self.orders[oid].price
            for oid in self._open_ids
            if self.orders[oid].side == side
        ]
        return sorted(prices, reverse=(side == OrderSide.BID))

    def count_open(self) -> dict[str, int]:
        """Count open orders by side."""
        bids = sum(
            1 for oid in self._open_ids if self.orders[oid].side == OrderSide.BID
        )
        asks = sum(
            1 for oid in self._open_ids if self.orders[oid].side == OrderSide.ASK
        )
        return {"bid": bids, "ask": asks}

    def _place_order(
        self,
        price: float,
        size: float,
        side: OrderSide,
        bar_index: int,
        is_pingpong: bool,
    ) -> GridOrder:
        order = GridOrder(
            id=self._next_id,
            price=price,
            size=size,
            side=side,
            status=OrderStatus.OPEN,
            is_pingpong=is_pingpong,
            placed_at_bar=bar_index,
        )
        self.orders[order.id] = order
        self._open_ids.add(order.id)
        self._next_id += 1
        return order
