"""Integration tests for GridBacktestEngine with synthetic data."""

from datetime import datetime, timedelta
from typing import Iterator, List

import pytest

from replaybt.data.providers.base import DataProvider
from replaybt.data.types import Bar
from replaybt.grid.engine import GridBacktestEngine
from replaybt.grid.types import GridConfig


class ListProvider(DataProvider):
    """Test data provider from a list of bars."""

    def __init__(self, bars: List[Bar], sym: str = "TEST", tf: str = "1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self) -> Iterator[Bar]:
        return iter(self._bars)

    def symbol(self) -> str:
        return self._sym

    def timeframe(self) -> str:
        return self._tf


def _ranging_bars(n: int, mid: float = 100.0, amplitude: float = 1.0) -> List[Bar]:
    """Generate bars that oscillate around mid price."""
    bars = []
    import math

    for i in range(n):
        t = datetime(2024, 1, 1) + timedelta(minutes=i)
        # Sinusoidal oscillation
        offset = amplitude * math.sin(2 * math.pi * i / 20)
        c = mid + offset
        h = c + amplitude * 0.3
        lo = c - amplitude * 0.3
        o = mid + amplitude * math.sin(2 * math.pi * (i - 1) / 20) if i > 0 else mid
        bars.append(Bar(timestamp=t, open=o, high=h, low=lo, close=c, volume=1000))
    return bars


def _trending_bars(
    n: int, start: float = 100.0, trend_per_bar: float = 0.1
) -> List[Bar]:
    """Generate bars with consistent uptrend."""
    bars = []
    price = start
    for i in range(n):
        t = datetime(2024, 1, 1) + timedelta(minutes=i)
        o = price
        c = price + trend_per_bar
        h = max(o, c) + 0.2
        lo = min(o, c) - 0.1
        bars.append(Bar(timestamp=t, open=o, high=h, low=lo, close=c, volume=1000))
        price = c
    return bars


def _spike_bars(
    n: int, mid: float = 100.0, spike_at: int = 10, spike_size: float = 10.0
) -> List[Bar]:
    """Generate calm bars with a volatility spike at a specific bar."""
    bars = []
    for i in range(n):
        t = datetime(2024, 1, 1) + timedelta(minutes=i)
        if i == spike_at:
            bars.append(
                Bar(
                    timestamp=t,
                    open=mid,
                    high=mid + spike_size,
                    low=mid - spike_size,
                    close=mid + spike_size * 0.5,
                    volume=5000,
                )
            )
        else:
            noise = 0.1 * (i % 3 - 1)
            bars.append(
                Bar(
                    timestamp=t,
                    open=mid + noise,
                    high=mid + 0.2,
                    low=mid - 0.2,
                    close=mid + noise,
                    volume=1000,
                )
            )
    return bars


class TestRangingMarket:
    def test_positive_pnl_from_spread(self):
        """Price oscillates -> spread capture should dominate."""
        bars = _ranging_bars(200, mid=100.0, amplitude=2.0)
        config = GridConfig(
            capital=10_000,
            spread_pct=0.005,
            num_levels=5,
            range_pct=0.10,
            tick_size=0.01,
            slippage_pct=0.0,
            max_inventory_pct=0.5,
            recenter_threshold=0.05,
            recenter_min_bars=10,
            snapshot_interval=10,
        )
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        assert results.total_fills > 0
        assert results.spread_pnl > 0
        assert results.total_bars == 200

    def test_bid_and_ask_fills(self):
        """Both sides should get fills in ranging market."""
        bars = _ranging_bars(200, mid=100.0, amplitude=2.0)
        config = GridConfig(
            capital=10_000,
            spread_pct=0.005,
            num_levels=5,
            range_pct=0.10,
            slippage_pct=0.0,
            recenter_threshold=0.05,
            recenter_min_bars=10,
            snapshot_interval=10,
        )
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        assert results.bid_fills > 0
        assert results.ask_fills > 0


class TestTrendingMarket:
    def test_inventory_accumulation(self):
        """Strong uptrend -> bids keep filling, inventory grows."""
        bars = _trending_bars(200, start=100.0, trend_per_bar=0.05)
        config = GridConfig(
            capital=10_000,
            spread_pct=0.005,
            num_levels=5,
            range_pct=0.10,
            slippage_pct=0.0,
            max_inventory_pct=0.5,
            recenter_threshold=0.02,
            recenter_min_bars=5,
            snapshot_interval=10,
        )
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        # In a strong uptrend, we accumulate base
        assert results.total_fills > 0
        assert results.recenters > 1  # price moves enough to trigger recenters


class TestVolGuard:
    def test_pause_on_spike(self):
        """Volatility spike triggers vol guard -> grid cancelled."""
        bars = _spike_bars(50, mid=100.0, spike_at=15, spike_size=5.0)
        config = GridConfig(
            capital=10_000,
            spread_pct=0.005,
            num_levels=5,
            range_pct=0.10,
            slippage_pct=0.0,
            vol_guard_enabled=True,
            vol_guard_atr_period=3,
            vol_guard_threshold_pct=0.5,
            vol_guard_cooldown=5,
            snapshot_interval=5,
        )
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        assert results.vol_guard_triggers >= 1
        assert results.vol_guard_bars_paused > 0


class TestCircuitBreaker:
    def test_drawdown_pauses_grid(self):
        """Large drawdown triggers circuit breaker -> fewer fills than without."""
        bars = _trending_bars(100, start=100.0, trend_per_bar=-0.5)
        base_config = dict(
            capital=10_000,
            spread_pct=0.005,
            num_levels=5,
            range_pct=0.10,
            slippage_pct=0.0,
            recenter_threshold=0.02,
            recenter_min_bars=5,
            snapshot_interval=5,
        )

        # With circuit breaker
        config_cb = GridConfig(**base_config, max_drawdown_pct=0.03)
        results_cb = GridBacktestEngine(data=ListProvider(bars), config=config_cb).run()

        # Without circuit breaker (very high threshold)
        config_no_cb = GridConfig(**base_config, max_drawdown_pct=0.99)
        results_no_cb = GridBacktestEngine(
            data=ListProvider(bars), config=config_no_cb
        ).run()

        # Circuit breaker should result in fewer fills (grid paused)
        assert results_cb.total_fills <= results_no_cb.total_fills


class TestRecenter:
    def test_price_deviation_triggers_recenter(self):
        """Price moving past threshold triggers re-center."""
        # Price gradually rises then returns
        bars = []
        for i in range(100):
            t = datetime(2024, 1, 1) + timedelta(minutes=i)
            if i < 50:
                p = 100.0 + i * 0.1  # slow rise
            else:
                p = 105.0 - (i - 50) * 0.1  # slow fall
            bars.append(
                Bar(
                    timestamp=t,
                    open=p - 0.05,
                    high=p + 0.3,
                    low=p - 0.3,
                    close=p,
                    volume=1000,
                )
            )
        config = GridConfig(
            capital=10_000,
            spread_pct=0.005,
            num_levels=5,
            range_pct=0.10,
            slippage_pct=0.0,
            recenter_threshold=0.01,
            recenter_min_bars=5,
            snapshot_interval=10,
        )
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        # Should have multiple re-centers from the 5% price move
        assert results.recenters > 1


class TestGridResults:
    def test_summary_format(self):
        bars = _ranging_bars(100, mid=100.0, amplitude=1.0)
        config = GridConfig(
            capital=10_000,
            spread_pct=0.005,
            num_levels=3,
            range_pct=0.10,
            slippage_pct=0.0,
            snapshot_interval=10,
        )
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        summary = results.summary()
        assert "Grid MM Results" in summary
        assert "Net PnL" in summary
        assert "Spread PnL" in summary

    def test_to_backtest_results(self):
        bars = _ranging_bars(100, mid=100.0, amplitude=2.0)
        config = GridConfig(
            capital=10_000,
            spread_pct=0.005,
            num_levels=3,
            range_pct=0.10,
            slippage_pct=0.0,
            snapshot_interval=10,
        )
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        bt = results.to_backtest_results()
        assert bt.initial_equity == results.initial_capital
        assert bt.final_equity == results.final_equity
        assert bt.net_pnl == pytest.approx(results.total_pnl)
        assert bt.symbol == results.symbol

    def test_empty_data(self):
        bars = [
            Bar(
                timestamp=datetime(2024, 1, 1),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=0,
            )
        ]
        config = GridConfig(capital=10_000)
        engine = GridBacktestEngine(data=ListProvider(bars), config=config)
        results = engine.run()

        assert results.total_fills == 0
        assert results.final_equity == 10_000.0


class TestSymbol:
    def test_symbol_from_provider(self):
        bars = _ranging_bars(50)
        config = GridConfig(capital=10_000, snapshot_interval=10)
        engine = GridBacktestEngine(data=ListProvider(bars, sym="ETH"), config=config)
        results = engine.run()
        assert results.symbol == "ETH"
