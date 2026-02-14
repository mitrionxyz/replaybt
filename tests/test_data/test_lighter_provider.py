"""Tests for LighterProvider and _BarBuilder (all mocked, no network)."""

import pytest
from datetime import datetime, timezone, timedelta

from replaybt.data.providers.live.lighter import (
    _BarBuilder,
    LighterProvider,
    LIGHTER_MARKETS,
)
from replaybt.data.types import Bar


class TestBarBuilder:
    """Test the tick-to-bar aggregator in isolation."""

    def test_first_tick_no_emit(self):
        """First tick starts a bar but doesn't complete one."""
        bb = _BarBuilder("1m", symbol="ETH")
        ts = datetime(2024, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
        result = bb.tick(100.0, ts)
        assert result is None

    def test_same_period_ticks_no_emit(self):
        """Multiple ticks in the same 1m period don't emit a bar."""
        bb = _BarBuilder("1m", symbol="ETH")
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        for sec in [0, 10, 20, 30, 40, 50]:
            result = bb.tick(100.0 + sec * 0.01, base + timedelta(seconds=sec))
            assert result is None

    def test_boundary_emits_completed_bar(self):
        """Tick crossing into new period emits the completed bar."""
        bb = _BarBuilder("1m", symbol="ETH")
        t0 = datetime(2024, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
        t1 = datetime(2024, 1, 1, 0, 1, 30, tzinfo=timezone.utc)

        bb.tick(100.0, t0)
        bar = bb.tick(101.0, t1)

        assert bar is not None
        assert isinstance(bar, Bar)
        assert bar.open == 100.0
        assert bar.close == 100.0
        assert bar.high == 100.0
        assert bar.low == 100.0
        assert bar.volume == 0.0
        assert bar.symbol == "ETH"
        assert bar.timeframe == "1m"

    def test_high_low_tracking(self):
        """High and Low track correctly across ticks."""
        bb = _BarBuilder("1m", symbol="SOL")
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        bb.tick(100.0, base)
        bb.tick(105.0, base + timedelta(seconds=10))
        bb.tick(95.0, base + timedelta(seconds=20))
        bb.tick(102.0, base + timedelta(seconds=30))

        # Cross boundary to emit
        bar = bb.tick(103.0, base + timedelta(minutes=1))

        assert bar is not None
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 95.0
        assert bar.close == 102.0

    def test_5m_boundary(self):
        """5-minute bars accumulate correctly."""
        bb = _BarBuilder("5m", symbol="ETH")
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Ticks at minutes 0, 1, 2, 3, 4 — all same 5m period
        for m in range(5):
            result = bb.tick(100.0 + m, base + timedelta(minutes=m))
            assert result is None

        # Tick at minute 5 — new period, emits bar
        bar = bb.tick(110.0, base + timedelta(minutes=5))
        assert bar is not None
        assert bar.open == 100.0
        assert bar.high == 104.0
        assert bar.low == 100.0
        assert bar.close == 104.0

    def test_1h_boundary(self):
        """1-hour bars accumulate correctly."""
        bb = _BarBuilder("1h", symbol="ETH")
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        bb.tick(100.0, base)
        bb.tick(110.0, base + timedelta(minutes=30))

        # Cross into next hour
        bar = bb.tick(105.0, base + timedelta(hours=1))
        assert bar is not None
        assert bar.open == 100.0
        assert bar.high == 110.0
        assert bar.low == 100.0
        assert bar.close == 110.0

    def test_reset(self):
        """reset() clears accumulated state."""
        bb = _BarBuilder("1m", symbol="ETH")
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        bb.tick(100.0, base)

        bb.reset()
        # After reset, first tick should not emit
        result = bb.tick(200.0, base + timedelta(minutes=5))
        assert result is None

    def test_multiple_bars_sequential(self):
        """Multiple bars emitted sequentially."""
        bb = _BarBuilder("1m", symbol="ETH")
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        bars = []
        bb.tick(100.0, base)
        bar = bb.tick(101.0, base + timedelta(minutes=1))
        if bar:
            bars.append(bar)
        bar = bb.tick(102.0, base + timedelta(minutes=2))
        if bar:
            bars.append(bar)

        assert len(bars) == 2
        assert bars[0].open == 100.0
        assert bars[1].open == 101.0


class TestLighterProviderExtractMidPrice:
    def test_extract_mid_price(self):
        """Correct mid from bid/ask."""
        p = LighterProvider("ETH")
        data = {
            "order_book": {
                "bids": [{"price": "3000.00"}],
                "asks": [{"price": "3002.00"}],
            }
        }
        mid = p._extract_mid_price(data)
        assert mid == 3001.0

    def test_extract_mid_price_empty_bids(self):
        """Returns None when bids are empty."""
        p = LighterProvider("ETH")
        data = {"order_book": {"bids": [], "asks": [{"price": "3002.00"}]}}
        assert p._extract_mid_price(data) is None

    def test_extract_mid_price_empty_asks(self):
        """Returns None when asks are empty."""
        p = LighterProvider("ETH")
        data = {"order_book": {"bids": [{"price": "3000.00"}], "asks": []}}
        assert p._extract_mid_price(data) is None

    def test_extract_mid_price_no_order_book(self):
        """Returns None when order_book key missing."""
        p = LighterProvider("ETH")
        assert p._extract_mid_price({}) is None
        assert p._extract_mid_price({"other": 1}) is None


class TestLighterProviderInit:
    def test_symbol(self):
        p = LighterProvider("ETH")
        assert p.symbol() == "ETH"

    def test_timeframe(self):
        p = LighterProvider("SOL", "5m")
        assert p.timeframe() == "5m"

    def test_unknown_symbol_raises(self):
        with pytest.raises(ValueError, match="Unknown Lighter market"):
            LighterProvider("UNKNOWN")

    def test_all_markets_valid(self):
        for sym in LIGHTER_MARKETS:
            p = LighterProvider(sym)
            assert p.symbol() == sym


class TestLighterProviderClose:
    @pytest.mark.asyncio
    async def test_close_resets_bar_builder(self):
        p = LighterProvider("ETH")
        # Simulate some state in bar builder
        p._bar_builder.tick(100.0, datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert p._bar_builder._open is not None

        await p.close()
        assert p._bar_builder._open is None
