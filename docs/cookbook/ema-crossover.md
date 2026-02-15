# EMA Crossover

A basic trend-following strategy: go long when a fast EMA crosses above a slow EMA, short on the opposite cross.

## Complete Example

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, MarketOrder, Side


class EMACrossover(Strategy):
    def configure(self, config):
        self._prev_fast = None
        self._prev_slow = None

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

## What's Happening

1. **Indicators** — two EMAs computed on each 1m bar's close price
2. **Crossover detection** — compare current vs previous EMA values
3. **Signal** — `MarketOrder` returned on crossover, fills at next bar's open
4. **Exits** — engine manages TP at +5% and SL at -3% automatically

## Multi-Timeframe Variant

Compute EMAs on 30-minute bars instead of 1-minute:

```python
config={
    "indicators": {
        "ema_fast": {"type": "ema", "period": 15, "timeframe": "30m", "source": "close"},
        "ema_slow": {"type": "ema", "period": 35, "timeframe": "30m", "source": "close"},
    },
}
```

The strategy code stays the same. The engine resamples 1m bars into 30m bars and updates the EMAs every 30 minutes.

## Adding a Trend Filter

Only take longs when the 1h EMA trend is bullish:

```python
config={
    "indicators": {
        "ema_fast": {"type": "ema", "period": 15, "timeframe": "30m", "source": "close"},
        "ema_slow": {"type": "ema", "period": 35, "timeframe": "30m", "source": "close"},
        "ema_fast_1h": {"type": "ema", "period": 15, "timeframe": "1h", "source": "close"},
        "ema_slow_1h": {"type": "ema", "period": 35, "timeframe": "1h", "source": "close"},
    },
}
```

```python
def on_bar(self, bar, indicators, positions):
    fast = indicators.get("ema_fast")
    slow = indicators.get("ema_slow")
    fast_1h = indicators.get("ema_fast_1h")
    slow_1h = indicators.get("ema_slow_1h")

    if any(v is None for v in [fast, slow, fast_1h, slow_1h]):
        self._prev_fast, self._prev_slow = fast, slow
        return None

    crossed_up = fast > slow and self._prev_fast <= self._prev_slow
    self._prev_fast, self._prev_slow = fast, slow

    # Only long when 1h trend is bullish
    if not positions and crossed_up and fast_1h > slow_1h:
        return MarketOrder(side=Side.LONG, take_profit_pct=0.06, stop_loss_pct=0.03)
    return None
```
