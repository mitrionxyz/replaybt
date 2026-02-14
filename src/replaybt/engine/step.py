"""Step Mode: Gym-like step interface for RL agents.

Wraps BacktestEngine with a proxy strategy pattern. Zero changes to
BacktestEngine — the proxy's on_bar() always returns None, and the
agent controls entries exclusively via step(action).

Usage:
    env = StepEngine(data=CSVProvider('ETH_1m.csv'), config={...})
    obs = env.reset()
    while not obs.done:
        action = agent.decide(obs)  # MarketOrder, LimitOrder, or None
        result = env.step(action)
        obs = result.observation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from ..data.types import Bar, Fill, Position, Trade, Side
from ..data.providers.base import DataProvider
from ..strategy.base import Strategy
from .loop import BacktestEngine
from .orders import Order, MarketOrder, LimitOrder, CancelPendingLimitsOrder


@dataclass(frozen=True)
class StepObservation:
    """What the agent sees after each step."""
    bar: Bar
    indicators: Dict[str, Any]
    positions: List[Position]
    equity: float
    step_count: int
    done: bool


@dataclass(frozen=True)
class StepResult:
    """Returned from step(): observation + reward + metadata."""
    observation: StepObservation
    reward: float
    done: bool
    info: Dict[str, Any]


class _ProxyStrategy(Strategy):
    """Internal: always returns None from on_bar (agent controls via step).
    Delegates on_fill/on_exit/check_exits to optional inner strategy."""

    def __init__(self, inner: Optional[Strategy] = None):
        self._inner = inner

    def on_bar(self, bar, indicators, positions):
        return None

    def on_fill(self, fill):
        return self._inner.on_fill(fill) if self._inner else None

    def on_exit(self, fill, trade):
        return self._inner.on_exit(fill, trade) if self._inner else None

    def check_exits(self, bar, positions):
        return self._inner.check_exits(bar, positions) if self._inner else []

    def configure(self, config):
        if self._inner:
            self._inner.configure(config)


class StepEngine:
    """Gym-like step interface for RL agents. Wraps BacktestEngine.

    The proxy strategy's on_bar() always returns None. The agent
    controls entries exclusively via step(action). Exit management
    (SL/TP/breakeven) is handled by the engine as normal.

    Args:
        data: DataProvider yielding bars.
        config: Engine configuration dict (same as BacktestEngine).
        strategy: Optional inner strategy for on_fill/on_exit/check_exits
            delegation (e.g. engine-managed exits while agent controls entries).
    """

    def __init__(
        self,
        data: DataProvider,
        config: Optional[Dict] = None,
        strategy: Optional[Strategy] = None,
    ):
        self._data = data
        self._config = config or {}
        self._proxy = _ProxyStrategy(strategy)
        self._engine = BacktestEngine(
            strategy=self._proxy, data=data, config=self._config,
        )
        self._data_iter = None
        self._step_count = 0
        self._done = False
        self._prev_equity = self._engine.portfolio.initial_equity
        self._current_bar: Optional[Bar] = None

    def reset(self) -> StepObservation:
        """Reset engine state and advance to first bar.

        Returns:
            Initial observation with bar 0's data.
        """
        self._engine.portfolio.reset()
        self._engine.indicators.reset()
        self._engine._pending_order = None
        self._engine._pending_limits.clear()
        self._engine._bar_count = 0
        self._engine._first_bar = None
        self._engine._last_bar = None

        self._data.reset()
        self._data_iter = iter(self._data)
        self._step_count = 0
        self._done = False
        self._prev_equity = self._engine.portfolio.initial_equity

        # Advance to first bar
        try:
            bar = next(self._data_iter)
        except StopIteration:
            self._done = True
            dummy = Bar(
                timestamp=__import__('datetime').datetime.min,
                open=0, high=0, low=0, close=0, volume=0,
            )
            return StepObservation(
                bar=dummy, indicators={}, positions=[],
                equity=self._engine.portfolio.equity,
                step_count=0, done=True,
            )

        self._current_bar = bar
        self._engine._first_bar = bar
        self._engine._last_bar = bar

        # Seed indicators with the first bar
        self._engine.indicators.update(bar)

        return StepObservation(
            bar=bar,
            indicators=self._engine.indicators.values(),
            positions=list(self._engine.portfolio.positions),
            equity=self._engine.portfolio.equity,
            step_count=0,
            done=False,
        )

    def step(
        self, action: Optional[Union[Order, MarketOrder, LimitOrder]] = None,
    ) -> StepResult:
        """Advance one bar and apply the agent's action.

        Args:
            action: MarketOrder, LimitOrder, or None.
                MarketOrder → set as pending, fills at next bar's open.
                LimitOrder → appended to pending limits.
                None → no order.

        Returns:
            StepResult with observation, reward, done flag, and info.

        Raises:
            StopIteration: If called after data is exhausted.
        """
        if self._done:
            raise StopIteration("Data exhausted. Call reset() to start over.")

        # Inject action into engine state
        if action is not None:
            if isinstance(action, LimitOrder):
                from .loop import _PendingLimit
                self._engine._pending_limits.append(_PendingLimit(order=action))
            elif isinstance(action, (Order, MarketOrder)):
                self._engine._pending_order = action

        # Snapshot fill/trade counts before processing
        fills_before = len(self._engine.portfolio.fills)
        trades_before = len(self._engine.portfolio.trades)

        # Advance to next bar
        try:
            bar = next(self._data_iter)
        except StopIteration:
            self._done = True
            equity = self._engine.portfolio.equity
            reward = equity - self._prev_equity
            self._prev_equity = equity
            self._step_count += 1
            return StepResult(
                observation=StepObservation(
                    bar=self._current_bar,
                    indicators=self._engine.indicators.values(),
                    positions=list(self._engine.portfolio.positions),
                    equity=equity,
                    step_count=self._step_count,
                    done=True,
                ),
                reward=reward,
                done=True,
                info={"fills": [], "exits": []},
            )

        self._current_bar = bar
        self._engine._last_bar = bar

        # Run the 4-phase loop on this bar
        # Phase 1-3 execute pending orders and check exits
        # Phase 4 calls proxy.on_bar() which returns None
        self._engine._process_bar(bar)

        # Collect new fills and exits
        new_fills = self._engine.portfolio.fills[fills_before:]
        new_trades = self._engine.portfolio.trades[trades_before:]

        equity = self._engine.portfolio.equity
        reward = equity - self._prev_equity
        self._prev_equity = equity
        self._step_count += 1

        return StepResult(
            observation=StepObservation(
                bar=bar,
                indicators=self._engine.indicators.values(),
                positions=list(self._engine.portfolio.positions),
                equity=equity,
                step_count=self._step_count,
                done=False,
            ),
            reward=reward,
            done=False,
            info={
                "fills": list(new_fills),
                "exits": list(new_trades),
            },
        )
