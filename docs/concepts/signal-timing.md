# Signal Timing

## The T / T+1 Rule

```
WRONG (look-ahead bias):
  Signal at bar T close → Entry at bar T close

CORRECT (realistic):
  Signal at bar T close → Entry at bar T+1 open
```

When `on_bar()` returns an `Order`, the engine does **not** fill it immediately. The order becomes *pending* and fills at the **next bar's open** with adverse slippage applied.

## How Pending Orders Work

```python
class MyStrategy(Strategy):
    def on_bar(self, bar, indicators, positions):
        if some_condition:
            # This order is NOT filled now.
            # It becomes pending and fills at the NEXT bar's open.
            return MarketOrder(side=Side.LONG, take_profit_pct=0.05)
        return None
```

Internally:

1. `on_bar()` returns a `MarketOrder` during Phase 4 of bar T
2. The engine stores it as a pending order
3. At the start of bar T+1 (Phase 1), the pending order fills at `bar_T1.open * (1 + slippage)`

## Multiple Orders

`on_bar()` can return a single order or a list:

```python
def on_bar(self, bar, indicators, positions):
    orders = []

    # Last MarketOrder wins (overwrites previous pending market order)
    orders.append(MarketOrder(side=Side.LONG))

    # LimitOrders stack (all are added to the pending limit queue)
    orders.append(LimitOrder(side=Side.LONG, limit_price=2300.0))
    orders.append(LimitOrder(side=Side.LONG, limit_price=2250.0))

    return orders
```

Rules:

- **MarketOrder**: the last one returned replaces any previous pending market order
- **LimitOrder**: each one is appended to the pending limit queue
- **StopOrder**: each one is appended to the pending stop queue

## skip_signal_on_close

When a position closes during Phase 2 or 3 of a bar, should `on_bar()` still run?

```python
config = {
    "skip_signal_on_close": True,   # default — skip on_bar after exit
    # "skip_signal_on_close": False,  # for mean-reversion re-entry
}
```

- **True** (default): if a position closes this bar, `on_bar()` is skipped. Prevents same-bar re-entry after a stop or target hit. Good for trend-following.
- **False**: `on_bar()` always runs. Allows immediate re-entry after an exit. Good for mean-reversion strategies where you want to flip direction on exit.

## same_direction_only

```python
config = {
    "same_direction_only": True,  # default — reject opposite orders
}
```

When True, if you have a LONG position open and `on_bar()` returns a SHORT order, the order is silently rejected. Set False to allow hedging.

## Verifying Your Timing

Use the [DelayTest](../api/validation.md) to add +1 bar latency. If PnL drops dramatically, your strategy may have hidden timing sensitivity:

```python
from replaybt.validation.stress import DelayTest

result = DelayTest(
    strategy_factory=MyStrategy,
    data=data,
    config=config,
    delay_bars=1,
).run()
print(result.verdict)  # "PASS" or "FAIL"
```
