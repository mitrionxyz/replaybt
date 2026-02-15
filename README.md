# replaybt

Realistic backtesting engine for algo traders and AI agents.

The engine owns execution — your strategy only emits signals. No look-ahead bias by default. Gap protection, adverse slippage, and fees are built in, not bolted on.

## Install

```bash
pip install replaybt
```

```
============================================================
  Backtest Results: ETH
============================================================
  Net PnL:          $1,445.06 (+14.5%)
  Max Drawdown:     5.6%
  Total Trades:     11
  Win Rate:         54.5%
  Avg Win:          $495.00 (4.98%)
  Avg Loss:         $304.99 (3.02%)
  Profit Factor:    1.95
  Total Fees:       $33.00
  Initial Equity:   $10,000.00
  Final Equity:     $11,445.06
  ────────────────────────────────────────────────────────
  Buy & Hold:       +2.8%
  Alpha:            +11.7%
  ────────────────────────────────────────────────────────
  Exit Breakdown:
    STOP_LOSS               5 (45.5%)
    TAKE_PROFIT             6 (54.5%)
============================================================
```

## Quick Start

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
            return MarketOrder(side=Side.LONG, take_profit_pct=0.05, stop_loss_pct=0.03)
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

## Key Features

- **Signals at T, fills at T+1** — no look-ahead bias
- **Gap protection** — open gaps past stops fill at the open, not the stop level
- **11 built-in indicators** with automatic multi-timeframe resampling
- **Limit orders, scale-in, breakeven stops, trailing stops, partial TP**
- **Multi-asset** — time-synchronized portfolio backtest
- **RL-ready** — `StepEngine` with gym-like `step()` / `reset()`
- **Declarative strategies** — JSON config, no Python class needed
- **Validation** — static bias auditor, delay test, OOS split
- **Optimization** — parallel parameter sweep, walk-forward, Monte Carlo

## Documentation

Full documentation: [sirmoremoney.github.io/replaybt](https://sirmoremoney.github.io/replaybt)

- [Getting Started](https://sirmoremoney.github.io/replaybt/getting-started/) — first backtest tutorial
- [Concepts](https://sirmoremoney.github.io/replaybt/concepts/) — execution loop, signal timing, gap protection
- [Cookbook](https://sirmoremoney.github.io/replaybt/cookbook/) — working recipes for common patterns
- [API Reference](https://sirmoremoney.github.io/replaybt/api/) — every class, method, and parameter

## License

MIT
