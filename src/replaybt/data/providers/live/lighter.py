"""Lighter WebSocket order book provider."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from ...types import Bar
from .base import AsyncDataProvider

logger = logging.getLogger(__name__)

LIGHTER_WS_URL = "wss://mainnet.zklighter.elliot.ai/stream"

LIGHTER_MARKETS = {
    "ETH": {"market_id": 0, "price_decimals": 2},
    "SOL": {"market_id": 2, "price_decimals": 3},
    "SUI": {"market_id": 16, "price_decimals": 5},
    "AXS": {"market_id": 131, "price_decimals": 4},
    "HYPE": {"market_id": 24, "price_decimals": 4},
    "LIT": {"market_id": 120, "price_decimals": 4},
}


class _BarBuilder:
    """Accumulates mid-price ticks into OHLCV bars.

    Each tick updates the current bar. When a tick falls into a new
    time period, the completed bar is returned and a new one starts.
    """

    def __init__(self, timeframe: str, symbol: str = ""):
        self._minutes = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15,
            "30m": 30, "1h": 60, "4h": 240,
        }[timeframe]
        self._timeframe = timeframe
        self._symbol = symbol
        self._open: Optional[float] = None
        self._high: Optional[float] = None
        self._low: Optional[float] = None
        self._close: Optional[float] = None
        self._bar_start: Optional[datetime] = None

    def _boundary(self, ts: datetime) -> int:
        """Return the bar boundary index for a timestamp."""
        epoch_minutes = int(ts.timestamp()) // 60
        return epoch_minutes // self._minutes

    def tick(self, price: float, ts: datetime) -> Optional[Bar]:
        """Process a price tick. Returns completed Bar or None."""
        boundary = self._boundary(ts)
        completed = None

        # If we have an existing bar and the tick is in a new period,
        # emit the completed bar
        if (
            self._bar_start is not None
            and boundary != self._boundary(self._bar_start)
        ):
            completed = Bar(
                timestamp=self._bar_start,
                open=self._open,
                high=self._high,
                low=self._low,
                close=self._close,
                volume=0.0,
                symbol=self._symbol,
                timeframe=self._timeframe,
            )
            self._open = None
            self._high = None
            self._low = None

        # Start or update current bar
        if self._open is None:
            self._open = price
            self._high = price
            self._low = price
            self._bar_start = ts
        else:
            self._high = max(self._high, price)
            self._low = min(self._low, price)

        self._close = price
        return completed

    def reset(self) -> None:
        """Clear accumulated state."""
        self._open = None
        self._high = None
        self._low = None
        self._close = None
        self._bar_start = None


class LighterProvider(AsyncDataProvider):
    """WebSocket order book provider for Lighter exchange.

    Connects to the Lighter WebSocket stream, subscribes to
    order book updates for a market, and builds OHLCV bars from
    the mid price (average of best bid and best ask).

    Args:
        symbol: Market name (e.g. "ETH", "SOL").
        timeframe: Bar interval (default "1m").
        ws_url: Override WebSocket endpoint (for testing).
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str = "1m",
        ws_url: str = LIGHTER_WS_URL,
    ):
        if symbol not in LIGHTER_MARKETS:
            raise ValueError(
                f"Unknown Lighter market: {symbol}. "
                f"Available: {list(LIGHTER_MARKETS.keys())}"
            )
        self._symbol = symbol
        self._timeframe = timeframe
        self._ws_url = ws_url
        self._market = LIGHTER_MARKETS[symbol]
        self._bar_builder = _BarBuilder(timeframe, symbol)
        self._reconnect_delay = 5

    def symbol(self) -> str:
        return self._symbol

    def timeframe(self) -> str:
        return self._timeframe

    async def __aiter__(self) -> AsyncIterator[Bar]:
        while True:
            try:
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    await self._subscribe(ws)
                    self._reconnect_delay = 5  # Reset on success
                    async for message in ws:
                        data = json.loads(message)
                        mid = self._extract_mid_price(data)
                        if mid is not None:
                            bar = self._bar_builder.tick(
                                mid, datetime.now(tz=timezone.utc)
                            )
                            if bar is not None:
                                yield bar
            except (ConnectionClosed, ConnectionError, OSError) as e:
                logger.warning(
                    "Lighter WS disconnected (%s), reconnecting in %ds",
                    e, self._reconnect_delay,
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    async def _subscribe(self, ws) -> None:
        """Subscribe to order book updates for our market."""
        market_id = self._market["market_id"]
        sub_msg = json.dumps({
            "type": "subscribe",
            "channel": f"order_book.{market_id}",
        })
        await ws.send(sub_msg)
        logger.info(
            "Subscribed to Lighter order book: %s (market %d)",
            self._symbol, market_id,
        )

    def _extract_mid_price(self, data: dict) -> Optional[float]:
        """Extract mid price from order book update."""
        book = data.get("order_book", {})
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if bids and asks:
            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            return (best_bid + best_ask) / 2
        return None

    async def close(self) -> None:
        """Reset bar builder state."""
        self._bar_builder.reset()
