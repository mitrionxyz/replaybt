"""Runtime stress tests: signal delay and out-of-sample split."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

from ..data.providers.base import DataProvider
from ..data.types import Bar, Fill, Position, Trade
from ..engine.loop import BacktestEngine
from ..engine.orders import Order, CancelPendingLimitsOrder
from ..reporting.metrics import BacktestResults
from ..strategy.base import Strategy


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

class _ListProvider(DataProvider):
    """Internal provider wrapping a pre-loaded list of bars."""

    def __init__(self, bars: List[Bar], sym: str = "", tf: str = "1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf


class _DelayedStrategy(Strategy):
    """Wrapper that queues on_bar signals by N bars."""

    def __init__(self, inner: Strategy, delay: int = 1):
        self._inner = inner
        self._delay = delay
        self._queue: deque = deque()

    def configure(self, config: dict) -> None:
        self._inner.configure(config)

    def on_bar(
        self,
        bar: Bar,
        indicators: Dict[str, Any],
        positions: List[Position],
    ) -> Union[None, Order, List[Order]]:
        signal = self._inner.on_bar(bar, indicators, positions)
        self._queue.append(signal)
        if len(self._queue) > self._delay:
            return self._queue.popleft()
        return None

    def on_fill(self, fill: Fill) -> Optional[Order]:
        return self._inner.on_fill(fill)

    def on_exit(
        self, fill: Fill, trade: Trade,
    ) -> Union[None, Order, CancelPendingLimitsOrder]:
        return self._inner.on_exit(fill, trade)

    def check_exits(self, bar: Bar, positions: List[Position]) -> List:
        return self._inner.check_exits(bar, positions)

    def warmup_periods(self) -> Dict[str, int]:
        return self._inner.warmup_periods()


# ------------------------------------------------------------------
# DelayTest
# ------------------------------------------------------------------

@dataclass(frozen=True)
class DelayTestResult:
    """Result of a +N bar delay stress test."""
    normal: BacktestResults
    delayed: BacktestResults
    delay_bars: int
    pnl_change_pct: float
    wr_change: float
    verdict: str  # "PASS" or "FAIL"


class DelayTest:
    """Run backtest with +N bar delay on signals.

    If PnL drops more than ``fail_threshold`` (default 50%) with +1 bar
    delay, the strategy is likely latency-sensitive or has look-ahead bias.

    Args:
        strategy_factory: Callable returning a fresh Strategy instance.
        data: DataProvider (bars will be pre-loaded and replayed twice).
        config: Engine config dict.
        delay_bars: How many extra bars to delay signals (default 1).
        fail_threshold: Max allowed PnL drop fraction (default 0.5 = 50%).
    """

    def __init__(
        self,
        strategy_factory: Callable[[], Strategy],
        data: DataProvider,
        config: Optional[dict] = None,
        delay_bars: int = 1,
        fail_threshold: float = 0.5,
    ):
        self._factory = strategy_factory
        self._data = data
        self._config = config or {}
        self._delay = delay_bars
        self._fail_threshold = fail_threshold

    def run(self) -> DelayTestResult:
        """Run normal + delayed backtests and compare."""
        bars = list(self._data)
        symbol = self._data.symbol()
        tf = self._data.timeframe()

        # Normal run
        provider_a = _ListProvider(bars, symbol, tf)
        engine_a = BacktestEngine(
            strategy=self._factory(),
            data=provider_a,
            config=self._config,
        )
        normal = engine_a.run()

        # Delayed run
        provider_b = _ListProvider(bars, symbol, tf)
        delayed_strat = _DelayedStrategy(self._factory(), self._delay)
        engine_b = BacktestEngine(
            strategy=delayed_strat,
            data=provider_b,
            config=self._config,
        )
        delayed = engine_b.run()

        # Compare
        if abs(normal.net_pnl) < 1e-9:
            pnl_change = 0.0
        else:
            pnl_change = (
                (delayed.net_pnl - normal.net_pnl) / abs(normal.net_pnl)
            )

        wr_change = delayed.win_rate - normal.win_rate

        if abs(pnl_change) > self._fail_threshold:
            verdict = "FAIL"
        else:
            verdict = "PASS"

        return DelayTestResult(
            normal=normal,
            delayed=delayed,
            delay_bars=self._delay,
            pnl_change_pct=pnl_change * 100,
            wr_change=wr_change,
            verdict=verdict,
        )


# ------------------------------------------------------------------
# OOSSplit
# ------------------------------------------------------------------

@dataclass(frozen=True)
class OOSResult:
    """Result of an out-of-sample split test."""
    train: BacktestResults
    test: BacktestResults
    split_ratio: float
    wr_divergence: float
    pnl_ratio: float
    verdict: str  # "PASS" or "FAIL"


class OOSSplit:
    """Run backtest on train/test split.

    Splits data at the given ratio (default 50/50). If win rate diverges
    more than ``wr_threshold`` percentage points or test PnL (adjusted
    for period length) is below ``pnl_threshold`` of train PnL, FAIL.

    Args:
        strategy_factory: Callable returning a fresh Strategy instance.
        data: DataProvider (bars will be pre-loaded and split).
        config: Engine config dict.
        split_ratio: Fraction of bars for training (default 0.5).
        wr_threshold: Max allowed win-rate divergence in pp (default 10).
        pnl_threshold: Min test/train PnL ratio, length-adjusted (default 0.25).
    """

    def __init__(
        self,
        strategy_factory: Callable[[], Strategy],
        data: DataProvider,
        config: Optional[dict] = None,
        split_ratio: float = 0.5,
        wr_threshold: float = 10.0,
        pnl_threshold: float = 0.25,
    ):
        self._factory = strategy_factory
        self._data = data
        self._config = config or {}
        self._split_ratio = split_ratio
        self._wr_threshold = wr_threshold
        self._pnl_threshold = pnl_threshold

    def run(self) -> OOSResult:
        """Run train + test backtests and compare."""
        bars = list(self._data)
        symbol = self._data.symbol()
        tf = self._data.timeframe()

        split_idx = int(len(bars) * self._split_ratio)
        train_bars = bars[:split_idx]
        test_bars = bars[split_idx:]

        # Train
        provider_train = _ListProvider(train_bars, symbol, tf)
        engine_train = BacktestEngine(
            strategy=self._factory(),
            data=provider_train,
            config=self._config,
        )
        train_result = engine_train.run()

        # Test
        provider_test = _ListProvider(test_bars, symbol, tf)
        engine_test = BacktestEngine(
            strategy=self._factory(),
            data=provider_test,
            config=self._config,
        )
        test_result = engine_test.run()

        # Compare
        wr_div = abs(train_result.win_rate - test_result.win_rate)

        # Length-adjusted PnL ratio: normalize test PnL to same length as train
        if abs(train_result.net_pnl) < 1e-9:
            pnl_ratio = 0.0 if abs(test_result.net_pnl) < 1e-9 else float("inf")
        else:
            # Adjust for different period lengths
            if len(test_bars) > 0 and len(train_bars) > 0:
                length_factor = len(train_bars) / len(test_bars)
            else:
                length_factor = 1.0
            pnl_ratio = (test_result.net_pnl * length_factor) / abs(
                train_result.net_pnl
            )

        # Verdict
        wr_fail = wr_div > self._wr_threshold
        pnl_fail = pnl_ratio < self._pnl_threshold
        verdict = "FAIL" if (wr_fail or pnl_fail) else "PASS"

        return OOSResult(
            train=train_result,
            test=test_result,
            split_ratio=self._split_ratio,
            wr_divergence=wr_div,
            pnl_ratio=pnl_ratio,
            verdict=verdict,
        )
