"""Hyperliquid REST candle polling provider."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional

import aiohttp

from ...types import Bar
from .base import AsyncDataProvider

logger = logging.getLogger(__name__)

HL_INFO_URL = "https://api.hyperliquid.xyz/info"

# Hyperliquid interval strings
_INTERVAL_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class HyperliquidProvider(AsyncDataProvider):
    """REST polling provider for Hyperliquid candle snapshots.

    Polls the Hyperliquid info API at a configurable interval,
    yielding new completed candles as Bar objects. The last candle
    in each response is excluded (incomplete/forming).

    Args:
        symbol: Coin name (e.g. "ETH", "SOL").
        timeframe: Candle interval (default "1m").
        poll_interval: Seconds between polls (default 60.0).
        url: Override API endpoint (for testing).
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str = "1m",
        poll_interval: float = 60.0,
        url: str = HL_INFO_URL,
    ):
        self._symbol = symbol
        self._timeframe = timeframe
        self._poll_interval = poll_interval
        self._url = url
        self._session: Optional[aiohttp.ClientSession] = None
        self._hl_interval = _INTERVAL_MAP.get(timeframe, timeframe)

    def symbol(self) -> str:
        return self._symbol

    def timeframe(self) -> str:
        return self._timeframe

    async def warmup(self, periods: int = 200) -> List[Bar]:
        """Fetch historical candles for indicator warmup."""
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        try:
            raw = await self._fetch_candles(session, limit=periods + 1)
            # Exclude last candle (incomplete)
            completed = raw[:-1] if raw else []
            return [self._parse_candle(c) for c in completed]
        finally:
            await session.close()

    async def __aiter__(self) -> AsyncIterator[Bar]:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        self._session = session
        try:
            last_ts: Optional[float] = None
            while True:
                try:
                    candles = await self._fetch_candles(session)
                    # Exclude last candle (incomplete)
                    completed = candles[:-1] if candles else []
                    for c in completed:
                        bar = self._parse_candle(c)
                        ts = bar.timestamp.timestamp()
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                            yield bar
                except aiohttp.ClientError as e:
                    logger.warning("Hyperliquid fetch error: %s", e)
                except Exception as e:
                    logger.warning("Hyperliquid unexpected error: %s", e)
                await asyncio.sleep(self._poll_interval)
        finally:
            await session.close()
            self._session = None

    async def _fetch_candles(
        self,
        session: aiohttp.ClientSession,
        limit: int = 100,
    ) -> list:
        """POST to Hyperliquid info API for candleSnapshot."""
        # Calculate start time: go back enough to get `limit` candles
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        tf_minutes = _tf_to_minutes(self._timeframe)
        start_ms = now_ms - (limit * tf_minutes * 60 * 1000)

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": self._symbol,
                "interval": self._hl_interval,
                "startTime": start_ms,
                "endTime": now_ms,
            },
        }
        async with session.post(self._url, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    def _parse_candle(self, raw: dict) -> Bar:
        """Convert Hyperliquid candle dict to Bar."""
        return Bar(
            timestamp=datetime.fromtimestamp(
                raw["t"] / 1000, tz=timezone.utc
            ),
            open=float(raw["o"]),
            high=float(raw["h"]),
            low=float(raw["l"]),
            close=float(raw["c"]),
            volume=float(raw["v"]),
            symbol=self._symbol,
            timeframe=self._timeframe,
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


def _tf_to_minutes(tf: str) -> int:
    """Convert timeframe string to minutes."""
    mapping = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15,
        "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
    }
    return mapping.get(tf, 1)
