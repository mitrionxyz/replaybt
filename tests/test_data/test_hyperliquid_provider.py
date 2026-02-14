"""Tests for HyperliquidProvider (all mocked, no network)."""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from replaybt.data.providers.live.hyperliquid import (
    HyperliquidProvider,
    _tf_to_minutes,
)
from replaybt.data.types import Bar


def _make_candle(t_ms: int, o=100, h=105, l=95, c=102, v=1000):
    """Create a raw Hyperliquid candle dict."""
    return {
        "t": t_ms,
        "o": str(o),
        "h": str(h),
        "l": str(l),
        "c": str(c),
        "v": str(v),
    }


class TestSymbolTimeframe:
    def test_symbol(self):
        p = HyperliquidProvider("ETH", "1m")
        assert p.symbol() == "ETH"

    def test_timeframe(self):
        p = HyperliquidProvider("SOL", "5m")
        assert p.timeframe() == "5m"


class TestParseCandle:
    def test_parses_ohlcv(self):
        p = HyperliquidProvider("ETH")
        raw = _make_candle(1700000000000, o=100, h=110, l=90, c=105, v=500)
        bar = p._parse_candle(raw)

        assert isinstance(bar, Bar)
        assert bar.open == 100.0
        assert bar.high == 110.0
        assert bar.low == 90.0
        assert bar.close == 105.0
        assert bar.volume == 500.0
        assert bar.symbol == "ETH"
        assert bar.timeframe == "1m"

    def test_timestamp_utc(self):
        p = HyperliquidProvider("ETH")
        raw = _make_candle(1700000000000)
        bar = p._parse_candle(raw)
        assert bar.timestamp.tzinfo == timezone.utc
        assert bar.timestamp == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


class TestWarmup:
    @pytest.mark.asyncio
    async def test_warmup_returns_bars(self):
        """warmup() fetches N historical bars, excludes incomplete."""
        candles = [
            _make_candle(1700000000000 + i * 60000)
            for i in range(5)
        ]

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=candles)
        mock_resp.raise_for_status = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            p = HyperliquidProvider("ETH", "1m")
            bars = await p.warmup(periods=4)

        # 5 candles fetched, last excluded → 4 bars
        assert len(bars) == 4
        assert all(isinstance(b, Bar) for b in bars)

    @pytest.mark.asyncio
    async def test_warmup_empty_response(self):
        """warmup() returns empty list if API returns empty."""
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=[])
        mock_resp.raise_for_status = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            p = HyperliquidProvider("ETH", "1m")
            bars = await p.warmup(periods=100)

        assert bars == []


class _StopIteration(Exception):
    """Sentinel to break out of async generator in tests."""
    pass


class TestIteration:
    @pytest.mark.asyncio
    async def test_iter_yields_new_bars_only(self):
        """Deduplication: only yields bars with timestamps > last seen."""
        # Two polls: first returns candles 0-2, second returns 1-3
        candles_poll1 = [_make_candle(1700000000000 + i * 60000) for i in range(3)]
        candles_poll2 = [_make_candle(1700000000000 + i * 60000) for i in range(1, 4)]

        call_count = 0

        async def mock_json():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return candles_poll1
            return candles_poll2

        mock_resp = AsyncMock()
        mock_resp.json = mock_json
        mock_resp.raise_for_status = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.close = AsyncMock()
        mock_session.closed = False

        collected = []
        poll_count = 0

        async def fake_sleep(secs):
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 2:
                raise _StopIteration

        with (
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            p = HyperliquidProvider("ETH", "1m", poll_interval=1.0)
            try:
                async for bar in p:
                    collected.append(bar)
            except _StopIteration:
                pass

        # Poll 1: candles[0:2] (3 candles, last excluded → 2 bars)
        # Poll 2: candles[1:3] (3 candles, last excluded → 2, but candle[1] already seen → only candle[2])
        assert len(collected) == 3
        # Timestamps should be strictly increasing
        timestamps = [b.timestamp.timestamp() for b in collected]
        assert timestamps == sorted(timestamps)
        assert len(set(timestamps)) == len(timestamps)

    @pytest.mark.asyncio
    async def test_iter_excludes_incomplete(self):
        """Last candle in response is always excluded."""
        candles = [_make_candle(1700000000000 + i * 60000) for i in range(3)]

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=candles)
        mock_resp.raise_for_status = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.close = AsyncMock()
        mock_session.closed = False

        collected = []

        async def stop_after_one(_):
            raise _StopIteration

        with (
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("asyncio.sleep", side_effect=stop_after_one),
        ):
            p = HyperliquidProvider("ETH", "1m", poll_interval=1.0)
            try:
                async for bar in p:
                    collected.append(bar)
            except _StopIteration:
                pass

        # 3 candles, last excluded → 2 bars
        assert len(collected) == 2


class TestClose:
    @pytest.mark.asyncio
    async def test_close_cleans_session(self):
        """close() closes the aiohttp session."""
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()

        p = HyperliquidProvider("ETH")
        p._session = mock_session
        await p.close()

        mock_session.close.assert_called_once()
        assert p._session is None


class TestTfToMinutes:
    def test_known_timeframes(self):
        assert _tf_to_minutes("1m") == 1
        assert _tf_to_minutes("5m") == 5
        assert _tf_to_minutes("15m") == 15
        assert _tf_to_minutes("30m") == 30
        assert _tf_to_minutes("1h") == 60
        assert _tf_to_minutes("4h") == 240
        assert _tf_to_minutes("1d") == 1440

    def test_unknown_defaults_to_1(self):
        assert _tf_to_minutes("2h") == 1
