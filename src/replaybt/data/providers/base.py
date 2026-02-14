"""Base data provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional

from ..types import Bar


class DataProvider(ABC):
    """Abstract base for all data providers.

    A DataProvider yields Bar objects one at a time, simulating
    the experience of receiving market data in real time.
    """

    @abstractmethod
    def __iter__(self) -> Iterator[Bar]:
        """Yield bars in chronological order."""
        ...

    @abstractmethod
    def symbol(self) -> str:
        """Return the symbol this provider serves."""
        ...

    @abstractmethod
    def timeframe(self) -> str:
        """Return the base timeframe (e.g. '1m')."""
        ...

    def reset(self) -> None:
        """Reset provider to beginning. Override if stateful."""
        pass
