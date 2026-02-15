# Trailing Stop

A stop that follows price as it moves in your favor, locking in profits from large moves.

## Complete Example

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, MarketOrder, Side


class TrailingStopStrategy(Strategy):
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
                stop_loss_pct=0.05,                  # safety SL at 5%
                trailing_stop_pct=0.02,              # trail 2% below peak
                trailing_stop_activation_pct=0.03,   # activate after +3%
            )
        return None


engine = BacktestEngine(
    strategy=TrailingStopStrategy(),
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

## How It Works

```
Entry at $2,000 (LONG)
  Safety SL = $1,900 (5%)
  Trail activates at $2,060 (+3%)
  Trail distance = 2%

Price path:
  $2,000 → $2,060: trail activates, trail stop = $2,018.80
  $2,060 → $2,100: trail stop moves up to $2,058.00
  $2,100 → $2,150: trail stop moves up to $2,107.00
  $2,150 → $2,110: trail stop at $2,107.00 — EXIT at $2,107

Profit: +5.35% (vs 8% if you'd used a fixed TP at $2,160)
But captures most of a +7.5% move without predicting the top
```

## Parameters

| Parameter | Description | Typical Value |
|-----------|-------------|---------------|
| `trailing_stop_pct` | Distance from peak (LONG) or trough (SHORT) | 0.02 (2%) |
| `trailing_stop_activation_pct` | Minimum profit to activate trailing | 0.03 (3%) |

## With Fixed TP

You can combine a trailing stop with a fixed take profit:

```python
MarketOrder(
    side=Side.LONG,
    take_profit_pct=0.10,                # cap at +10%
    stop_loss_pct=0.035,                 # safety SL
    trailing_stop_pct=0.02,              # trail 2%
    trailing_stop_activation_pct=0.04,   # activate at +4%
)
```

Whichever triggers first (fixed TP or trailing stop) closes the position.

## Without Activation Threshold

Set `trailing_stop_activation_pct=0` to start trailing immediately from entry:

```python
MarketOrder(
    side=Side.LONG,
    trailing_stop_pct=0.03,
    trailing_stop_activation_pct=0.0,  # active from bar 1
)
```

!!! warning
    Immediate trailing can trigger premature exits in choppy markets. An activation threshold gives the trade room to develop before the trail starts.
