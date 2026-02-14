"""Tests for DelayTest and OOSSplit stress tests."""

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from replaybt.data.types import Bar, Fill, Position, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import MarketOrder
from replaybt.strategy.base import Strategy
from replaybt.validation.stress import (
    DelayTest, DelayTestResult, OOSSplit, OOSResult,
)


class ListProvider(DataProvider):
    def __init__(self, bars, sym="TEST", tf="1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf


def make_trending_bars(n=100, base=100.0, trend=0.05):
    """Generate bars with a consistent uptrend (robust to delay)."""
    bars = []
    price = base
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


def make_timing_sensitive_bars(n=60):
    """Bars where a 1-bar delay causes entry at a much worse price.

    Pattern: flat, then sudden spike, then reversal.
    Strategy buys on the spike bar, but the next bar opens much higher
    and then crashes.
    """
    bars = []
    for i in range(n):
        t = datetime(2024, 1, 1) + timedelta(minutes=i)
        if i < 20:
            # Flat
            bars.append(Bar(t, 100, 101, 99, 100, 1000, "TEST"))
        elif i == 20:
            # Spike bar — strategy signals here
            bars.append(Bar(t, 100, 108, 100, 107, 5000, "TEST"))
        elif i == 21:
            # Normal execution: entry at 107 open, still OK
            bars.append(Bar(t, 107, 108, 106, 107.5, 2000, "TEST"))
        elif i == 22:
            # Delayed execution would enter here at 115
            bars.append(Bar(t, 115, 116, 100, 101, 3000, "TEST"))
        else:
            # Crash — delayed entry gets stopped out badly
            bars.append(Bar(t, 95 - (i - 23) * 0.5, 96, 90, 92, 2000, "TEST"))
    return bars


class RobustTrendStrategy(Strategy):
    """Buy on bar 5, take profit at 5%. Robust to delay."""
    def __init__(self):
        self.bars_seen = 0

    def on_bar(self, bar, indicators, positions):
        self.bars_seen += 1
        if self.bars_seen == 5 and not positions:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.05,
                stop_loss_pct=0.10,
            )
        return None


class TimingSensitiveStrategy(Strategy):
    """Buys when price spikes >5%. Very timing dependent."""
    def __init__(self):
        self._prev_close = None

    def on_bar(self, bar, indicators, positions):
        if self._prev_close is not None and not positions:
            change = (bar.close - self._prev_close) / self._prev_close
            if change > 0.05:
                self._prev_close = bar.close
                return MarketOrder(
                    side=Side.LONG,
                    take_profit_pct=0.08,
                    stop_loss_pct=0.05,
                )
        self._prev_close = bar.close
        return None


# ------------------------------------------------------------------
# DelayTest tests
# ------------------------------------------------------------------

class TestDelayTest:
    def test_delay_test_runs(self):
        bars = make_trending_bars(50)
        result = DelayTest(
            strategy_factory=RobustTrendStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        ).run()
        assert isinstance(result, DelayTestResult)

    def test_delay_test_pass_robust_strategy(self):
        bars = make_trending_bars(100)
        result = DelayTest(
            strategy_factory=RobustTrendStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        ).run()
        assert result.verdict == "PASS"

    def test_delay_result_fields(self):
        bars = make_trending_bars(50)
        result = DelayTest(
            strategy_factory=RobustTrendStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        ).run()
        assert result.normal is not None
        assert result.delayed is not None
        assert result.delay_bars == 1
        assert isinstance(result.pnl_change_pct, float)
        assert isinstance(result.wr_change, float)
        assert result.verdict in ("PASS", "FAIL")

    def test_delay_test_custom_delay(self):
        bars = make_trending_bars(50)
        result = DelayTest(
            strategy_factory=RobustTrendStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
            delay_bars=3,
        ).run()
        assert result.delay_bars == 3

    def test_delay_test_no_trades(self):
        """Strategy that never trades should pass (0 PnL both times)."""
        class NeverTradeStrategy(Strategy):
            def on_bar(self, bar, indicators, positions):
                return None

        bars = make_trending_bars(20)
        result = DelayTest(
            strategy_factory=NeverTradeStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        ).run()
        assert result.verdict == "PASS"
        assert result.pnl_change_pct == 0.0


# ------------------------------------------------------------------
# OOSSplit tests
# ------------------------------------------------------------------

class TestOOSSplit:
    def test_oos_split_runs(self):
        bars = make_trending_bars(100)
        result = OOSSplit(
            strategy_factory=RobustTrendStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        ).run()
        assert isinstance(result, OOSResult)

    def test_oos_result_fields(self):
        bars = make_trending_bars(100)
        result = OOSSplit(
            strategy_factory=RobustTrendStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        ).run()
        assert result.train is not None
        assert result.test is not None
        assert result.split_ratio == 0.5
        assert isinstance(result.wr_divergence, float)
        assert isinstance(result.pnl_ratio, float)
        assert result.verdict in ("PASS", "FAIL")

    def test_oos_split_custom_ratio(self):
        bars = make_trending_bars(100)
        result = OOSSplit(
            strategy_factory=RobustTrendStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
            split_ratio=0.7,
        ).run()
        assert result.split_ratio == 0.7

    def test_oos_split_no_trades(self):
        """No-trade strategy should have 0 divergence."""
        class NeverTradeStrategy(Strategy):
            def on_bar(self, bar, indicators, positions):
                return None

        bars = make_trending_bars(50)
        result = OOSSplit(
            strategy_factory=NeverTradeStrategy,
            data=ListProvider(bars),
            config={"initial_equity": 10000},
        ).run()
        assert result.wr_divergence == 0.0
