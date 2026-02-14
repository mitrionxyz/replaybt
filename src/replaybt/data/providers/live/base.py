"""Async data provider base for live/paper trading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, List

from ...types import Bar


class AsyncDataProvider(ABC):
    """Base for async (live) data providers.

    Yields Bar objects as they complete in real time. Supports
    warmup (fetch historical bars before streaming) and graceful
    shutdown.

    Unlike the sync DataProvider (which iterates a fixed dataset),
    AsyncDataProvider runs indefinitely until stopped.
    """

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[Bar]:
        """Yield completed bars asynchronously."""
        ...

    @abstractmethod
    def symbol(self) -> str:
        """Return the symbol this provider serves."""
        ...

    @abstractmethod
    def timeframe(self) -> str:
        """Return the base timeframe (e.g. '1m')."""
        ...

    async def warmup(self, periods: int = 200) -> List[Bar]:
        """Fetch historical bars for indicator warmup.

        Override in subclass if historical data is available.
        Returns empty list by default.
        """
        return []

    async def close(self) -> None:
        """Clean up connections. Override if stateful."""
        pass
