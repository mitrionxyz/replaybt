# Getting Started

## Install

```bash
pip install replaybt
```

## Prepare Data

replaybt expects 1-minute OHLCV data in CSV or Parquet format with columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`.

```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,2300.50,2301.20,2299.80,2300.90,125.5
2024-01-01 00:01:00,2300.90,2302.00,2300.50,2301.80,98.3
...
```

You can also fetch data directly from exchanges:

```python
from replaybt import BinanceProvider

data = BinanceProvider("ETHUSDT", start="2024-01-01", end="2024-12-31")
```

## Your First Backtest

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, MarketOrder, Side


class EMACrossover(Strategy):
    """Go long when fast EMA crosses above slow EMA."""

    def configure(self, config):
        self._prev_fast = self._prev_slow = None

    def on_bar(self, bar, indicators, positions):
        fast = indicators.get("ema_fast")
        slow = indicators.get("ema_slow")

        # Wait for indicators to warm up
        if fast is None or slow is None or self._prev_fast is None:
            self._prev_fast, self._prev_slow = fast, slow
            return None

        # Detect crossover
        crossed_up = fast > slow and self._prev_fast <= self._prev_slow
        crossed_down = fast < slow and self._prev_fast >= self._prev_slow
        self._prev_fast, self._prev_slow = fast, slow

        # Emit signal (fills at next bar's open)
        if not positions:
            if crossed_up:
                return MarketOrder(
                    side=Side.LONG,
                    take_profit_pct=0.05,
                    stop_loss_pct=0.03,
                )
            if crossed_down:
                return MarketOrder(
                    side=Side.SHORT,
                    take_profit_pct=0.05,
                    stop_loss_pct=0.03,
                )
        return None


engine = BacktestEngine(
    strategy=EMACrossover(),
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    config={
        "initial_equity": 10_000,
        "indicators": {
            "ema_fast": {"type": "ema", "period": 15, "source": "close"},
            "ema_slow": {"type": "ema", "period": 35, "source": "close"},
        },
    },
)
results = engine.run()
print(results.summary())
```

## Understanding the Output

`results.summary()` prints:

```
============================================================
  Backtest Results: ETH
============================================================
  Net PnL:          $1,245.00 (+12.5%)
  Max Drawdown:     8.3%
  Total Trades:     47
  Win Rate:         63.8%
  Avg Win:          $89.50 (3.21%)
  Avg Loss:         $52.30 (1.88%)
  Profit Factor:    1.71
  Total Fees:       $32.90
  Initial Equity:   $10,000.00
  Final Equity:     $11,245.00
  ────────────────────────────────────────────────────────
  Buy & Hold:       +45.2%
  Alpha:            -32.7%
  ────────────────────────────────────────────────────────
  Exit Breakdown:
    BREAKEVEN              12 (25.5%)
    STOP_LOSS              15 (31.9%)
    TAKE_PROFIT            20 (42.6%)
============================================================
```

Key metrics:

| Metric | What it means |
|--------|--------------|
| **Net PnL** | Profit after all fees and slippage |
| **Max Drawdown** | Largest peak-to-trough equity decline |
| **Win Rate** | Percentage of trades that were profitable |
| **Profit Factor** | Gross profit / gross loss (> 1 = profitable) |
| **Total Fees** | Sum of all slippage + taker/maker fees |
| **Alpha** | Strategy return minus buy-and-hold return |

## Monthly Breakdown

```python
print(results.monthly_table())
```

Shows per-month PnL, win rate, and trade count — useful for spotting regime-dependent performance.

## What Happens Under the Hood

Every bar goes through four phases:

1. **Fill pending orders** — market orders fill at this bar's open + slippage
2. **Check limit orders** — pending limit orders checked for price-triggered fills
3. **Check exits** — SL/TP checked against open (gap), then high/low (intra-bar)
4. **Call strategy** — `on_bar()` runs with the completed bar, returned orders become pending

This means your signal at bar T always fills at bar T+1's open. No look-ahead bias is possible.

## Next Steps

- [Concepts](../concepts/index.md) — deep dive into the execution model
- [Strategy Callbacks](../strategy/callbacks.md) — `on_fill`, `on_exit`, `check_exits`
- [Cookbook](../cookbook/index.md) — working recipes for common patterns
