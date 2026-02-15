"""Cached data provider — fetch once, serve from Parquet."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Union

import pandas as pd

from .providers.base import DataProvider
from .providers.csv import CSVProvider
from .types import Bar


_DEFAULT_CACHE_DIR = Path.home() / ".replaybt" / "cache"

# Common quote suffixes to strip for symbol inference
_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "BUSD", "TUSD", "UST", "PERP")


def _infer_symbol_name(exchange_symbol: str) -> str:
    """Infer short symbol from exchange pair.

    'ETHUSDT' -> 'ETH', 'BTC-USDT' -> 'BTC', 'SOL-PERP' -> 'SOL'
    """
    # Handle hyphenated pairs
    name = exchange_symbol.replace("-", "")
    for suffix in _QUOTE_SUFFIXES:
        if name.upper().endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)].upper()
    return name.upper()


def _parse_datetime(val: Union[str, datetime, None]) -> Optional[datetime]:
    """Convert string or datetime to datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return pd.Timestamp(val).to_pydatetime()


class CachedProvider(DataProvider):
    """DataProvider that fetches from an exchange and caches as Parquet.

    First access fetches data via the provided ExchangeFetcher and writes
    to a local Parquet file. Subsequent accesses load from cache. Supports
    incremental updates when the requested range extends beyond the cache.

    Args:
        fetcher: ExchangeFetcher instance (BinanceFetcher, BybitFetcher, etc).
        symbol: Exchange symbol (e.g. 'ETHUSDT').
        timeframe: Candle interval (default '1m').
        start: Start of range (str or datetime).
        end: End of range (str or datetime).
        cache_dir: Cache directory (default ~/.replaybt/cache/).
        symbol_name: Override inferred bar symbol (e.g. 'ETH').
        verbose: Print fetch progress.
    """

    def __init__(
        self,
        fetcher,
        symbol: str,
        timeframe: str = "1m",
        start: Union[str, datetime, None] = None,
        end: Union[str, datetime, None] = None,
        cache_dir: Union[str, Path, None] = None,
        symbol_name: Optional[str] = None,
        verbose: bool = True,
    ):
        self._fetcher = fetcher
        self._exchange_symbol = symbol
        self._timeframe = timeframe
        self._start = _parse_datetime(start)
        self._end = _parse_datetime(end)
        self._symbol_name = symbol_name or _infer_symbol_name(symbol)
        self._verbose = verbose

        env_dir = os.environ.get("REPLAYBT_CACHE_DIR")
        if cache_dir is not None:
            self._cache_dir = Path(cache_dir)
        elif env_dir:
            self._cache_dir = Path(env_dir)
        else:
            self._cache_dir = _DEFAULT_CACHE_DIR

        self._inner: Optional[CSVProvider] = None

    def _cache_path(self) -> Path:
        """Return path to cached Parquet file."""
        exchange = self._fetcher.exchange_name()
        filename = f"{self._exchange_symbol}_{self._timeframe}.parquet"
        return self._cache_dir / exchange / filename

    def _ensure_data(self) -> Path:
        """Ensure cached Parquet file covers the requested range."""
        path = self._cache_path()

        if path.exists():
            cached_df = pd.read_parquet(path)
            cached_df["timestamp"] = pd.to_datetime(cached_df["timestamp"], utc=True)

            if len(cached_df) > 0:
                cached_start = cached_df["timestamp"].min().to_pydatetime()
                cached_end = cached_df["timestamp"].max().to_pydatetime()

                need_before = self._start and self._start < cached_start
                need_after = self._end and self._end > cached_end

                if not need_before and not need_after:
                    return path

                # Incremental fetch for gaps
                parts = [cached_df]

                if need_before:
                    if self._verbose:
                        print(f"Fetching {self._exchange_symbol} data before cache ({self._start} to {cached_start})...")
                    before_df = self._fetcher.fetch(
                        self._exchange_symbol, self._timeframe,
                        self._start, cached_start,
                        verbose=self._verbose,
                    )
                    if len(before_df) > 0:
                        parts.insert(0, before_df)

                if need_after:
                    if self._verbose:
                        print(f"Fetching {self._exchange_symbol} data after cache ({cached_end} to {self._end})...")
                    after_df = self._fetcher.fetch(
                        self._exchange_symbol, self._timeframe,
                        cached_end, self._end,
                        verbose=self._verbose,
                    )
                    if len(after_df) > 0:
                        parts.append(after_df)

                if len(parts) > 1:
                    merged = pd.concat(parts, ignore_index=True)
                    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
                    merged = merged.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
                    self._atomic_write(path, merged)

                return path

        # Full fetch
        if self._verbose:
            print(f"Fetching {self._exchange_symbol} {self._timeframe} from {self._fetcher.exchange_name()}...")

        df = self._fetcher.fetch(
            self._exchange_symbol, self._timeframe,
            self._start, self._end,
            verbose=self._verbose,
        )

        if len(df) == 0:
            raise ValueError(f"No data returned for {self._exchange_symbol} {self._timeframe}")

        self._atomic_write(path, df)
        return path

    def _atomic_write(self, path: Path, df: pd.DataFrame) -> None:
        """Write Parquet atomically via temp file + rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, suffix=".parquet.tmp",
        )
        os.close(tmp_fd)
        try:
            df.to_parquet(tmp_path, index=False)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _get_inner(self) -> CSVProvider:
        """Lazily create the inner CSVProvider."""
        if self._inner is None:
            path = self._ensure_data()
            self._inner = CSVProvider(
                path=path,
                symbol_name=self._symbol_name,
                timeframe=self._timeframe,
                start=self._start.isoformat() if self._start else None,
                end=self._end.isoformat() if self._end else None,
            )
        return self._inner

    def __iter__(self) -> Iterator[Bar]:
        return iter(self._get_inner())

    def symbol(self) -> str:
        return self._symbol_name

    def timeframe(self) -> str:
        return self._timeframe

    def reset(self) -> None:
        if self._inner is not None:
            self._inner.reset()

    def to_dataframe(self) -> pd.DataFrame:
        """Return the underlying dataframe."""
        return self._get_inner().to_dataframe()

    def __len__(self) -> int:
        return len(self._get_inner())
