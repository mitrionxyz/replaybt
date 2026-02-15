# replaybt

**Realistic backtesting engine for algo traders and AI agents.**

The engine owns execution — your strategy only emits signals. No look-ahead bias by default. Gap protection, adverse slippage, and fees are built in, not bolted on.

---

## Why replaybt?

Most backtesting frameworks let you fill orders at the close of the bar that generated the signal. That's not how real trading works. In production, you see the bar close, compute indicators, and fill at the *next* bar's open — at a worse price.

replaybt enforces this by design:

- **Signals at T, fills at T+1** — the engine queues market orders and fills at the next bar's open
- **Gap protection** — if the open gaps past your stop, you get the open (not the stop level)
- **Adverse slippage** — entries fill worse, exits fill worse, always
- **1-minute resolution** — check stops intra-bar, not just at bar boundaries

## Features

| Category | What you get |
|----------|-------------|
| **Execution** | 4-phase loop, gap protection, adverse slippage, maker/taker fees |
| **Indicators** | 11 built-in (EMA, SMA, RSI, ATR, CHOP, Bollinger, MACD, Stochastic, VWAP, OBV) + multi-timeframe resampler |
| **Orders** | Market, limit (with timeout), stop orders, scale-in via merge |
| **Risk** | Breakeven stops, trailing stops, partial take profit |
| **Multi-asset** | Time-synchronized multi-symbol loop with portfolio-level metrics |
| **RL-ready** | `StepEngine` with gym-like `step(action)` / `reset()` API |
| **AI-friendly** | `DeclarativeStrategy` from JSON config, no Python class needed |
| **Validation** | Static bias auditor (11 checks), delay test, out-of-sample split |
| **Optimization** | Parallel parameter sweep, walk-forward, Monte Carlo |
| **Live-ready** | Async data providers for Hyperliquid and Lighter exchanges |

## Install

```bash
pip install replaybt
```

Optional extras:

```bash
pip install replaybt[live]    # + aiohttp, websockets
pip install replaybt[plots]   # + matplotlib
pip install replaybt[data]    # + requests (exchange fetchers)
pip install replaybt[dev]     # + pytest, pytest-cov
```

## Quick Example

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, MarketOrder, Side


class EMACrossover(Strategy):
    def configure(self, config):
        self._prev_fast = self._prev_slow = None

    def on_bar(self, bar, indicators, positions):
        fast = indicators.get("ema_fast")
        slow = indicators.get("ema_slow")
        if fast is None or slow is None or self._prev_fast is None:
            self._prev_fast, self._prev_slow = fast, slow
            return None

        crossed_up = fast > slow and self._prev_fast <= self._prev_slow
        self._prev_fast, self._prev_slow = fast, slow

        if not positions and crossed_up:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.05,
                stop_loss_pct=0.03,
            )
        return None


engine = BacktestEngine(
    strategy=EMACrossover(),
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    config={
        "initial_equity": 10_000,
        "indicators": {
            "ema_fast": {"type": "ema", "period": 15, "source": "close"},
            "ema_slow": {"type": "ema", "period": 35, "source": "close"},
        },
    },
)
results = engine.run()
print(results.summary())
```

## Next Steps

- [Getting Started](getting-started/index.md) — install, run your first backtest, understand the output
- [Concepts](concepts/index.md) — how the execution loop, signal timing, and gap protection work
- [Cookbook](cookbook/index.md) — working recipes for common patterns
- [API Reference](api/index.md) — every class, method, and parameter
