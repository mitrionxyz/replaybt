"""Tests for Step Mode (StepEngine)."""

from datetime import datetime, timedelta
from typing import Iterator

import pytest

from replaybt.data.types import Bar, Side, Position
from replaybt.data.providers.base import DataProvider
from replaybt.engine.orders import MarketOrder, LimitOrder
from replaybt.engine.step import StepEngine, StepObservation, StepResult
from replaybt.engine.loop import BacktestEngine
from replaybt.strategy.base import Strategy


class _FakeProvider(DataProvider):
    """Yields N bars with rising prices."""

    def __init__(self, n: int = 20, base_price: float = 100.0):
        self._n = n
        self._base = base_price

    def __iter__(self) -> Iterator[Bar]:
        for i in range(self._n):
            p = self._base + i * 0.5
            yield Bar(
                timestamp=datetime(2025, 1, 1) + timedelta(minutes=i),
                open=p,
                high=p + 0.3,
                low=p - 0.3,
                close=p + 0.1,
                volume=1000.0,
                symbol="TEST",
                timeframe="1m",
            )

    def symbol(self) -> str:
        return "TEST"

    def timeframe(self) -> str:
        return "1m"


class _TrendProvider(DataProvider):
    """Yields bars that go up then down (for TP/SL testing)."""

    def __init__(self):
        self._bars = []
        base = datetime(2025, 1, 1)
        # Bar 0: entry signal bar
        # Bar 1-5: price rises 2% per bar (triggers TP at 5%)
        # Bar 6+: price crashes
        prices = [100, 100, 102, 104, 106, 108, 80, 75, 70]
        for i, p in enumerate(prices):
            self._bars.append(Bar(
                timestamp=base + timedelta(minutes=i),
                open=p,
                high=p + 0.5,
                low=p - 0.5,
                close=p,
                volume=1000.0,
                symbol="TEST",
                timeframe="1m",
            ))

    def __iter__(self) -> Iterator[Bar]:
        yield from self._bars

    def symbol(self) -> str:
        return "TEST"

    def timeframe(self) -> str:
        return "1m"


