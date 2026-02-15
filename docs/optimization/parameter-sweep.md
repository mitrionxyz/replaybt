# Parameter Sweep

Parallel grid search across parameter combinations using multiprocessing.

## Complete Example

```python
from replaybt import CSVProvider, Strategy, MarketOrder, Side
from replaybt.optimize.sweep import ParameterSweep


class EMACrossover(Strategy):
    def configure(self, config):
        self._prev_fast = self._prev_slow = None

    def on_bar(self, bar, indicators, positions):
        fast = indicators.get("ema_fast")
        slow = indicators.get("ema_slow")
        if fast is None or slow is None or self._prev_fast is None:
            self._prev_fast, self._prev_slow = fast, slow
            return None

        crossed_up = fast > slow and self._prev_fast <= self._prev_slow
        self._prev_fast, self._prev_slow = fast, slow

        if not positions and crossed_up:
            return MarketOrder(side=Side.LONG)
        return None


sweep = ParameterSweep(
    strategy_class=EMACrossover,
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    base_config={
        "initial_equity": 10_000,
        "indicators": {
            "ema_fast": {"type": "ema", "period": 5, "source": "close"},
            "ema_slow": {"type": "ema", "period": 10, "source": "close"},
        },
    },
    param_grid={
        "take_profit_pct": [0.02, 0.04, 0.06, 0.08, 0.10],
        "stop_loss_pct": [0.01, 0.02, 0.03, 0.04],
    },
    n_workers=10,
)

results = sweep.run()
print(results.summary(top_n=10))
```

## Parameters

```python
ParameterSweep(
    strategy_class=MyStrategy,    # Strategy CLASS (not instance)
    data=data_provider,           # DataProvider instance
    base_config=config_dict,      # base engine config
    param_grid={                  # parameters to sweep
        "take_profit_pct": [0.04, 0.06, 0.08],
        "stop_loss_pct": [0.02, 0.03, 0.04],
    },
    n_workers=10,                 # parallel workers (default: cpu_count)
)
```

The sweep evaluates every combination of parameter values. With 5 TP values and 4 SL values, that's 20 combinations evaluated in parallel.

## SweepResults

### Top/Bottom Results

```python
results = sweep.run()

# Top 10 by net PnL
best = results.best("net_pnl", n=10)
for combo in best:
    print(f"TP={combo['take_profit_pct']}, SL={combo['stop_loss_pct']} → ${combo['net_pnl']:,.0f}")

# Bottom 5
worst = results.worst("net_pnl", n=5)
```

### Filter

```python
# Only combos where TP >= 0.06
filtered = results.filter(take_profit_pct=0.06)
print(filtered.summary())
```

### DataFrame Export

```python
df = results.to_dataframe()
print(df.sort_values("net_pnl", ascending=False).head(10))
```

### Available Metrics

Each combo dict includes:

| Key | Description |
|-----|-------------|
| `net_pnl` | Net profit/loss |
| `net_return_pct` | Return percentage |
| `max_drawdown_pct` | Maximum drawdown |
| `total_trades` | Number of trades |
| `win_rate` | Win rate percentage |
| `profit_factor` | Gross profit / gross loss |

Plus all parameter keys from `param_grid`.

## Formatted Summary

```python
print(results.summary(metric="net_pnl", top_n=20))
```

Prints a table of the top 20 combinations sorted by the specified metric.
