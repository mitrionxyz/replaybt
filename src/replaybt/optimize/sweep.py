"""Generic parallel parameter grid search using BacktestEngine."""

from __future__ import annotations

import itertools
from multiprocessing import Pool, cpu_count
from typing import Dict, List, Optional, Type

from ..data.providers.base import DataProvider
from ..data.types import Bar
from ..engine.loop import BacktestEngine
from ..strategy.base import Strategy
from .results import SweepResults


class _ListProvider(DataProvider):
    """Internal provider wrapping a pre-loaded list of bars."""

    def __init__(self, bars: List[Bar], sym: str, tf: str):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf


def _run_single_combo(args) -> dict:
    """Run one backtest combo. Module-level for multiprocessing pickling."""
    strategy_class, bars, symbol, timeframe, base_config, params = args

    config = {**base_config, **params}

    provider = _ListProvider(bars, symbol, timeframe)
    strategy = strategy_class()
    engine = BacktestEngine(strategy=strategy, data=provider, config=config)
    results = engine.run()

    return {
        **params,
        "net_pnl": results.net_pnl,
        "net_return_pct": results.net_return_pct,
        "max_drawdown_pct": results.max_drawdown_pct,
        "total_trades": results.total_trades,
        "win_rate": results.win_rate,
        "profit_factor": results.profit_factor,
        "total_fees": results.total_fees,
        "avg_win": results.avg_win,
        "avg_loss": results.avg_loss,
    }


class ParameterSweep:
    """Parallel parameter grid search.

    Runs BacktestEngine for each parameter combination in parallel
    using multiprocessing. Strategies read swept params from config
    via configure().

    Usage:
        sweep = ParameterSweep(
            strategy_class=MyStrategy,
            data=CSVProvider('ETH_1m.csv'),
            base_config={'initial_equity': 10000},
            param_grid={
                'take_profit_pct': [0.04, 0.06, 0.08],
                'stop_loss_pct': [0.02, 0.03, 0.035],
            },
            n_workers=10,
        )
        results = sweep.run()
        print(results.summary())

    Args:
        strategy_class: Strategy subclass (not instance).
        data: DataProvider with bar data.
        base_config: Base engine config dict.
        param_grid: Dict of param_name -> list of values to sweep.
        n_workers: Number of parallel workers (default: cpu_count).
    """

    def __init__(
        self,
        strategy_class: Type[Strategy],
        data: DataProvider,
        base_config: dict,
        param_grid: Dict[str, list],
        n_workers: Optional[int] = None,
    ):
        self._strategy_class = strategy_class
        self._data = data
        self._base_config = base_config
        self._param_grid = param_grid
        self._n_workers = n_workers

    def _build_combos(self) -> List[dict]:
        """Build all parameter combinations from the grid."""
        keys = sorted(self._param_grid.keys())
        values = [self._param_grid[k] for k in keys]
        return [
            dict(zip(keys, combo))
            for combo in itertools.product(*values)
        ]

    def run(self) -> SweepResults:
        """Run all combos in parallel. Returns SweepResults."""
        bars = list(self._data)
        symbol = self._data.symbol()
        timeframe = self._data.timeframe()

        combos = self._build_combos()

        worker_args = [
            (
                self._strategy_class, bars, symbol, timeframe,
                self._base_config, combo,
            )
            for combo in combos
        ]

        n = self._n_workers or cpu_count()

        if n == 1:
            # Single-worker: skip multiprocessing overhead
            raw_results = [_run_single_combo(a) for a in worker_args]
        else:
            with Pool(n) as pool:
                raw_results = pool.map(_run_single_combo, worker_args)

        return SweepResults(combos=raw_results)
