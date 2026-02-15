# Custom Exits

Beyond basic SL/TP, replaybt supports breakeven stops, trailing stops, partial take profit, and strategy-driven exits.

## Breakeven Stop

Move the stop loss to lock in a small profit once the position reaches a threshold:

```python
MarketOrder(
    side=Side.LONG,
    take_profit_pct=0.06,
    stop_loss_pct=0.03,
    breakeven_trigger_pct=0.02,   # activate at +2%
    breakeven_lock_pct=0.005,     # move SL to +0.5%
)
```

When price reaches +1.5% from entry, the stop loss moves to entry + 0.5%. If price reverses, you exit with a small profit instead of a full loss.

## Trailing Stop

A stop that follows price as it moves in your favor:

```python
MarketOrder(
    side=Side.LONG,
    trailing_stop_pct=0.02,              # trail 2% below peak
    trailing_stop_activation_pct=0.03,   # activate after +3% profit
)
```

The trailing stop activates once the position is +3% in profit. From that point, it trails 2% below the highest price seen. If price drops 2% from its peak, the position closes.

You can use a trailing stop with or without a fixed TP/SL:

```python
# Trailing stop only (no fixed TP)
MarketOrder(
    side=Side.LONG,
    stop_loss_pct=0.05,           # safety SL
    trailing_stop_pct=0.02,
    trailing_stop_activation_pct=0.01,
)
```

## Partial Take Profit

Close a fraction of the position at the first TP, then set a new TP for the remainder:

```python
MarketOrder(
    side=Side.LONG,
    take_profit_pct=0.05,
    stop_loss_pct=0.03,
    partial_tp_pct=0.5,           # close 50% at TP
    partial_tp_new_tp_pct=0.10,   # new TP at +10% for remainder
)
```

When the first TP is hit:
1. 50% of the position closes at the TP level
2. The remaining 50% gets a new TP at +10% from entry
3. The stop loss stays the same

## Strategy-Driven Exits (check_exits)

For exits based on indicators, time, or custom logic, implement `check_exits()`:

```python
class RSIExitStrategy(Strategy):
    def check_exits(self, bar, positions):
        exits = []
        for i, pos in enumerate(positions):
            # Exit long when RSI > 70
            rsi = self._current_rsi  # stored from on_bar
            if pos.is_long and rsi and rsi > 70:
                exits.append((i, bar.close, "RSI_OVERBOUGHT"))
        return exits

    def on_bar(self, bar, indicators, positions):
        self._current_rsi = indicators.get("rsi")
        # ... entry logic ...
```

### Partial Close via check_exits

Return a 4-tuple to close a fraction:

```python
def check_exits(self, bar, positions):
    exits = []
    for i, pos in enumerate(positions):
        pnl_pct = (bar.close - pos.entry_price) / pos.entry_price
        if pos.is_long and pnl_pct > 0.03:
            # Close 50% at current price
            exits.append((i, bar.close, "PARTIAL_TAKE", 0.5))
    return exits
```

## Post-Exit Re-Entry (on_exit)

Use `on_exit()` to immediately enter a new position after an exit:

```python
class FlipStrategy(Strategy):
    def on_exit(self, fill, trade):
        # After TP, flip direction if conditions are met
        if trade.reason == "TAKE_PROFIT":
            opposite = Side.SHORT if trade.side == Side.LONG else Side.LONG
            return MarketOrder(
                side=opposite,
                take_profit_pct=0.05,
                stop_loss_pct=0.03,
            )
        return None
```

## Canceling Pending Orders on Exit

When a position closes, any pending limit orders (e.g., scale-in) may still be active. Cancel them with `CancelPendingLimitsOrder`:

```python
from replaybt import CancelPendingLimitsOrder

class CleanupStrategy(Strategy):
    def on_exit(self, fill, trade):
        # Cancel pending scale-in limit orders
        return CancelPendingLimitsOrder()
```

## Combining Exit Types

All exit types can be combined on a single order:

```python
MarketOrder(
    side=Side.LONG,
    take_profit_pct=0.06,             # fixed TP
    stop_loss_pct=0.03,              # fixed SL
    breakeven_trigger_pct=0.02,      # breakeven at +2%
    breakeven_lock_pct=0.005,        # lock at +0.5%
    trailing_stop_pct=0.02,           # trail 2% below peak
    trailing_stop_activation_pct=0.04, # activate at +4%
    partial_tp_pct=0.5,               # close 50% at TP
    partial_tp_new_tp_pct=0.12,       # remainder TP at +12%
)
```

The engine evaluates exit conditions in priority order: gap check, SL, TP, breakeven activation, trailing stop update and check, partial TP.
