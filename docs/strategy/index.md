# Strategy

A strategy in replaybt is a class that receives completed bars and returns orders. The engine handles everything else — execution, slippage, fees, exits.

## Strategy Lifecycle

```
Engine created
│
├─ configure(config)          # once, before first bar
│
├─ For each bar:
│  ├─ (engine fills pending orders)
│  ├─ (engine checks SL/TP/breakeven/trailing)
│  ├─ check_exits(bar, positions)  # optional custom exit logic
│  └─ on_bar(bar, indicators, positions)  # emit signals
│      │
│      ├─ on_fill(fill)       # after entry fill (next bar)
│      └─ on_exit(fill, trade) # after position close
│
└─ Engine returns BacktestResults
```

## Pages

| Page | What you'll learn |
|------|------------------|
| [Callbacks](callbacks.md) | `on_bar`, `on_fill`, `on_exit`, `check_exits` |
| [Declarative](declarative.md) | JSON-config strategy with no Python class |
| [Per-Symbol Config](per-symbol-config.md) | `StrategyConfig` defaults + per-symbol overrides |
| [Custom Exits](custom-exits.md) | Partial TP, trailing stops, breakeven, post-exit re-entry |
