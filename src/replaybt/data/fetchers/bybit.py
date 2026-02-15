"""Bybit public API fetcher for historical OHLCV data."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from .base import ExchangeFetcher

# Bybit kline intervals
_TIMEFRAME_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
}

_BASE_URL = "https://api.bybit.com"
_KLINES_ENDPOINT = "/v5/market/kline"
_MAX_CANDLES = 200


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


class BybitFetcher(ExchangeFetcher):
    """Fetch historical klines from Bybit public REST API.

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
        return "bybit"

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
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": _MAX_CANDLES,
            }
            if start_ms is not None:
                params["start"] = start_ms
            if end_ms is not None:
                params["end"] = end_ms

            url = f"{self._base_url}{_KLINES_ENDPOINT}"
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()

            body = resp.json()
            if body.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {body.get('retMsg', 'unknown')}")

            data = body.get("result", {}).get("list", [])
            if not data:
                break

            all_rows.extend(data)
            page += 1

            if verbose:
                # Bybit returns descending, so last element is oldest
                oldest_ts = datetime.fromtimestamp(int(data[-1][0]) / 1000, tz=timezone.utc)
                print(f"  Bybit {symbol} page {page}: {len(data)} candles, oldest {oldest_ts}")

            if len(data) < _MAX_CANDLES:
                break

            # Bybit returns descending — oldest is last element
            # Set end to oldest timestamp - 1 to paginate backwards
            oldest_ms = int(data[-1][0])
            end_ms = oldest_ms - 1

            if start_ms is not None and end_ms < start_ms:
                break

            time.sleep(self._rate_limit)

        if not all_rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Bybit format: [timestamp_ms, open, high, low, close, volume, turnover]
        df = pd.DataFrame(all_rows, columns=[
            "open_time", "open", "high", "low", "close", "volume", "turnover",
        ])

        df["timestamp"] = pd.to_datetime(df["open_time"].astype(int), unit="ms", utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)

        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

        return df
