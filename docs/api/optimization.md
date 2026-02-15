# Optimization

## ParameterSweep

Parallel grid search using multiprocessing.

```python
from replaybt.optimize.sweep import ParameterSweep

sweep = ParameterSweep(
    strategy_class=MyStrategy,
    data=CSVProvider("ETH_1m.csv"),
    base_config={"initial_equity": 10_000},
    param_grid={
        "take_profit_pct": [0.04, 0.06, 0.08],
        "stop_loss_pct": [0.02, 0.03, 0.04],
    },
    n_workers=10,
)
results = sweep.run()
```

### Constructor

```python
ParameterSweep(
    strategy_class: Type[Strategy],
    data: DataProvider,
    base_config: dict,
    param_grid: Dict[str, list],
    n_workers: Optional[int] = None,   # default: cpu_count
)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `SweepResults` | Execute sweep |

---

## SweepResults

Ranked results from a parameter sweep.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `combos` | `List[dict]` | Each combo has params + metrics |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `best(metric, n)` | `List[dict]` | Top N by metric (descending) |
| `worst(metric, n)` | `List[dict]` | Bottom N by metric |
| `filter(**kwargs)` | `SweepResults` | Filter by param values |
| `to_dataframe()` | `pd.DataFrame` | Export as DataFrame |
| `summary(metric, top_n)` | `str` | Formatted summary table |

### Combo Keys

Each dict in `combos` contains all parameter keys from `param_grid` plus:

| Key | Type | Description |
|-----|------|-------------|
| `net_pnl` | `float` | Net PnL |
| `net_return_pct` | `float` | Return percentage |
| `max_drawdown_pct` | `float` | Max drawdown |
| `total_trades` | `int` | Trade count |
| `win_rate` | `float` | Win rate |
| `profit_factor` | `float` | Profit factor |
