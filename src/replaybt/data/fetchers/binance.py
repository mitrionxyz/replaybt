"""Binance public API fetcher for historical OHLCV data."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from .base import ExchangeFetcher

# Binance kline intervals
_TIMEFRAME_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "1w": "1w",
}

_BASE_URL = "https://api.binance.com"
_KLINES_ENDPOINT = "/api/v3/klines"
_MAX_CANDLES = 1000


def _import_requests():
    """Lazy import with helpful error."""
    try:
        import requests
        return requests
    except ImportError:
        raise ImportError(
            "The 'requests' package is required for exchange fetchers. "
            "Install it with: pip install replaybt[data]"
        )


class BinanceFetcher(ExchangeFetcher):
    """Fetch historical klines from Binance public REST API.

    No API key required. Rate limited to stay within public limits.

    Args:
        base_url: API base URL (override for testnet).
        rate_limit: Seconds between requests (default 0.2 = 5 req/s).
    """

    def __init__(
        self,
        base_url: str = _BASE_URL,
        rate_limit: float = 0.2,
    ):
        self._base_url = base_url
        self._rate_limit = rate_limit

    def exchange_name(self) -> str:
        return "binance"

    def fetch(
        self,
        symbol: str,
        timeframe: str = "1m",
        start: datetime = None,
        end: datetime = None,
        verbose: bool = False,
    ) -> pd.DataFrame:
        requests = _import_requests()

        interval = _TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {list(_TIMEFRAME_MAP.keys())}"
            )

        start_ms = int(start.timestamp() * 1000) if start else None
        end_ms = int(end.timestamp() * 1000) if end else None

        all_rows = []
        page = 0

        while True:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": _MAX_CANDLES,
            }
            if start_ms is not None:
                params["startTime"] = start_ms
            if end_ms is not None:
                params["endTime"] = end_ms

            url = f"{self._base_url}{_KLINES_ENDPOINT}"
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            all_rows.extend(data)
            page += 1

            if verbose:
                ts = datetime.fromtimestamp(data[-1][0] / 1000, tz=timezone.utc)
                print(f"  Binance {symbol} page {page}: {len(data)} candles, up to {ts}")

            if len(data) < _MAX_CANDLES:
                break

            # Advance past last candle's close time
            last_close_time = data[-1][6]  # closeTime field
            start_ms = last_close_time + 1

            if end_ms is not None and start_ms > end_ms:
                break

            time.sleep(self._rate_limit)

        if not all_rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(all_rows, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ])

        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)

        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

        return df
