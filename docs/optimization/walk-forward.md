# Walk-Forward

Rolling walk-forward optimization: optimize parameters on a training window, then test on the next out-of-sample window. Repeat across the dataset.

## Complete Example

```python
from replaybt import CSVProvider, Strategy, MarketOrder, Side
from replaybt import WalkForward


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


wf = WalkForward(
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
        "take_profit_pct": [0.04, 0.06, 0.08],
        "stop_loss_pct": [0.02, 0.03, 0.04],
    },
    n_windows=4,       # number of train/test windows
    train_pct=0.60,    # 60% train, 40% test per window
    metric="net_pnl",  # optimize for net PnL
    anchored=False,    # sliding windows (vs anchored)
)

result = wf.run()
print(result.summary())
```

## Parameters

```python
WalkForward(
    strategy_class=MyStrategy,
    data=data_provider,
    base_config=config_dict,
    param_grid=param_dict,
    n_windows=4,          # number of train/test windows
    train_pct=0.60,       # train fraction per window
    metric="net_pnl",     # metric to optimize on train
    anchored=False,       # False=sliding, True=anchored
    n_workers=10,         # parallel workers for sweep
)
```

## Sliding vs Anchored

**Sliding** (default): each window is a fixed-size slice that moves forward.

```
Window 1: [====TRAIN====][==TEST==]
Window 2:       [====TRAIN====][==TEST==]
Window 3:             [====TRAIN====][==TEST==]
```

**Anchored**: training always starts from the beginning, growing larger.

```
Window 1: [====TRAIN====][==TEST==]
Window 2: [========TRAIN========][==TEST==]
Window 3: [============TRAIN============][==TEST==]
```

## WalkForwardResult

```python
result = wf.run()

# Aggregate OOS metrics
result.oos_net_pnl           # combined OOS PnL
result.oos_total_trades      # combined OOS trades
result.oos_win_rate          # combined OOS win rate
result.oos_max_drawdown_pct  # combined OOS max drawdown

# Parameter stability
result.param_stability       # {param_name: [values per window]}
result.params_consistent     # True if same params chosen >50% of windows

# Per-window details
for w in result.windows:
    print(f"Window {w.window_index}: "
          f"train PnL=${w.train_metrics['net_pnl']:,.0f}, "
          f"test PnL=${w.test_result.net_pnl:,.0f}, "
          f"params={w.best_params}")
```

## Interpreting Results

- **params_consistent = True**: the same parameters keep winning across windows. Good sign.
- **params_consistent = False**: optimal parameters change every window. Likely overfitting.
- **OOS PnL negative**: the strategy doesn't generalize. Reconsider the approach.
