# Execution Loop

Every bar passes through four phases in strict order. The engine never skips or reorders phases.

## The 4 Phases

```
Bar arrives (1-minute candle)
│
├─ Phase 1: Fill pending orders
│  ├─ Market orders → fill at bar OPEN + adverse slippage
│  └─ Limit orders → check if price crossed limit level
│
├─ Phase 2: Check exits
│  ├─ Gap check → did OPEN gap past SL/TP?
│  ├─ Intra-bar → check HIGH/LOW against SL/TP levels
│  ├─ Breakeven → activate if profit threshold reached
│  └─ Trailing stop → update trail, check if hit
│
├─ Phase 3: Strategy exits
│  └─ check_exits() → strategy-initiated closes
│
└─ Phase 4: Signals
   ├─ on_bar() → strategy sees COMPLETED bar + indicators
   └─ Returned orders become PENDING for next bar
```

## Why This Order Matters

**Phase 1 before Phase 4** ensures that signals from bar T fill at bar T+1's open. Your strategy never sees incomplete data.

**Phase 2 before Phase 4** ensures exits are processed before new signals. If a position closes this bar, the strategy can optionally emit a new signal on the same bar (controlled by `skip_signal_on_close`).

**Phase 3 between Phase 2 and Phase 4** gives your strategy a chance to close positions based on custom logic (via `check_exits`) before `on_bar` runs.

## Example: One Bar's Lifecycle

```python
# Bar T-1: strategy sees EMA crossover, returns MarketOrder(LONG)
# → order becomes PENDING

# Bar T arrives:
#   Phase 1: pending LONG fills at bar T's open ($2,300.50 + slippage)
#   Phase 2: check SL/TP against bar T's high/low — no exit
#   Phase 3: check_exits() — no custom exit
#   Phase 4: on_bar() runs with bar T data — no new signal

# Bar T+1 arrives:
#   Phase 1: no pending orders
#   Phase 2: bar T+1's low hits SL → exit at SL level
#   Phase 3: skipped (position already closed)
#   Phase 4: on_bar() runs — could emit new signal
```

## Configuration

```python
engine = BacktestEngine(
    strategy=my_strategy,
    data=data,
    config={
        # Phase 1 settings
        "slippage": 0.0002,       # 0.02% per side, adverse direction
        "taker_fee": 0.00015,     # 0.015% per side
        "maker_fee": 0.0,         # for limit orders

        # Phase 4 settings
        "skip_signal_on_close": True,   # skip on_bar when position closes
        "same_direction_only": True,    # reject opposite-direction orders
    },
)
```

## Event Hooks

You can observe each phase without modifying the loop:

```python
engine.on("fill", lambda fill: print(f"Filled: {fill}"))
engine.on("exit", lambda fill, trade: print(f"Exit: {trade.reason}"))
engine.on("bar", lambda bar: None)  # every bar
engine.on("signal", lambda order: print(f"Signal: {order.side}"))
```
