# Scale-In

Add to an existing position at a better price. replaybt supports two methods: DCA (limit order at a fixed dip) and signal-based (second entry on a new signal).

## DCA Scale-In

Place a limit order to buy more if price dips after entry:

```python
from replaybt import Strategy, MarketOrder, LimitOrder, Side, CancelPendingLimitsOrder


class DCAStrategy(Strategy):
    def configure(self, config):
        self._prev_rsi = None

    def on_bar(self, bar, indicators, positions):
        rsi = indicators.get("rsi")
        prev = self._prev_rsi
        self._prev_rsi = rsi
        if rsi is None or prev is None:
            return None

        if not positions and rsi < 25 and prev >= 25:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.04,
                stop_loss_pct=0.05,
            )
        return None

    def on_fill(self, fill):
        if fill.is_entry:
            # Scale in at -0.5% from entry
            dip_price = fill.price * 0.995
            return LimitOrder(
                side=fill.side,
                limit_price=dip_price,
                merge_position=True,   # merge into existing position
                timeout_bars=120,      # cancel after 120 bars (2 hours)
                size_usd=fill.size_usd * 0.5,  # 50% of main size
            )
        return None

    def on_exit(self, fill, trade):
        # Cancel pending scale-in when position closes
        return CancelPendingLimitsOrder()
```

### How merge_position Works

When `merge_position=True`, the limit order doesn't open a new position. Instead, it merges into the existing one:

- Entry price becomes the weighted average of both fills
- Position size increases
- SL/TP levels recalculate from the new average entry

### Timeout

`timeout_bars=120` means the limit order is canceled after 120 bars if not filled. Set `timeout_bars=0` for no timeout.

### min_positions

Use `min_positions=1` to ensure the limit order only fills when a position already exists:

```python
LimitOrder(
    side=fill.side,
    limit_price=dip_price,
    merge_position=True,
    min_positions=1,  # only fill if at least 1 position exists
)
```

## Signal-Based Scale-In

Enter a second position on a new RSI signal in the same direction:

```python
class SignalScaleIn(Strategy):
    def configure(self, config):
        self._prev_rsi = None

    def on_bar(self, bar, indicators, positions):
        rsi = indicators.get("rsi")
        prev = self._prev_rsi
        self._prev_rsi = rsi
        if rsi is None or prev is None:
            return None

        if rsi < 25 and prev >= 25:
            if not positions:
                return MarketOrder(
                    side=Side.LONG,
                    take_profit_pct=0.04,
                    stop_loss_pct=0.05,
                )
            # Already have a position — scale in with another signal
            elif len(positions) == 1 and positions[0].is_long:
                return MarketOrder(
                    side=Side.LONG,
                    take_profit_pct=0.04,
                    stop_loss_pct=0.05,
                    size_usd=5000,  # smaller second entry
                )
        return None
```

!!! note
    For signal-based scale-in with `max_positions=1`, you need `merge_position=True` on a `LimitOrder` instead, or increase `max_positions` in the engine config.

## Engine Config for Scale-In

```python
config = {
    "initial_equity": 10_000,
    "max_positions": 1,       # merge into single position
    "default_size_usd": 10_000,
}
```

With `max_positions=1` and `merge_position=True`, the engine merges additional fills into the existing position rather than rejecting them.
