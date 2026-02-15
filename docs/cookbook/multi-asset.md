# Multi-Asset

Run the same strategy on multiple symbols in a time-synchronized loop. `MultiAssetEngine` merges bars chronologically and produces portfolio-level metrics that capture correlated drawdowns.

## Complete Example

```python
from replaybt import MultiAssetEngine, CSVProvider, Strategy, MarketOrder, Side


class EMACrossover(Strategy):
    def configure(self, config):
        self._prev = {}

    def on_bar(self, bar, indicators, positions):
        sym = bar.symbol
        fast = indicators.get("ema_fast")
        slow = indicators.get("ema_slow")

        prev = self._prev.get(sym)
        self._prev[sym] = (fast, slow)

        if fast is None or slow is None or prev is None:
            return None
        if prev[0] is None:
            return None

        crossed_up = fast > slow and prev[0] <= prev[1]

        if not positions and crossed_up:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.05,
                stop_loss_pct=0.03,
            )
        return None


engine = MultiAssetEngine(
    strategy=EMACrossover(),
    assets={
        "ETH": CSVProvider("ETH_1m.csv", symbol_name="ETH"),
        "SOL": CSVProvider("SOL_1m.csv", symbol_name="SOL"),
    },
    config={
        "initial_equity": 10_000,   # per symbol
        "indicators": {
            "ema_fast": {"type": "ema", "period": 15, "source": "close"},
            "ema_slow": {"type": "ema", "period": 35, "source": "close"},
        },
    },
)
results = engine.run()
print(results.summary())        # combined + per-symbol
print(results.monthly_table())  # combined monthly breakdown
```

## Per-Symbol Config

Override indicators, sizing, or other config per symbol:

```python
config = {
    "initial_equity": 10_000,
    "indicators": {
        "ema_fast": {"type": "ema", "period": 15, "source": "close"},
        "ema_slow": {"type": "ema", "period": 35, "source": "close"},
    },
    "symbol_configs": {
        "ETH": {
            "indicators": {
                "ema_fast": {"type": "ema", "period": 10, "source": "close"},
                "ema_slow": {"type": "ema", "period": 30, "source": "close"},
            },
        },
        "SUI": {
            "default_size_usd": 5_000,
        },
    },
}
```

## Exposure Cap

Limit total portfolio exposure across all symbols:

```python
config = {
    "initial_equity": 10_000,
    "max_total_exposure_usd": 25_000,  # cap total open exposure
    # ...
}
```

When the cap is reached, new orders are rejected until existing positions close.

## Using bar.symbol

In a multi-asset strategy, `bar.symbol` tells you which asset the current bar belongs to. Positions are isolated per symbol.

```python
def on_bar(self, bar, indicators, positions):
    # bar.symbol == "ETH" or "SOL" etc.
    # positions = only positions for this symbol
    pass
```

## Results

`MultiAssetResults` provides:

```python
# Combined metrics
results.combined_net_pnl          # total PnL across all symbols
results.combined_max_drawdown_pct  # portfolio-level drawdown
results.combined_win_rate
results.combined_total_trades

# Per-symbol results
eth = results.per_symbol["ETH"]   # BacktestResults
sol = results.per_symbol["SOL"]   # BacktestResults
print(eth.summary())

# Combined equity curve
results.combined_equity_curve     # [(datetime, equity), ...]
```

!!! note
    Combined max drawdown captures correlated losses across symbols. Running separate `BacktestEngine` instances would understate the true portfolio drawdown.
