# Data Types

## Bar

A single OHLCV candle. Frozen dataclass (immutable).

```python
from replaybt import Bar

bar = Bar(
    timestamp=datetime(2024, 1, 1, 0, 0),
    open=2300.50,
    high=2301.20,
    low=2299.80,
    close=2300.90,
    volume=125.5,
    symbol="ETH",
    timeframe="1m",
)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timestamp` | `datetime` | required | Bar open time |
| `open` | `float` | required | Open price |
| `high` | `float` | required | High price |
| `low` | `float` | required | Low price |
| `close` | `float` | required | Close price |
| `volume` | `float` | required | Volume |
| `symbol` | `str` | `""` | Asset symbol |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

---

## Side

Trade direction.

```python
from replaybt import Side

Side.LONG   # "LONG"
Side.SHORT  # "SHORT"
```

---

## OrderType

```python
from replaybt import OrderType

OrderType.MARKET  # "MARKET"
OrderType.LIMIT   # "LIMIT"
OrderType.STOP    # "STOP"
```

---

## ExitReason

```python
from replaybt import ExitReason

ExitReason.STOP_LOSS          # "STOP_LOSS"
ExitReason.STOP_LOSS_GAP      # "STOP_LOSS_GAP"
ExitReason.TAKE_PROFIT        # "TAKE_PROFIT"
ExitReason.TAKE_PROFIT_GAP    # "TAKE_PROFIT_GAP"
ExitReason.BREAKEVEN          # "BREAKEVEN"
ExitReason.BREAKEVEN_GAP      # "BREAKEVEN_GAP"
ExitReason.TRAILING_STOP      # "TRAILING_STOP"
ExitReason.TRAILING_STOP_GAP  # "TRAILING_STOP_GAP"
ExitReason.PARTIAL_TP         # "PARTIAL_TP"
ExitReason.SIGNAL             # "SIGNAL"
```

---

## Fill

An order fill event. Frozen dataclass.

```python
from replaybt import Fill
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timestamp` | `datetime` | required | Fill time |
| `side` | `Side` | required | LONG or SHORT |
| `price` | `float` | required | Fill price (after slippage) |
| `size_usd` | `float` | required | Position size in USD |
| `symbol` | `str` | `""` | Asset symbol |
| `fees` | `float` | `0.0` | Fees paid |
| `slippage_cost` | `float` | `0.0` | Slippage cost |
| `is_entry` | `bool` | `True` | True for entries, False for exits |
| `reason` | `str` | `""` | Exit reason (empty for entries) |

---

## Position

An open position. Mutable dataclass.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `side` | `Side` | required | LONG or SHORT |
| `entry_price` | `float` | required | Average entry price |
| `entry_time` | `datetime` | required | Entry timestamp |
| `size_usd` | `float` | required | Position size |
| `stop_loss` | `float` | required | Current SL price |
| `take_profit` | `float` | required | Current TP price |
| `symbol` | `str` | `""` | Asset symbol |
| `breakeven_activated` | `bool` | `False` | Breakeven active |
| `breakeven_trigger` | `float` | `0.0` | Breakeven trigger price |
| `breakeven_lock` | `float` | `0.0` | Breakeven lock price |
| `trailing_stop_pct` | `float` | `0.0` | Trail distance |
| `trailing_stop_activation_pct` | `float` | `0.0` | Trail activation |
| `position_high` | `float` | `0.0` | Highest price since entry |
| `position_low` | `float` | `0.0` | Lowest price since entry |
| `trailing_stop_activated` | `bool` | `False` | Trail active |
| `partial_tp_pct` | `float` | `0.0` | Partial TP fraction |
| `partial_tp_new_tp_pct` | `float` | `0.0` | New TP after partial |
| `partial_tp_done` | `bool` | `False` | Partial TP executed |
| `group` | `Optional[str]` | `None` | Position group |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_long` | `bool` | True if LONG side |

---

## Trade

A completed trade (entry + exit). Frozen dataclass.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `entry_time` | `datetime` | required | Entry timestamp |
| `exit_time` | `datetime` | required | Exit timestamp |
| `side` | `Side` | required | LONG or SHORT |
| `entry_price` | `float` | required | Entry price |
| `exit_price` | `float` | required | Exit price |
| `size_usd` | `float` | required | Position size |
| `pnl_usd` | `float` | required | Profit/loss in USD |
| `pnl_pct` | `float` | required | Profit/loss as fraction |
| `fees` | `float` | required | Total fees (entry + exit) |
| `reason` | `str` | required | Exit reason |
| `symbol` | `str` | `""` | Asset symbol |
| `is_partial` | `bool` | `False` | Partial close |
| `group` | `Optional[str]` | `None` | Position group |

---

## PendingOrder

Internal representation of a queued order.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `side` | `Side` | required | Direction |
| `order_type` | `OrderType` | `MARKET` | Order type |
| `limit_price` | `Optional[float]` | `None` | Limit fill price |
| `size_usd` | `Optional[float]` | `None` | Position size |
| `stop_loss_pct` | `Optional[float]` | `None` | SL percentage |
| `take_profit_pct` | `Optional[float]` | `None` | TP percentage |
| `symbol` | `str` | `""` | Asset symbol |
| `bars_elapsed` | `int` | `0` | Bars since placed |
| `max_bars` | `int` | `0` | Timeout (0 = never) |
