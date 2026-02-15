"""Rolling walk-forward optimization.

Splits data into sequential train/test windows, optimizes parameters
on each training period, then validates on the out-of-sample test period.
Produces aggregate OOS metrics across all windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type

from ..data.providers.base import DataProvider
from ..data.types import Bar, Trade
from ..engine.loop import BacktestEngine
from ..optimize.sweep import ParameterSweep, _ListProvider
from ..reporting.metrics import BacktestResults
from ..strategy.base import Strategy


@dataclass(frozen=True)
class WindowResult:
    """Results from a single walk-forward window."""

    window_index: int
    train_start_idx: int
    train_end_idx: int
    test_start_idx: int
    test_end_idx: int
    best_params: dict
    train_metrics: dict
    test_result: BacktestResults
    all_combos: int


@dataclass
class WalkForwardResult:
    """Aggregate results from all walk-forward windows."""

    windows: List[WindowResult] = field(default_factory=list)
    n_windows: int = 0
    anchored: bool = False
    train_pct: float = 0.60
    metric: str = "net_pnl"

    # Aggregated OOS
    oos_net_pnl: float = 0.0
    oos_total_trades: int = 0
    oos_win_rate: float = 0.0
    oos_max_drawdown_pct: float = 0.0

    # Stability
    param_stability: Dict[str, List] = field(default_factory=dict)

    @property
    def params_consistent(self) -> bool:
        """True if the same params were selected in >50% of windows."""
        if not self.windows:
            return True
        n = len(self.windows)
        for values in self.param_stability.values():
            from collections import Counter

            most_common_count = Counter(
                str(v) for v in values
            ).most_common(1)[0][1]
            if most_common_count <= n / 2:
                return False
        return True

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"{'='*60}",
            f"  Walk-Forward Optimization ({self.n_windows} windows"
            f"{', anchored' if self.anchored else ', sliding'})",
            f"{'='*60}",
            f"  Metric:           {self.metric}",
            f"  Train/Test:       {self.train_pct:.0%} / {1-self.train_pct:.0%}",
            f"  OOS Net PnL:      ${self.oos_net_pnl:,.2f}",
            f"  OOS Trades:       {self.oos_total_trades}",
            f"  OOS Win Rate:     {self.oos_win_rate:.1f}%",
            f"  OOS Max DD:       {self.oos_max_drawdown_pct:.1f}%",
            f"  Params Consistent: {'Yes' if self.params_consistent else 'No'}",
            f"  {'─'*56}",
            f"  Per-Window:",
        ]

        for w in self.windows:
            test_pnl = w.test_result.net_pnl
            test_trades = w.test_result.total_trades
            lines.append(
                f"    W{w.window_index}: "
                f"train[{w.train_start_idx}:{w.train_end_idx}] "
                f"test[{w.test_start_idx}:{w.test_end_idx}] "
                f"PnL=${test_pnl:+,.0f} ({test_trades} trades) "
                f"params={w.best_params}"
            )

        if self.param_stability:
            lines.append(f"  {'─'*56}")
            lines.append(f"  Param Stability:")
            for param, values in sorted(self.param_stability.items()):
                lines.append(f"    {param}: {values}")

        lines.append(f"{'='*60}")
        return "\n".join(lines)


class WalkForward:
    """Rolling walk-forward optimization.

    Splits data into ``n_windows`` sequential test periods. For each window,
    runs a parameter sweep on the training data, selects the best combo
    by ``metric``, then runs a fresh backtest on the test data.

    Usage::

        wf = WalkForward(
            strategy_class=MyStrategy,
            data=CSVProvider('ETH_1m.csv'),
            base_config={'initial_equity': 10000},
            param_grid={'tp_pct': [0.04, 0.06, 0.08]},
            n_windows=5,
        )
        result = wf.run()
        print(result.summary())

    Args:
        strategy_class: Strategy subclass (not instance).
        data: DataProvider with bar data.
        base_config: Base engine config dict.
        param_grid: Dict of param_name -> list of values to sweep.
        n_windows: Number of walk-forward windows.
        train_pct: Fraction of each window used for training (0-1).
        anchored: If True, training always starts at bar 0.
        metric: Metric to optimize (key in sweep combo dicts).
        n_workers: Number of parallel workers for sweep.
    """

    def __init__(
        self,
        strategy_class: Type[Strategy],
        data: DataProvider,
        base_config: dict,
        param_grid: Dict[str, list],
        n_windows: int = 5,
        train_pct: float = 0.60,
        anchored: bool = False,
        metric: str = "net_pnl",
        n_workers: Optional[int] = None,
    ):
        self._strategy_class = strategy_class
        self._data = data
        self._base_config = base_config
        self._param_grid = param_grid
        self._n_windows = n_windows
        self._train_pct = train_pct
        self._anchored = anchored
        self._metric = metric
        self._n_workers = n_workers

    def run(self) -> WalkForwardResult:
        """Execute walk-forward optimization across all windows."""
        bars = list(self._data)
        symbol = self._data.symbol()
        timeframe = self._data.timeframe()
        n_bars = len(bars)

        step = n_bars // self._n_windows
        if step == 0:
            raise ValueError(
                f"Not enough bars ({n_bars}) for {self._n_windows} windows"
            )

        windows: List[WindowResult] = []

        for i in range(self._n_windows):
            test_start = i * step
            test_end = (i + 1) * step if i < self._n_windows - 1 else n_bars

            if self._anchored:
                train_start = 0
                train_end = test_start
            else:
                train_length = int(step * self._train_pct / (1 - self._train_pct))
                train_start = max(0, test_start - train_length)
                train_end = test_start

            # Skip windows with no training data
            if train_end <= train_start:
                continue

            train_bars = bars[train_start:train_end]
            test_bars = bars[test_start:test_end]

            # Run parameter sweep on training data
            train_provider = _ListProvider(train_bars, symbol, timeframe)
            sweep = ParameterSweep(
                strategy_class=self._strategy_class,
                data=train_provider,
                base_config=self._base_config,
                param_grid=self._param_grid,
                n_workers=self._n_workers,
            )
            sweep_results = sweep.run()

            # Pick best combo
            best_list = sweep_results.best(metric=self._metric, n=1)
            if not best_list:
                continue
            best_combo = best_list[0]

            # Extract only the swept param keys
            metric_keys = {
                "net_pnl", "net_return_pct", "max_drawdown_pct",
                "total_trades", "win_rate", "profit_factor",
                "total_fees", "avg_win", "avg_loss",
            }
            best_params = {
                k: v for k, v in best_combo.items() if k not in metric_keys
            }
            train_metrics = {
                k: v for k, v in best_combo.items() if k in metric_keys
            }

            # Run fresh backtest on test data with best params
            test_config = {**self._base_config, **best_params}
            test_provider = _ListProvider(test_bars, symbol, timeframe)
            strategy = self._strategy_class()
            engine = BacktestEngine(
                strategy=strategy,
                data=test_provider,
                config=test_config,
            )
            test_result = engine.run()

            windows.append(
                WindowResult(
                    window_index=i,
                    train_start_idx=train_start,
                    train_end_idx=train_end,
                    test_start_idx=test_start,
                    test_end_idx=test_end,
                    best_params=best_params,
                    train_metrics=train_metrics,
                    test_result=test_result,
                    all_combos=len(sweep_results),
                )
            )

        # Aggregate OOS metrics
        oos_pnl = sum(w.test_result.net_pnl for w in windows)
        oos_trades: List[Trade] = []
        for w in windows:
            oos_trades.extend(w.test_result.trades)
        oos_total = len(oos_trades)
        oos_wins = sum(1 for t in oos_trades if t.pnl_usd > 0)

        # Continuous OOS equity curve for max DD
        oos_dd = 0.0
        if windows:
            equity = self._base_config.get("initial_equity", 10_000.0)
            peak = equity
            for w in windows:
                for trade in w.test_result.trades:
                    equity += trade.pnl_usd
                    peak = max(peak, equity)
                    dd = (peak - equity) / peak if peak > 0 else 0.0
                    oos_dd = max(oos_dd, dd)

        # Param stability
        param_stability: Dict[str, List] = {}
        if windows:
            param_keys = list(windows[0].best_params.keys())
            for key in param_keys:
                param_stability[key] = [w.best_params.get(key) for w in windows]

        return WalkForwardResult(
            windows=windows,
            n_windows=len(windows),
            anchored=self._anchored,
            train_pct=self._train_pct,
            metric=self._metric,
            oos_net_pnl=oos_pnl,
            oos_total_trades=oos_total,
            oos_win_rate=(oos_wins / oos_total * 100) if oos_total else 0.0,
            oos_max_drawdown_pct=oos_dd * 100,
            param_stability=param_stability,
        )
