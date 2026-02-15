"""Tests for CachedProvider (no network, mock fetcher + tmp_path)."""

import os
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from replaybt.data.cache import CachedProvider, _infer_symbol_name
from replaybt.data.types import Bar


def _make_fetcher(df: pd.DataFrame, name: str = "testex") -> MagicMock:
    """Create a mock ExchangeFetcher that returns the given DataFrame."""
    fetcher = MagicMock()
    fetcher.exchange_name.return_value = name
    fetcher.fetch.return_value = df
    return fetcher


def _sample_df(n: int = 20, start_ts: int = 1704067200) -> pd.DataFrame:
    """Create a sample OHLCV DataFrame with n rows."""
    timestamps = pd.date_range(
        start=pd.Timestamp(start_ts, unit="s", tz="UTC"),
        periods=n,
        freq="1min",
    )
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [100.0 + i * 0.1 for i in range(n)],
        "high": [101.0 + i * 0.1 for i in range(n)],
        "low": [99.0 + i * 0.1 for i in range(n)],
        "close": [100.5 + i * 0.1 for i in range(n)],
        "volume": [1000.0] * n,
    })


class TestCachedProvider:
    def test_full_fetch_creates_cache(self, tmp_path):
        """First access fetches data and writes Parquet cache."""
        df = _sample_df(10)
        fetcher = _make_fetcher(df)

        provider = CachedProvider(
            fetcher, "ETHUSDT", "1m",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 0, 10, tzinfo=timezone.utc),
            cache_dir=tmp_path,
            verbose=False,
        )

        bars = list(provider)
        assert len(bars) == 10
        assert isinstance(bars[0], Bar)
        fetcher.fetch.assert_called_once()

        # Parquet should exist
        cache_file = tmp_path / "testex" / "ETHUSDT_1m.parquet"
        assert cache_file.exists()

    def test_cache_hit_no_fetch(self, tmp_path):
        """Second access with same range loads from cache, no fetch call."""
        df = _sample_df(10)
        fetcher = _make_fetcher(df)

        # End must match last bar's timestamp (00:09) for exact cache hit
        kwargs = dict(
            symbol="ETHUSDT", timeframe="1m",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 0, 9, tzinfo=timezone.utc),
            cache_dir=tmp_path, verbose=False,
        )

        # First access
        p1 = CachedProvider(fetcher, **kwargs)
        list(p1)
        assert fetcher.fetch.call_count == 1

        # Second access — should not fetch again
        p2 = CachedProvider(fetcher, **kwargs)
        list(p2)
        assert fetcher.fetch.call_count == 1

    def test_incremental_update(self, tmp_path):
        """When cache is partial, only the gap is fetched."""
        # Initial data: first 10 bars
        df1 = _sample_df(10)
        fetcher = _make_fetcher(df1)

        p1 = CachedProvider(
            fetcher, "ETHUSDT", "1m",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 0, 10, tzinfo=timezone.utc),
            cache_dir=tmp_path, verbose=False,
        )
        list(p1)

        # Now request wider range — fetcher returns extension
        df2 = _sample_df(5, start_ts=1704067200 + 10 * 60)
        fetcher.fetch.return_value = df2

        p2 = CachedProvider(
            fetcher, "ETHUSDT", "1m",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc),
            cache_dir=tmp_path, verbose=False,
        )
        bars = list(p2)

        # Should have fetched only the gap
        assert fetcher.fetch.call_count == 2
        assert len(bars) == 15

    def test_to_dataframe_and_len(self, tmp_path):
        """to_dataframe() and __len__() work correctly."""
        df = _sample_df(15)
        fetcher = _make_fetcher(df)

        provider = CachedProvider(
            fetcher, "ETHUSDT", "1m",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc),
            cache_dir=tmp_path, verbose=False,
        )

        assert len(provider) == 15
        result_df = provider.to_dataframe()
        assert len(result_df) == 15
        assert "close" in result_df.columns

    def test_symbol_name_inference(self, tmp_path):
        """Symbol name is inferred from exchange symbol."""
        df = _sample_df(5)
        fetcher = _make_fetcher(df)

        provider = CachedProvider(
            fetcher, "SOLUSDT", "1m",
            cache_dir=tmp_path, verbose=False,
        )
        assert provider.symbol() == "SOL"

    def test_env_var_cache_dir(self, tmp_path, monkeypatch):
        """REPLAYBT_CACHE_DIR env var overrides default."""
        monkeypatch.setenv("REPLAYBT_CACHE_DIR", str(tmp_path / "env_cache"))
        df = _sample_df(5)
        fetcher = _make_fetcher(df)

        provider = CachedProvider(
            fetcher, "ETHUSDT", "1m", verbose=False,
        )

        list(provider)
        cache_file = tmp_path / "env_cache" / "testex" / "ETHUSDT_1m.parquet"
        assert cache_file.exists()


class TestSymbolInference:
    def test_usdt_suffix(self):
        assert _infer_symbol_name("ETHUSDT") == "ETH"

    def test_usdc_suffix(self):
        assert _infer_symbol_name("BTCUSDC") == "BTC"

    def test_hyphenated(self):
        assert _infer_symbol_name("SOL-USDT") == "SOL"

    def test_perp_suffix(self):
        assert _infer_symbol_name("SOL-PERP") == "SOL"

    def test_no_suffix(self):
        assert _infer_symbol_name("ETH") == "ETH"
