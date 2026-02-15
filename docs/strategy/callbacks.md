# Strategy Callbacks

## on_bar (required)

Called with every completed bar. Return an `Order` to emit a signal, or `None`.

```python
from replaybt import Strategy, MarketOrder, Side, Bar
from typing import Dict, Any, List

class MyStrategy(Strategy):
    def on_bar(
        self,
        bar: Bar,               # completed 1m bar
        indicators: Dict[str, Any],  # current indicator values
        positions: List,         # open positions
    ):
        ema = indicators.get("ema_fast")
        if ema is None:
            return None

        if not positions and bar.close > ema:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.05,
                stop_loss_pct=0.03,
            )
        return None
```

**Arguments:**

| Arg | Type | Description |
|-----|------|-------------|
| `bar` | `Bar` | Current completed 1m bar with timestamp, OHLCV, symbol |
| `indicators` | `Dict[str, Any]` | Values from configured indicators. `None` if not ready |
| `positions` | `List[Position]` | Currently open positions for this symbol |

**Returns:** `Order`, `List[Order]`, or `None`

## configure

Called once before the first bar. Use it to initialize strategy state.

```python
class MyStrategy(Strategy):
    def configure(self, config: dict):
        self._prev_fast = None
        self._prev_slow = None
        self._trade_count = 0
```

The `config` dict is the same dict passed to the engine constructor.

## on_fill

Called after an entry fill (or a merge fill for scale-in). Can return a `LimitOrder` for scale-in or a `MarketOrder`.

```python
from replaybt import LimitOrder

class ScaleInStrategy(Strategy):
    def on_fill(self, fill):
        if fill.is_entry:
            # Place a limit order to scale in at -0.5% from entry
            dip_price = fill.price * (1 - 0.005) if fill.side == Side.LONG else fill.price * (1 + 0.005)
            return LimitOrder(
                side=fill.side,
                limit_price=dip_price,
                merge_position=True,  # merge into existing position
                timeout_bars=120,
            )
        return None
```

**Arguments:**

| Arg | Type | Description |
|-----|------|-------------|
| `fill` | `Fill` | The fill event with price, side, size, fees, `is_entry` flag |

**Returns:** `Order` or `None`

## on_exit

Called after a position closes. Can return an `Order` for immediate re-entry, a `CancelPendingLimitsOrder` to clean up, or `None`.

```python
from replaybt import CancelPendingLimitsOrder

class FlipStrategy(Strategy):
    def on_exit(self, fill, trade):
        # Cancel any pending scale-in limit orders
        if trade.reason == "TAKE_PROFIT":
            return CancelPendingLimitsOrder()
        return None
```

**Arguments:**

| Arg | Type | Description |
|-----|------|-------------|
| `fill` | `Fill` | The exit fill |
| `trade` | `Trade` | Completed trade with entry/exit times, PnL, reason |

**Returns:** `Order`, `CancelPendingLimitsOrder`, or `None`

## check_exits

Called before `on_bar()` on every bar where positions are open. Lets you implement custom exit logic (e.g., time-based exits, indicator-based exits).

```python
class TimedExitStrategy(Strategy):
    def check_exits(self, bar, positions):
        exits = []
        for i, pos in enumerate(positions):
            # Close after 100 bars
            hours_held = (bar.timestamp - pos.entry_time).total_seconds() / 3600
            if hours_held > 100:
                exits.append((i, bar.close, "TIME_EXIT"))
        return exits
```

**Return format:** list of tuples:

```python
# Full close:
(position_index, exit_price, reason_string)

# Partial close:
(position_index, exit_price, reason_string, close_fraction)
# close_fraction: 0.5 = close 50% of position
```

!!! note
    If `check_exits()` returns any exits, `on_bar()` is **skipped** for that bar (same behavior as engine-level SL/TP exits).

## Warmup

Indicators need a warmup period before producing valid values. During warmup, `indicators.get("name")` returns `None`.

```python
def on_bar(self, bar, indicators, positions):
    ema = indicators.get("ema_fast")
    if ema is None:
        return None  # still warming up
    # ... rest of logic
```

The number of warmup bars depends on the indicator and its period. For an EMA with period 35 on 30m timeframe, you need at least `35 * 30 = 1,050` 1m bars before it's ready.
