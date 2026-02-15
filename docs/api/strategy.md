# Strategy

## Strategy (ABC)

Abstract base class. Implement `on_bar()` to create a strategy.

```python
from replaybt import Strategy, MarketOrder, Side

class MyStrategy(Strategy):
    def configure(self, config):
        self._state = None

    def on_bar(self, bar, indicators, positions):
        return None  # or Order
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `configure` | `(config: dict) -> None` | Called once before first bar |
| `on_bar` | `(bar, indicators, positions) -> Order \| List[Order] \| None` | **Required.** Emit signals |
| `on_fill` | `(fill: Fill) -> Optional[Order]` | After entry/merge fill |
| `on_exit` | `(fill: Fill, trade: Trade) -> Order \| CancelPendingLimitsOrder \| None` | After position close |
| `check_exits` | `(bar: Bar, positions: List[Position]) -> List[Tuple]` | Custom exit logic |

### on_bar Return Types

| Return | Behavior |
|--------|----------|
| `None` | No action |
| `MarketOrder` | Replaces pending market order |
| `LimitOrder` | Appends to pending limit queue |
| `StopOrder` | Appends to pending stop queue |
| `List[Order]` | Last MarketOrder wins; LimitOrders stack |

### check_exits Return Format

```python
# Full close
[(position_index, exit_price, reason_string)]

# Partial close
[(position_index, exit_price, reason_string, close_fraction)]
```

---

## DeclarativeStrategy

JSON-config strategy. No Python subclassing needed.

```python
from replaybt import DeclarativeStrategy

# From JSON file
strategy = DeclarativeStrategy.from_json("config.json")

# From dict
strategy = DeclarativeStrategy.from_config(config_dict)
```

### Class Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `from_json(path)` | `DeclarativeStrategy` | Load from JSON file |
| `from_config(config)` | `DeclarativeStrategy` | Create from dict |

### Instance Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `indicator_config()` | `Dict` | Indicator config for engine |
| `on_bar(bar, indicators, positions)` | `Optional[Order]` | Execute declarative logic |

### Condition Types

| Type | Fields | Description |
|------|--------|-------------|
| `crossover` | `fast`, `slow` | fast > slow AND prev_fast <= prev_slow |
| `crossunder` | `fast`, `slow` | fast < slow AND prev_fast >= prev_slow |
| `above` | `left`, `right` | left > right |
| `below` | `left`, `right` | left < right |
| `above_threshold` | `indicator`, `threshold` | value >= threshold |
| `below_threshold` | `indicator`, `threshold` | value <= threshold |
| `crosses_above` | `indicator`, `threshold` | now > threshold AND prev <= threshold |
| `crosses_below` | `indicator`, `threshold` | now < threshold AND prev >= threshold |

---

## StrategyConfig

Per-symbol configuration with defaults and overrides.

```python
from replaybt import StrategyConfig

config = StrategyConfig(
    defaults={"tp": 0.06, "sl": 0.03},
    overrides={"ETH": {"tp": 0.08, "sl": 0.04}},
)
```

### Constructor

```python
StrategyConfig(
    defaults: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get(key, symbol, default)` | `Any` | Get value, checking overrides first |
| `for_symbol(symbol)` | `Dict[str, Any]` | Merged config for a symbol |
| `symbols()` | `list` | Symbols with overrides |
