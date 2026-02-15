"""Base exchange fetcher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd


class ExchangeFetcher(ABC):
    """Abstract base for exchange data fetchers.

    Fetchers download historical OHLCV data from exchange REST APIs.
    They handle pagination, rate limiting, and response normalization.

    Returned DataFrames have columns:
        timestamp (datetime64[ns, UTC]), open, high, low, close, volume
    sorted chronologically with no duplicates.
    """

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        verbose: bool = False,
    ) -> pd.DataFrame:
        """Fetch OHLCV data for the given symbol and time range.

        Args:
            symbol: Exchange trading pair (e.g. 'ETHUSDT').
            timeframe: Candle interval (e.g. '1m', '5m', '1h', '1d').
            start: Start of range (inclusive, UTC).
            end: End of range (inclusive, UTC).
            verbose: Print progress per page.

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume.
        """
        ...

    @abstractmethod
    def exchange_name(self) -> str:
        """Identifier for cache directory (e.g. 'binance')."""
        ...
