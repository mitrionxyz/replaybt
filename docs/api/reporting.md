# Reporting

## BacktestResults

Complete backtest results with all metrics.

```python
results = engine.run()
print(results.summary())
print(results.monthly_table())
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | Asset symbol |
| `initial_equity` | `float` | Starting capital |
| `final_equity` | `float` | Ending capital |
| `net_pnl` | `float` | Net profit/loss |
| `net_return_pct` | `float` | Return percentage |
| `max_drawdown_pct` | `float` | Peak-to-trough drawdown |
| `total_trades` | `int` | Number of trades |
| `winning_trades` | `int` | Profitable trades |
| `losing_trades` | `int` | Unprofitable trades |
| `win_rate` | `float` | Win rate (0-100) |
| `avg_win` | `float` | Average win in USD |
| `avg_loss` | `float` | Average loss in USD (absolute) |
| `avg_win_pct` | `float` | Average win percent |
| `avg_loss_pct` | `float` | Average loss percent |
| `profit_factor` | `float` | Gross profit / gross loss |
| `total_fees` | `float` | Cumulative fees |
| `trades` | `List[Trade]` | All closed trades |
| `exit_breakdown` | `Dict[str, int]` | Count by exit reason |
| `equity_curve` | `List[Tuple[datetime, float]]` | Equity after each trade |
| `buy_hold_return_pct` | `Optional[float]` | Buy & hold return |
| `first_price` | `Optional[float]` | First bar close |
| `last_price` | `Optional[float]` | Last bar close |
| `monthly` | `List[MonthStats]` | Monthly breakdown |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `summary()` | `str` | Formatted summary table |
| `monthly_table()` | `str` | Monthly breakdown table |

### Class Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `from_portfolio(portfolio, symbol, first_bar, last_bar)` | `BacktestResults` | Build from Portfolio |

---

## MultiAssetResults

Combined results from multi-asset backtest.

```python
results = multi_engine.run()
print(results.summary())
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `per_symbol` | `Dict[str, BacktestResults]` | Individual results |
| `combined_equity_curve` | `List[Tuple[datetime, float]]` | Summed equity |
| `combined_max_drawdown_pct` | `float` | Portfolio drawdown |
| `combined_net_pnl` | `float` | Total PnL |
| `combined_return_pct` | `float` | Total return |
| `combined_total_trades` | `int` | Total trades |
| `combined_win_rate` | `float` | Combined win rate |
| `combined_total_fees` | `float` | Total fees |
| `combined_profit_factor` | `float` | Combined profit factor |
| `total_initial_equity` | `float` | Sum of initial equities |
| `combined_monthly` | `List[MonthStats]` | Combined monthly breakdown |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `summary()` | `str` | Combined + per-symbol summary |
| `monthly_table()` | `str` | Combined monthly table |

### Class Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `from_portfolios(portfolios, first_bars, last_bars, config)` | `MultiAssetResults` | Build from per-symbol portfolios |

---

## MonthStats

Statistics for a single month.

| Field | Type | Description |
|-------|------|-------------|
| `year` | `int` | Year |
| `month` | `int` | Month (1-12) |
| `trades` | `int` | Trade count |
| `wins` | `int` | Winning trades |
| `losses` | `int` | Losing trades |
| `gross_profit` | `float` | Sum of winning PnL |
| `gross_loss` | `float` | Sum of losing PnL |
| `net_pnl` | `float` | Net PnL |
| `fees` | `float` | Fees paid |
| `max_win` | `float` | Largest win |
| `max_loss` | `float` | Largest loss |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `win_rate` | `float` | Win rate (0-100) |
| `label` | `str` | "YYYY-MM" |

---

## Utility Functions

```python
from replaybt import monthly_breakdown, format_monthly_table

months = monthly_breakdown(trades)
table = format_monthly_table(months, initial_equity=10_000)
```
