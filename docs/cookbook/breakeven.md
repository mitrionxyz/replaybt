# Breakeven Stop

Move the stop loss to lock in a small profit once the trade reaches a threshold.

## Complete Example

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, MarketOrder, Side


class BreakevenStrategy(Strategy):
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
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.08,
                stop_loss_pct=0.035,
                breakeven_trigger_pct=0.015,  # activate at +1.5%
                breakeven_lock_pct=0.005,     # move SL to +0.5%
            )
        return None


engine = BacktestEngine(
    strategy=BreakevenStrategy(),
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    config={
        "initial_equity": 10_000,
        "indicators": {
            "ema_fast": {"type": "ema", "period": 15, "timeframe": "30m", "source": "close"},
            "ema_slow": {"type": "ema", "period": 35, "timeframe": "30m", "source": "close"},
        },
    },
)
results = engine.run()
print(results.summary())
```

## How It Works

```
Entry at $2,000 (LONG)
  SL = $1,930 (3.5% below entry)
  TP = $2,160 (8% above entry)
  Breakeven trigger = $2,030 (+1.5%)
  Breakeven lock = $2,010 (+0.5%)

Price rises to $2,035:
  → Breakeven activated!
  → SL moves from $1,930 to $2,010

If price reverses:
  → Exit at $2,010 (BREAKEVEN reason)
  → Small profit instead of full loss
```

## Exit Breakdown

Breakeven exits show as `BREAKEVEN` in the exit breakdown:

```
Exit Breakdown:
  BREAKEVEN              28 (58.3%)
  STOP_LOSS              12 (25.0%)
  TAKE_PROFIT             8 (16.7%)
```

## Parameters

| Parameter | Description | Typical Value |
|-----------|-------------|---------------|
| `breakeven_trigger_pct` | Profit level that activates breakeven | 0.015 (1.5%) |
| `breakeven_lock_pct` | Where SL moves to after activation | 0.005 (0.5%) |

The lock level must be less than the trigger level. Once activated, the breakeven is permanent for that position — the SL cannot move back down.
