# Orders

## Order (base)

Base class for all order types.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `side` | `Side` | required | `Side.LONG` or `Side.SHORT` |
| `size_usd` | `Optional[float]` | `None` | Position size (None = use config default) |
| `symbol` | `str` | `""` | Asset symbol |
| `group` | `Optional[str]` | `None` | Position group for independent tracking |
| `take_profit_pct` | `Optional[float]` | `None` | TP as fraction from entry (0.08 = 8%) |
| `stop_loss_pct` | `Optional[float]` | `None` | SL as fraction from entry (0.035 = 3.5%) |
| `breakeven_trigger_pct` | `Optional[float]` | `None` | Activate breakeven at this profit |
| `breakeven_lock_pct` | `Optional[float]` | `None` | Lock SL at this profit level |
| `trailing_stop_pct` | `Optional[float]` | `None` | Trail distance from peak |
| `trailing_stop_activation_pct` | `Optional[float]` | `None` | Min profit to start trailing |
| `partial_tp_pct` | `Optional[float]` | `None` | Fraction to close at TP (0.5 = 50%) |
| `partial_tp_new_tp_pct` | `Optional[float]` | `None` | New TP for remainder after partial close |
| `cancel_pending_limits` | `bool` | `False` | Cancel all pending limits when processed |

---

## MarketOrder

Fills at the next bar's open + adverse slippage.

```python
from replaybt import MarketOrder, Side

order = MarketOrder(
    side=Side.LONG,
    take_profit_pct=0.08,
    stop_loss_pct=0.035,
)
```

Inherits all `Order` fields. No additional fields.

---

## LimitOrder

Price-triggered entry. Fills when price crosses the limit level. Uses maker fees by default.

```python
from replaybt import LimitOrder, Side

order = LimitOrder(
    side=Side.LONG,
    limit_price=2300.0,
    timeout_bars=120,
    merge_position=True,
)
```

### Additional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `limit_price` | `float` | `0.0` | Fill price |
| `timeout_bars` | `int` | `0` | Cancel after N bars (0 = never) |
| `use_maker_fee` | `bool` | `True` | Use maker fee (False = taker) |
| `min_positions` | `int` | `0` | Only fill when >= N positions exist |
| `merge_position` | `bool` | `False` | Merge into existing position |

### merge_position

When `True`, the limit order doesn't open a new position. Instead it merges into the existing one:

- Entry price becomes weighted average
- Position size increases
- SL/TP recalculate from new average entry

### min_positions

Guards against orphaned limit orders. If `min_positions=1`, the limit order only fills when at least one position exists. Useful for DCA scale-in orders that shouldn't fill after the main position has already closed.

---

## StopOrder

Fills when price breaks through the stop price. Becomes a market order on trigger.

```python
from replaybt import StopOrder, Side

order = StopOrder(
    side=Side.LONG,
    stop_price=2400.0,
    timeout_bars=100,
)
```

### Additional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stop_price` | `float` | `0.0` | Trigger price |
| `timeout_bars` | `int` | `0` | Cancel after N bars (0 = never) |

---

## CancelPendingLimitsOrder

Sentinel class. Return from `on_exit()` or `on_fill()` to cancel all pending limit orders without placing a new order.

```python
from replaybt import CancelPendingLimitsOrder

def on_exit(self, fill, trade):
    return CancelPendingLimitsOrder()
```
