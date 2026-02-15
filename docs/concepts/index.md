# Concepts

These pages explain the core mechanics that make replaybt different from other backtesting frameworks.

| Page | What you'll learn |
|------|------------------|
| [Execution Loop](execution-loop.md) | The 4-phase bar processing pipeline |
| [Signal Timing](signal-timing.md) | Why signals at T fill at T+1, and how pending orders work |
| [Gap Protection](gap-protection.md) | How open gaps affect stop and target fills |
| [Multi-Timeframe](multi-timeframe.md) | Computing indicators on higher timeframes from 1m data |

## The Core Principle

In real trading:

1. A bar closes
2. You see the close price
3. You compute indicators
4. You place an order
5. The order fills at the **next bar's open**

Most backtesting frameworks skip step 5 and fill at the close of the signal bar. This creates look-ahead bias — you're buying at a price you couldn't have bought at in production.

replaybt enforces realistic execution by design. The engine manages the order lifecycle; your strategy only emits signals.
