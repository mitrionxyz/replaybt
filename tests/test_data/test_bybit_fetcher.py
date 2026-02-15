"""Tests for BybitFetcher (mocked HTTP, no network)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from replaybt.data.fetchers.bybit import BybitFetcher


def _make_kline(open_time_ms, o=100.0, h=101.0, l=99.0, c=100.5, v=1000.0):
    """Create a single Bybit kline response row."""
    return [
        str(open_time_ms), str(o), str(h), str(l), str(c), str(v), "50000.0",
    ]


def _mock_requests():
    """Create a mock requests module."""
    return MagicMock()


def _make_bybit_response(klines, ret_code=0):
    """Create a mock requests.Response with Bybit envelope."""
    resp = MagicMock()
    resp.json.return_value = {
        "retCode": ret_code,
        "retMsg": "OK",
        "result": {"list": klines},
    }
    resp.raise_for_status.return_value = None
    return resp


class TestBybitFetcher:
    def test_single_page_fetch(self):
        """Fetch that fits in one page returns correct DataFrame."""
        # Bybit returns descending
        klines = [_make_kline(1704067200000 + (4 - i) * 60000) for i in range(5)]
        mock_req = _mock_requests()
        mock_req.get.return_value = _make_bybit_response(klines)

        with patch("replaybt.data.fetchers.bybit._import_requests", return_value=mock_req):
            fetcher = BybitFetcher()
            df = fetcher.fetch(
                "ETHUSDT", "1m",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc),
            )

        assert len(df) == 5
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        # Should be sorted ascending after processing
        assert df["timestamp"].iloc[0] < df["timestamp"].iloc[-1]

    def test_multi_page_pagination(self):
        """Multiple pages are concatenated correctly."""
        # Page 1: newest data (descending)
        page1 = [_make_kline(1704067200000 + (399 - i) * 60000) for i in range(200)]
        # Page 2: older data (descending)
        page2 = [_make_kline(1704067200000 + (199 - i) * 60000) for i in range(100)]

        mock_req = _mock_requests()
        mock_req.get.side_effect = [
            _make_bybit_response(page1),
            _make_bybit_response(page2),
        ]

        with patch("replaybt.data.fetchers.bybit._import_requests", return_value=mock_req):
            fetcher = BybitFetcher(rate_limit=0)
            df = fetcher.fetch(
                "ETHUSDT", "1m",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )

        assert len(df) == 300
        assert mock_req.get.call_count == 2

    def test_empty_response(self):
        """Empty response returns empty DataFrame with correct columns."""
        mock_req = _mock_requests()
        mock_req.get.return_value = _make_bybit_response([])

        with patch("replaybt.data.fetchers.bybit._import_requests", return_value=mock_req):
            fetcher = BybitFetcher()
            df = fetcher.fetch("ETHUSDT", "1m")

        assert len(df) == 0
        assert "timestamp" in df.columns

    def test_api_error(self):
        """Non-zero retCode raises RuntimeError."""
        mock_req = _mock_requests()
        mock_req.get.return_value = _make_bybit_response([], ret_code=10001)

        with patch("replaybt.data.fetchers.bybit._import_requests", return_value=mock_req):
            fetcher = BybitFetcher()
            with pytest.raises(RuntimeError, match="Bybit API error"):
                fetcher.fetch("ETHUSDT", "1m")

    def test_exchange_name(self):
        fetcher = BybitFetcher()
        assert fetcher.exchange_name() == "bybit"