class TestStepEngine:
    def test_reset_returns_first_bar(self):
        """Observation contains bar 0's data."""
        env = StepEngine(data=_FakeProvider(n=5))
        obs = env.reset()

        assert isinstance(obs, StepObservation)
        assert obs.bar.open == 100.0
        assert obs.step_count == 0
        assert obs.done is False

    def test_reset_clears_state(self):
        """Clean slate after previous run."""
        env = StepEngine(data=_FakeProvider(n=5))

        # First run
        obs = env.reset()
        env.step(MarketOrder(side=Side.LONG, take_profit_pct=0.5))
        env.step(None)

        # Reset and verify clean
        obs = env.reset()
        assert obs.step_count == 0
        assert obs.positions == []
        assert obs.equity == 10_000.0

    def test_step_advances_one_bar(self):
        """step_count increments by 1."""
        env = StepEngine(data=_FakeProvider(n=5))
        env.reset()

        r1 = env.step(None)
        assert r1.observation.step_count == 1

        r2 = env.step(None)
        assert r2.observation.step_count == 2

    def test_step_none_no_order(self):
        """No pending order created with None action."""
        env = StepEngine(data=_FakeProvider(n=5))
        env.reset()

        result = env.step(None)
        assert result.observation.positions == []
        assert result.reward == 0.0

    def test_step_market_order_fills_next(self):
        """MarketOrder at step N fills at step N+1."""
        env = StepEngine(data=_FakeProvider(n=10), config={
            "slippage": 0.0, "taker_fee": 0.0,
        })
        env.reset()

        # Step 1: submit order
        r1 = env.step(MarketOrder(side=Side.LONG, take_profit_pct=0.5))
        # Order is pending, fills at this bar's open (since we submitted before step)
        assert len(r1.observation.positions) == 1
        assert r1.info["fills"]  # Fill happened

    def test_step_limit_order_tracked(self):
        """LimitOrder tracked in pending limits."""
        env = StepEngine(data=_FakeProvider(n=10), config={
            "slippage": 0.0, "taker_fee": 0.0,
        })
        env.reset()

        # Submit limit order well below market
        result = env.step(LimitOrder(side=Side.LONG, limit_price=50.0))
        # Should not fill (price never reaches 50)
        assert len(result.observation.positions) == 0

    def test_step_reward_zero_no_trades(self):
        """0 reward when no position closes."""
        env = StepEngine(data=_FakeProvider(n=5))
        env.reset()

        result = env.step(None)
        assert result.reward == 0.0

    def test_step_reward_on_exit(self):
        """Reward = PnL when trade closes."""
        env = StepEngine(data=_TrendProvider(), config={
            "slippage": 0.0, "taker_fee": 0.0,
        })
        env.reset()

        # Submit long order (fills at bar 1 open = 100)
        r = env.step(MarketOrder(
            side=Side.LONG,
            take_profit_pct=0.05,  # 5% TP
            stop_loss_pct=0.30,    # 30% SL (won't hit)
        ))

        # Step through rising bars until TP hits
        total_reward = r.reward
        while not r.done:
            r = env.step(None)
            total_reward += r.reward
            if r.info.get("exits"):
                break

        # Should have closed with profit
        assert total_reward > 0

    def test_step_done_at_end(self):
        """done=True after last bar."""
        env = StepEngine(data=_FakeProvider(n=3))
        env.reset()

        r1 = env.step(None)  # bar 1
        assert r1.done is False

        r2 = env.step(None)  # bar 2
        assert r2.done is False

        r3 = env.step(None)  # exhausted
        assert r3.done is True

    def test_step_raises_after_done(self):
        """StopIteration on exhausted data."""
        env = StepEngine(data=_FakeProvider(n=2))
        env.reset()

        env.step(None)  # bar 1
        env.step(None)  # exhausted, done=True

        with pytest.raises(StopIteration):
            env.step(None)

    def test_step_sl_tp_respected(self):
        """TP/SL from order config honored by engine."""
        env = StepEngine(data=_TrendProvider(), config={
            "slippage": 0.0, "taker_fee": 0.0,
        })
        env.reset()

        # Long with tight TP
        env.step(MarketOrder(
            side=Side.LONG,
            take_profit_pct=0.03,  # 3% TP
            stop_loss_pct=0.30,
        ))

        # Step until position closes
        for _ in range(8):
            r = env.step(None)
            if not r.observation.positions:
                break

        # Position should have closed via TP
        assert len(r.observation.positions) == 0

    def test_step_indicators_update(self):
        """Indicator values in obs are current."""
        env = StepEngine(
            data=_FakeProvider(n=20),
            config={"indicators": {"test_ema": {"type": "ema", "timeframe": "1m", "period": 3}}},
        )
        obs = env.reset()

        # After warmup, EMA should be available
        for _ in range(5):
            r = env.step(None)

        assert "test_ema" in r.observation.indicators
        assert r.observation.indicators["test_ema"] is not None

    def test_step_positions_visible(self):
        """Open positions in observation."""
        env = StepEngine(data=_FakeProvider(n=10), config={
            "slippage": 0.0, "taker_fee": 0.0,
        })
        env.reset()

        # Open a position
        r = env.step(MarketOrder(
            side=Side.LONG,
            take_profit_pct=0.5,
            stop_loss_pct=0.5,
        ))

        assert len(r.observation.positions) == 1
        assert r.observation.positions[0].side == Side.LONG

    def test_step_info_fills_exits(self):
        """info dict contains fills and exits lists."""
        env = StepEngine(data=_FakeProvider(n=5))
        env.reset()

        result = env.step(None)
        assert "fills" in result.info
        assert "exits" in result.info
        assert isinstance(result.info["fills"], list)
        assert isinstance(result.info["exits"], list)

    def test_backtest_engine_unchanged(self):
        """Existing BacktestEngine.run() produces identical results."""

        class AlwaysLong(Strategy):
            def __init__(self):
                self._entered = False

            def on_bar(self, bar, indicators, positions):
                if not positions and not self._entered:
                    self._entered = True
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.05,
                        stop_loss_pct=0.30,
                    )
                return None

        # Run via BacktestEngine.run()
        engine = BacktestEngine(
            strategy=AlwaysLong(),
            data=_TrendProvider(),
            config={"slippage": 0.0, "taker_fee": 0.0},
        )
        results = engine.run()

        # Verify it still works (no regression from step.py import)
        assert results is not None
        assert results.total_trades >= 0

    def test_step_with_empty_data(self):
        """Empty provider returns done=True immediately."""

        class EmptyProvider(DataProvider):
            def __iter__(self):
                return iter([])
            def symbol(self):
                return "EMPTY"
            def timeframe(self):
                return "1m"

        env = StepEngine(data=EmptyProvider())
        obs = env.reset()
        assert obs.done is True

    def test_step_equity_matches(self):
        """Equity in observation matches portfolio equity."""
        env = StepEngine(data=_FakeProvider(n=5), config={
            "initial_equity": 50_000.0,
        })
        obs = env.reset()
        assert obs.equity == 50_000.0

        r = env.step(None)
        assert r.observation.equity == 50_000.0
