# Analysis

## MonteCarlo

Monte Carlo simulation for robustness analysis. Runs shuffle (permutation) and bootstrap (resampling) simulations on completed trade results.

```python
from replaybt import MonteCarlo

mc = MonteCarlo(results=backtest_results, n_simulations=1000)
mc_result = mc.run()
print(mc_result.summary())
```

### Constructor

```python
MonteCarlo(
    results: BacktestResults,
    n_simulations: int = 1000,
)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `MonteCarloResult` | Execute simulations |

### MonteCarloResult

| Field | Type | Description |
|-------|------|-------------|
| `n_simulations` | `int` | Simulations run |
| `n_trades` | `int` | Trades in source |
| `initial_equity` | `float` | Starting equity |
| `shuffle_pnl_percentiles` | `Dict[int, float]` | PnL at 5/25/50/75/95th pct |
| `shuffle_max_dd_mean` | `float` | Avg max drawdown |
| `shuffle_max_dd_percentiles` | `Dict[int, float]` | DD at 5/50/95th pct |
| `bootstrap_pnl_mean` | `float` | Expected PnL |
| `bootstrap_pnl_std` | `float` | PnL std deviation |
| `bootstrap_pnl_percentiles` | `Dict[int, float]` | PnL at 5/25/50/75/95th pct |
| `bootstrap_max_dd_mean` | `float` | Avg max drawdown |
| `bootstrap_max_dd_percentiles` | `Dict[int, float]` | DD at 5/50/95th pct |
| `ruin_probability` | `float` | Probability of total loss |

| Method | Returns | Description |
|--------|---------|-------------|
| `summary()` | `str` | Formatted report |

---

## WalkForward

Rolling walk-forward optimization. Trains on one window, tests on the next, repeats.

```python
from replaybt import WalkForward

wf = WalkForward(
    strategy_class=MyStrategy,
    data=data_provider,
    base_config=config,
    param_grid=grid,
    n_windows=4,
    train_pct=0.60,
    metric="net_pnl",
    anchored=False,
)
result = wf.run()
print(result.summary())
```

### Constructor

```python
WalkForward(
    strategy_class: Type[Strategy],
    data: DataProvider,
    base_config: dict,
    param_grid: Dict[str, list],
    n_windows: int = 4,
    train_pct: float = 0.60,
    metric: str = "net_pnl",
    anchored: bool = False,
    n_workers: Optional[int] = None,
)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `WalkForwardResult` | Execute walk-forward |

### WalkForwardResult

| Field | Type | Description |
|-------|------|-------------|
| `windows` | `List[WindowResult]` | Per-window results |
| `n_windows` | `int` | Number of windows |
| `anchored` | `bool` | Anchored mode |
| `train_pct` | `float` | Train fraction |
| `metric` | `str` | Optimization metric |
| `oos_net_pnl` | `float` | Combined OOS PnL |
| `oos_total_trades` | `int` | Combined OOS trades |
| `oos_win_rate` | `float` | Combined OOS win rate |
| `oos_max_drawdown_pct` | `float` | Combined OOS drawdown |
| `param_stability` | `Dict[str, List]` | Params per window |

| Property | Type | Description |
|----------|------|-------------|
| `params_consistent` | `bool` | Same params >50% of windows |

| Method | Returns | Description |
|--------|---------|-------------|
| `summary()` | `str` | Formatted report |

### WindowResult

| Field | Type | Description |
|-------|------|-------------|
| `window_index` | `int` | Window number |
| `train_start_idx` | `int` | Train start index |
| `train_end_idx` | `int` | Train end index |
| `test_start_idx` | `int` | Test start index |
| `test_end_idx` | `int` | Test end index |
| `best_params` | `dict` | Best params from train |
| `train_metrics` | `dict` | Training metrics |
| `test_result` | `BacktestResults` | OOS test results |
| `all_combos` | `int` | Combos evaluated |
