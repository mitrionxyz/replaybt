"""Tests for BinanceFetcher (mocked HTTP, no network)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call

from replaybt.data.fetchers.binance import BinanceFetcher


def _make_kline(open_time_ms, o=100.0, h=101.0, l=99.0, c=100.5, v=1000.0):
    """Create a single Binance kline response row."""
    close_time_ms = open_time_ms + 60_000 - 1  # 1m candle
    return [
        open_time_ms, str(o), str(h), str(l), str(c), str(v),
        close_time_ms, "50000.0", 100, "500.0", "25000.0", "0",
    ]


def _mock_requests():
    """Create a mock requests module."""
    return MagicMock()


def _setup_responses(mock_requests, *response_data_list):
    """Set up mock_requests.get to return responses in sequence."""
    responses = []
    for data in response_data_list:
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        responses.append(resp)
    mock_requests.get.side_effect = responses


class TestBinanceFetcher:
    def test_single_page_fetch(self):
        """Fetch that fits in one page returns correct DataFrame."""
        klines = [_make_kline(1704067200000 + i * 60000) for i in range(5)]
        mock_req = _mock_requests()
        _setup_responses(mock_req, klines)

        with patch("replaybt.data.fetchers.binance._import_requests", return_value=mock_req):
            fetcher = BinanceFetcher()
            df = fetcher.fetch(
                "ETHUSDT", "1m",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc),
            )

        assert len(df) == 5
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert df["open"].dtype == float
        assert df["close"].iloc[0] == 100.5

    def test_multi_page_pagination(self):
        """Multiple pages are concatenated correctly."""
        page1 = [_make_kline(1704067200000 + i * 60000) for i in range(1000)]
        page2 = [_make_kline(1704067200000 + (1000 + i) * 60000) for i in range(500)]
        mock_req = _mock_requests()
        _setup_responses(mock_req, page1, page2)

        with patch("replaybt.data.fetchers.binance._import_requests", return_value=mock_req):
            fetcher = BinanceFetcher(rate_limit=0)
            df = fetcher.fetch(
                "ETHUSDT", "1m",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )

        assert len(df) == 1500
        assert mock_req.get.call_count == 2

    def test_rate_limiting(self):
        """time.sleep is called between paginated requests."""
        page1 = [_make_kline(1704067200000 + i * 60000) for i in range(1000)]
        page2 = [_make_kline(1704067200000 + (1000 + i) * 60000) for i in range(100)]
        mock_req = _mock_requests()
        _setup_responses(mock_req, page1, page2)

        with patch("replaybt.data.fetchers.binance._import_requests", return_value=mock_req), \
             patch("replaybt.data.fetchers.binance.time.sleep") as mock_sleep:
            fetcher = BinanceFetcher(rate_limit=0.5)
            fetcher.fetch(
                "ETHUSDT", "1m",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )

        mock_sleep.assert_called_once_with(0.5)

    def test_empty_response(self):
        """Empty response returns empty DataFrame with correct columns."""
        mock_req = _mock_requests()
        _setup_responses(mock_req, [])

        with patch("replaybt.data.fetchers.binance._import_requests", return_value=mock_req):
            fetcher = BinanceFetcher()
            df = fetcher.fetch("ETHUSDT", "1m")

        assert len(df) == 0
        assert "timestamp" in df.columns

    def test_timestamp_conversion(self):
        """Timestamps are correctly converted from ms epoch to UTC datetime."""
        ts_ms = 1704067200000  # 2024-01-01 00:00:00 UTC
        klines = [_make_kline(ts_ms)]
        mock_req = _mock_requests()
        _setup_responses(mock_req, klines)

        with patch("replaybt.data.fetchers.binance._import_requests", return_value=mock_req):
            fetcher = BinanceFetcher()
            df = fetcher.fetch("ETHUSDT", "1m")

        assert df["timestamp"].iloc[0].year == 2024
        assert df["timestamp"].iloc[0].month == 1
        assert df["timestamp"].iloc[0].day == 1

    def test_unsupported_timeframe(self):
        """Unsupported timeframe raises ValueError."""
        fetcher = BinanceFetcher()
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            fetcher.fetch("ETHUSDT", "2m")

    def test_exchange_name(self):
        fetcher = BinanceFetcher()
        assert fetcher.exchange_name() == "binance"
