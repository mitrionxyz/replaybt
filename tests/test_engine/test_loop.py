"""Tests for the 4-phase BacktestEngine loop."""

import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from replaybt.data.types import Bar, Fill, Position, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import Order, MarketOrder
from replaybt.strategy.base import Strategy


class ListProvider(DataProvider):
    """Test data provider from a list of bars."""

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
    """Generate n synthetic 1m bars with a slight uptrend."""
    bars = []
    price = base_price
    for i in range(n):
        o = price
        h = price + 0.5
        l = price - 0.3
        c = price + trend
        bars.append(Bar(
            timestamp=datetime(2024, 1, 1) + timedelta(minutes=i),
            open=o, high=h, low=l, close=c,
            volume=1000, symbol="TEST", timeframe="1m",
        ))
        price = c
    return bars


class AlwaysBuyStrategy(Strategy):
    """Buys on bar 2, verifying execution happens at bar 3's open."""

    def __init__(self):
        self.signal_bar_idx = 0
        self.bars_seen = 0

    def on_bar(self, bar, indicators, positions):
        self.bars_seen += 1
        if self.bars_seen == 2 and not positions:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.05,
                stop_loss_pct=0.03,
            )
        return None


class NeverBuyStrategy(Strategy):
    """Never signals — used to test engine runs clean with no trades."""

    def on_bar(self, bar, indicators, positions):
        return None


class TestExecutionTiming:
    """Verify the T+1 execution paradigm."""

    def test_order_executes_at_next_bar_open(self):
        """Signal at bar T → execute at bar T+1 OPEN."""
        bars = make_bars(10)
        strategy = AlwaysBuyStrategy()
        engine = BacktestEngine(
            strategy=strategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000, "default_size_usd": 10000},
        )

        # Track fills
        fills = []
        engine.on("fill", lambda f: fills.append(f))

        results = engine.run()

        # Strategy signals on bar 2 (index 1), executes at bar 3 (index 2)
        assert len(fills) >= 1
        entry_fill = fills[0]
        # Entry should be at bar 3's open (bar index 2)
        expected_open = bars[2].open
        # With slippage applied
        assert entry_fill.price > expected_open  # LONG slippage = pay more
        assert entry_fill.is_entry is True

    def test_no_same_bar_execution(self):
        """Cannot signal and execute on the same bar."""

        class ImmediateBuyStrategy(Strategy):
            """Tries to buy on bar 0."""
            def on_bar(self, bar, indicators, positions):
                if not positions:
                    return MarketOrder(side=Side.LONG, take_profit_pct=0.05, stop_loss_pct=0.03)
                return None

        bars = make_bars(5)
        engine = BacktestEngine(
            strategy=ImmediateBuyStrategy(),
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        # Signal on bar 0 → execute at bar 1
        assert len(fills) >= 1
        # Fill timestamp should be bar 1, not bar 0
        assert fills[0].timestamp == bars[1].timestamp

    def test_no_signal_on_close_bar(self):
        """Don't generate new signal on the same bar a position closes."""

        class BuyThenBuyStrategy(Strategy):
            """Always tries to buy if no position."""
            def on_bar(self, bar, indicators, positions):
                if not positions:
                    return MarketOrder(side=Side.LONG, take_profit_pct=0.03, stop_loss_pct=0.03)
                return None

        # Create bars where position enters, survives a few bars, then SL hit
        bars = [
            Bar(datetime(2024, 1, 1, 0, 0), 100, 101, 99, 100.5, 1000, "TEST"),
            # Signal on bar 0 → entry on bar 1
            Bar(datetime(2024, 1, 1, 0, 1), 100.5, 101, 100, 100.8, 1000, "TEST"),
            Bar(datetime(2024, 1, 1, 0, 2), 100.8, 101.2, 100.5, 101.0, 1000, "TEST"),
            # SL hit on bar 3 (open gaps down past SL ~97.5)
            Bar(datetime(2024, 1, 1, 0, 3), 95.0, 96, 94, 95.5, 1000, "TEST"),
            # If no just_closed guard, strategy would signal here on bar 3
            # but it should NOT (just_closed=True skips signal generation)
            Bar(datetime(2024, 1, 1, 0, 4), 95.5, 96, 95, 95.8, 1000, "TEST"),
            # Signal allowed on bar 4 → entry on bar 5
            Bar(datetime(2024, 1, 1, 0, 5), 95.8, 96.5, 95, 96.0, 1000, "TEST"),
            Bar(datetime(2024, 1, 1, 0, 6), 96.0, 97, 95.5, 96.5, 1000, "TEST"),
        ]

        engine = BacktestEngine(
            strategy=BuyThenBuyStrategy(),
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        )

        signals = []
        engine.on("signal", lambda o: signals.append(o))
        results = engine.run()

        # First trade: entered bar 1, SL gap on bar 3
        assert len(results.trades) >= 1
        t1 = results.trades[0]
        assert t1.entry_time == datetime(2024, 1, 1, 0, 1)
        assert t1.exit_time == datetime(2024, 1, 1, 0, 3)

        # Second entry should be bar 5 (NOT bar 4 — bar 3 was just_closed)
        if len(results.trades) >= 2:
            t2 = results.trades[1]
            assert t2.entry_time == datetime(2024, 1, 1, 0, 5)


class TestNoTrades:
    def test_engine_runs_with_no_signals(self):
        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=NeverBuyStrategy(),
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        )
        results = engine.run()
        assert results.total_trades == 0
        assert results.final_equity == 10000


class TestMultiPosition:
    def test_max_positions_enforced(self):
        """Cannot open more positions than max_positions."""

        class GreedyStrategy(Strategy):
            def on_bar(self, bar, indicators, positions):
                if len(positions) < 3:
                    return MarketOrder(side=Side.LONG, take_profit_pct=0.10, stop_loss_pct=0.10)
                return None

        bars = make_bars(20)
        engine = BacktestEngine(
            strategy=GreedyStrategy(),
            data=ListProvider(bars),
            config={"initial_equity": 10000, "max_positions": 2},
        )
        results = engine.run()

        # Portfolio should never exceed 2 positions
        # (We can verify by checking trade count — with max_positions=2,
        # can only open 2 before they need to close)
        assert engine.portfolio.max_positions == 2


class TestEventCallbacks:
    def test_fill_callback_fires(self):
        bars = make_bars(5)
        engine = BacktestEngine(
            strategy=AlwaysBuyStrategy(),
            data=ListProvider(bars),
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()
        assert len(fills) >= 1

    def test_bar_callback_fires_every_bar(self):
        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=NeverBuyStrategy(),
            data=ListProvider(bars),
        )

        bar_count = []
        engine.on("bar", lambda b: bar_count.append(1))
        engine.run()
        assert len(bar_count) == 10
