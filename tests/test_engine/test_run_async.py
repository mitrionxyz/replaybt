"""Tests for BacktestEngine.run_async()."""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, List, Optional

from replaybt.data.types import Bar, Fill, Position, Side
from replaybt.data.providers.base import DataProvider
from replaybt.data.providers.live.base import AsyncDataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import MarketOrder
from replaybt.strategy.base import Strategy


class AsyncListProvider(AsyncDataProvider):
    """Test async provider from a list of bars."""

    def __init__(self, bars: List[Bar], sym: str = "TEST", tf: str = "1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    async def __aiter__(self) -> AsyncIterator[Bar]:
        for bar in self._bars:
            yield bar

    def symbol(self) -> str:
        return self._sym

    def timeframe(self) -> str:
        return self._tf


class SyncListProvider(DataProvider):
    """Test sync provider from a list of bars."""

    def __init__(self, bars: List[Bar], sym: str = "TEST", tf: str = "1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf


def make_bars(n: int, base_price: float = 100.0, trend: float = 0.1) -> List[Bar]:
    """Generate n synthetic 1m bars."""
    bars = []
    price = base_price
    for i in range(n):
        bars.append(Bar(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
            open=price, high=price + 0.5, low=price - 0.3, close=price + trend,
            volume=1000, symbol="TEST", timeframe="1m",
        ))
        price += trend
    return bars


class BuyOnBar2Strategy(Strategy):
    """Buys on bar 2, for testing execution timing."""

    def __init__(self):
        self.bars_seen = 0
        self.fills = []

    def on_bar(self, bar, indicators, positions):
        self.bars_seen += 1
        if self.bars_seen == 2 and not positions:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.50,
                stop_loss_pct=0.50,
            )
        return None

    def on_fill(self, fill):
        self.fills.append(fill)
        return None


class NeverTradeStrategy(Strategy):
    """Never signals."""

    def __init__(self):
        self.bars_seen = 0

    def on_bar(self, bar, indicators, positions):
        self.bars_seen += 1
        return None


class TestRunAsyncBasic:
    @pytest.mark.asyncio
    async def test_run_async_returns_results(self):
        """run_async() returns BacktestResults populated correctly."""
        bars = make_bars(10)
        strat = NeverTradeStrategy()
        data = AsyncListProvider(bars)

        engine = BacktestEngine(
            strategy=strat,
            data=SyncListProvider(bars),  # for __init__ (needs DataProvider)
            config={"initial_equity": 10000},
        )
        results = await engine.run_async(data)

        assert results.symbol == "TEST"
        assert results.initial_equity == 10000
        assert results.total_trades == 0
        assert strat.bars_seen == 10

    @pytest.mark.asyncio
    async def test_run_async_with_strategy(self):
        """Strategy.on_bar() called per bar, fills work."""
        bars = make_bars(20)
        strat = BuyOnBar2Strategy()
        data = AsyncListProvider(bars)

        engine = BacktestEngine(
            strategy=strat,
            data=SyncListProvider(bars),
            config={"initial_equity": 10000},
        )
        results = await engine.run_async(data)

        assert strat.bars_seen == 20
        assert len(strat.fills) >= 1
        assert strat.fills[0].is_entry is True


class TestRunAsyncParity:
    @pytest.mark.asyncio
    async def test_run_async_matches_run(self):
        """Same bars → identical results between sync run() and async run_async()."""
        bars = make_bars(50)
        config = {"initial_equity": 10000}

        # Sync run
        sync_strat = BuyOnBar2Strategy()
        sync_data = SyncListProvider(bars)
        sync_engine = BacktestEngine(
            strategy=sync_strat,
            data=sync_data,
            config=config,
        )
        sync_results = sync_engine.run()

        # Async run
        async_strat = BuyOnBar2Strategy()
        async_data = AsyncListProvider(bars)
        async_engine = BacktestEngine(
            strategy=async_strat,
            data=SyncListProvider(bars),
            config=config,
        )
        async_results = await async_engine.run_async(async_data)

        assert sync_results.net_pnl == async_results.net_pnl
        assert sync_results.total_trades == async_results.total_trades
        assert sync_results.win_rate == async_results.win_rate
        assert sync_results.max_drawdown_pct == async_results.max_drawdown_pct
        assert sync_results.total_fees == async_results.total_fees
        assert sync_results.final_equity == async_results.final_equity

    @pytest.mark.asyncio
    async def test_run_async_no_trades_matches(self):
        """No-trade scenario: sync and async produce same results."""
        bars = make_bars(10)
        config = {"initial_equity": 10000}

        sync_engine = BacktestEngine(
            strategy=NeverTradeStrategy(),
            data=SyncListProvider(bars),
            config=config,
        )
        sync_results = sync_engine.run()

        async_engine = BacktestEngine(
            strategy=NeverTradeStrategy(),
            data=SyncListProvider(bars),
            config=config,
        )
        async_results = await async_engine.run_async(AsyncListProvider(bars))

        assert sync_results.net_pnl == async_results.net_pnl
        assert sync_results.total_trades == async_results.total_trades


class TestExistingRunUnchanged:
    def test_sync_run_still_works(self):
        """Regression: sync run() still works after adding run_async()."""
        bars = make_bars(20)
        strat = BuyOnBar2Strategy()

        engine = BacktestEngine(
            strategy=strat,
            data=SyncListProvider(bars),
            config={"initial_equity": 10000},
        )
        results = engine.run()

        assert strat.bars_seen == 20
        assert results.initial_equity == 10000


class TestRunAsyncWarmup:
    @pytest.mark.asyncio
    async def test_warmup_pattern(self):
        """Warmup bars seed indicators before run_async."""
        all_bars = make_bars(30)
        warmup_bars = all_bars[:10]
        live_bars = all_bars[10:]

        strat = NeverTradeStrategy()
        data = AsyncListProvider(live_bars)

        engine = BacktestEngine(
            strategy=strat,
            data=SyncListProvider(live_bars),
            config={"initial_equity": 10000},
        )

        # Warm up indicators
        for bar in warmup_bars:
            engine.indicators.update(bar)

        results = await engine.run_async(data)

        # Strategy only saw live bars (not warmup)
        assert strat.bars_seen == 20
        assert results.symbol == "TEST"


class TestRunAsyncEmptyData:
    @pytest.mark.asyncio
    async def test_empty_provider(self):
        """run_async() handles empty provider gracefully."""
        strat = NeverTradeStrategy()
        data = AsyncListProvider([])

        engine = BacktestEngine(
            strategy=strat,
            data=SyncListProvider([]),
            config={"initial_equity": 10000},
        )
        results = await engine.run_async(data)

        assert results.total_trades == 0
        assert results.net_pnl == 0.0
        assert strat.bars_seen == 0
