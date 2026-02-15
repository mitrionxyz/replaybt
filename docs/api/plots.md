# Plots

Visualization functions for backtest results. Requires matplotlib:

```bash
pip install replaybt[plots]
```

All functions return a `matplotlib.figure.Figure`. Call `fig.savefig("plot.png")` to save.

```python
from replaybt.analysis.plots import plot_equity
```

---

## plot_equity

Equity curve with optional drawdown shading.

```python
fig = plot_equity(results, show_drawdown=True, figsize=(12, 6))
fig.savefig("equity.png")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `BacktestResults` | required | Results with equity curve |
| `show_drawdown` | `bool` | `True` | Shade drawdown regions |
| `figsize` | `Tuple[int, int]` | `(12, 6)` | Figure size |

---

## plot_drawdown

Drawdown as negative percentage filled area.

```python
fig = plot_drawdown(results, figsize=(12, 4))
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `BacktestResults` | required | Results with equity curve |
| `figsize` | `Tuple[int, int]` | `(12, 4)` | Figure size |

---

## plot_trades

Entry/exit markers, optionally on a price chart.

```python
fig = plot_trades(results, prices=price_list, figsize=(14, 6))
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `BacktestResults` | required | Results with trades |
| `prices` | `Optional[List[Tuple]]` | `None` | `(timestamp, price)` tuples for price line |
| `figsize` | `Tuple[int, int]` | `(14, 6)` | Figure size |

Markers: `^` = long entry, `v` = short entry, `x` = exit. Green = profit, red = loss.

---

## plot_monthly_heatmap

Monthly PnL as a Year x Month heatmap.

```python
fig = plot_monthly_heatmap(results, figsize=(10, 5))
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `BacktestResults` | required | Results with monthly data |
| `figsize` | `Tuple[int, int]` | `(10, 5)` | Figure size |

Green cells = profit, red cells = loss. Values annotated inside cells.

---

## plot_exit_breakdown

Exit reason breakdown as bar or pie chart.

```python
fig = plot_exit_breakdown(results, kind="bar", figsize=(8, 5))
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `BacktestResults` | required | Results with exit breakdown |
| `kind` | `str` | `"bar"` | `"bar"` or `"pie"` |
| `figsize` | `Tuple[int, int]` | `(8, 5)` | Figure size |

---

## plot_multi_equity

Per-symbol equity curves with optional combined portfolio overlay.

```python
fig = plot_multi_equity(multi_results, show_combined=True, figsize=(14, 7))
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `MultiAssetResults` | required | Multi-asset results |
| `show_combined` | `bool` | `True` | Show combined equity line |
| `figsize` | `Tuple[int, int]` | `(14, 7)` | Figure size |

---

## plot_sweep_heatmap

2D parameter sweep as a heatmap.

```python
fig = plot_sweep_heatmap(
    sweep_results,
    x_param="take_profit_pct",
    y_param="stop_loss_pct",
    metric="net_pnl",
    figsize=(10, 7),
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `results` | `SweepResults` | required | Sweep results |
| `x_param` | `str` | required | Parameter for x-axis |
| `y_param` | `str` | required | Parameter for y-axis |
| `metric` | `str` | `"net_pnl"` | Metric to display |
| `figsize` | `Tuple[int, int]` | `(10, 7)` | Figure size |
