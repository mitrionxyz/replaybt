# replaybt

Realistic backtesting engine for algo traders and AI agents.

The engine owns execution — your strategy only emits signals. No look-ahead bias by default. Gap protection, adverse slippage, and fees are built in, not bolted on.

## Why Another Backtesting Library?

Most backtesting frameworks let you fill orders at the close of the bar that generated the signal. That's not how real trading works. In production, you see the bar close, compute indicators, and fill at the *next* bar's open — at a worse price.

replaybt enforces this by design:

- **Signals at T, fills at T+1** — the engine queues market orders and fills at the next bar's open
- **Gap protection** — if the open gaps past your stop, you get the open (not the stop level)
- **Adverse slippage** — entries fill worse, exits fill worse, always
- **1-minute resolution** — check stops intra-bar, not just at bar boundaries

## Features

- **4-phase execution loop** — pending fills, limit checks, exit checks, then signals (no same-bar bias)
- **Realistic by default** — gap protection, adverse slippage, maker/taker fees
- **11 built-in indicators** — EMA, SMA, RSI, ATR, CHOP, Bollinger Bands, MACD, Stochastic, VWAP, OBV, plus a multi-timeframe resampler
- **Multi-timeframe** — feed 1m data, compute indicators on 5m/15m/30m/1h bars automatically
- **Limit orders** — price-triggered entries with timeout, maker fees, and min-position guards
- **Scale-in** — DCA or signal-based second entries with configurable dip, size, and timeout
- **Breakeven stops** — trigger at +X%, lock at +Y%
- **Replay mode** — historical data streamed at Nx wall-clock speed for visual debugging
- **RL-ready** — `StepEngine` with gym-like `step(action)` / `reset()` API
- **AI-agent friendly** — `DeclarativeStrategy` from JSON config, no Python class needed
- **Per-symbol configs** — `StrategyConfig` with defaults + per-symbol overrides
- **Validation suite** — static bias auditor (11 checks), +1 bar delay test, out-of-sample split
- **Parallel optimization** — `ParameterSweep` with multiprocessing across all CPU cores
- **Live-ready** — async data providers for Hyperliquid and Lighter exchanges

## Install

```bash
pip install replaybt
```

Optional extras:

```bash
pip install replaybt[live]   # + aiohttp, websockets (for live providers)
pip install replaybt[dev]    # + pytest, pytest-cov
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

## How It Works

Every bar goes through four phases in strict order:

| Phase | What Happens | Why |
|-------|-------------|-----|
| **1. Fill pending orders** | Market orders fill at this bar's open + slippage. Limit orders check if price crossed their level. | Signals from bar T fill at bar T+1's open — no look-ahead. |
| **2. Check scale-ins** | Pending scale-in limit orders checked for fill. | Second entries follow the same fill-at-next-bar rule. |
| **3. Check exits** | Open gap → exit at open. Otherwise check high/low against SL/TP levels. Breakeven activation. | Gap protection ensures you don't get a better fill than the market gave. |
| **4. Signals** | Call `strategy.on_bar()` with completed bar + indicators. Returned orders become pending. | Strategy sees only finalized data, never incomplete bars. |

## Strategy Callbacks

```python
class Strategy:
    def configure(self, config: dict) -> None: ...          # Called once before run
    def on_bar(self, bar, indicators, positions) -> Order:   # Required — emit signals
    def on_fill(self, fill: Fill) -> Optional[Order]: ...    # After entry fill
    def on_exit(self, fill: Fill, trade: Trade) -> Optional[Order]: ...  # After exit
    def check_exits(self, bar, positions) -> list: ...       # Custom exit logic
```

## Examples

Working examples are in the [`examples/`](examples/) directory:

| File | Description |
|------|-------------|
| [`01_basic_backtest.py`](examples/01_basic_backtest.py) | EMA crossover with TP/SL — simplest possible strategy |
| [`02_declarative_strategy.py`](examples/02_declarative_strategy.py) | JSON-config strategy, no Python class needed |
| [`trendmaster.json`](examples/trendmaster.json) | Example JSON config for a trend-following strategy |
| [`03_step_engine_rl.py`](examples/03_step_engine_rl.py) | RL agent with gym-like step/reset API |
| [`04_parameter_sweep.py`](examples/04_parameter_sweep.py) | Parallel TP/SL optimization with multiprocessing |
| [`05_validation.py`](examples/05_validation.py) | Static auditor + delay test + OOS split |

## Indicators

Configure indicators in the engine config dict. Multi-timeframe is automatic — set `timeframe` and the engine resamples 1m bars internally.

| Config `type` | Class | Key Parameters | Description |
|---------------|-------|----------------|-------------|
| `ema` | `EMA` | `period`, `source` | Exponential moving average |
| `sma` | `SMA` | `period`, `source` | Simple moving average |
| `rsi` | `RSI` | `period`, `method` | RSI (Wilder's exponential or simple rolling) |
| `atr` | `ATR` | `period` | Average true range |
| `chop` | `CHOP` | `period` | Choppiness index (ATR / price ratio) |
| `bollinger` | `BollingerBands` | `period`, `std_dev` | Bollinger Bands (upper, middle, lower) |
| `macd` | `MACD` | `fast`, `slow`, `signal` | MACD line, signal line, histogram |
| `stochastic` | `Stochastic` | `k_period`, `d_period` | Stochastic %K and %D |
| `vwap` | `VWAP` | `period` | Volume-weighted average price |
| `obv` | `OBV` | — | On-balance volume |
| `resampler` | `Resampler` | `timeframe` | OHLCV resampler (auto-used for multi-TF indicators) |

```python
"indicators": {
    "ema_fast": {"type": "ema", "period": 15, "timeframe": "30m", "source": "close"},
    "rsi_7":   {"type": "rsi", "period": 7, "method": "exponential"},
    "atr_14":  {"type": "atr", "period": 14, "timeframe": "1h"},
}
```

## Declarative Strategy

Define a strategy entirely in JSON — useful for AI agents, config-driven systems, or non-programmers:

```python
from replaybt import BacktestEngine, CSVProvider, DeclarativeStrategy

strategy = DeclarativeStrategy.from_json("trendmaster.json")
engine = BacktestEngine(
    strategy=strategy,
    data=CSVProvider("ETH_1m.csv"),
    config={"initial_equity": 10_000, "indicators": strategy.indicator_config()},
)
results = engine.run()
```

JSON condition types: `crossover`, `crossunder`, `above`, `below`, `above_threshold`, `below_threshold`, `crosses_above`, `crosses_below`. See [`examples/trendmaster.json`](examples/trendmaster.json) for a complete example.

## RL Agent (StepEngine)

```python
from replaybt import StepEngine, CSVProvider, MarketOrder, Side

env = StepEngine(
    data=CSVProvider("ETH_1m.csv"),
    config={"initial_equity": 10_000},
)
obs = env.reset()

while not obs.done:
    action = my_agent(obs)  # -> MarketOrder, LimitOrder, or None
    result = env.step(action)
    obs = result.observation
    # result.reward, result.done, result.info available
```

`StepObservation` gives you: `bar`, `indicators`, `positions`, `equity`, `step_count`, `done`.

## Per-Symbol Config

```python
from replaybt import StrategyConfig

config = StrategyConfig(
    defaults={"ema_fast": 15, "ema_slow": 35, "tp": 0.08, "sl": 0.035},
    overrides={
        "ETH": {"ema_fast": 10, "ema_slow": 30, "tp": 0.12, "sl": 0.04},
        "SUI": {"ema_fast": 8, "tp": 0.12},
    },
)
config.get("tp", symbol="ETH")  # 0.12
config.get("tp", symbol="SOL")  # 0.08 (falls back to default)
```

## Validation

### Static Auditor

Scans backtest source code for 11 common bias patterns:

```python
from replaybt.validation.auditor import audit_file

issues = audit_file("my_backtest.py")
for issue in issues:
    print(f"[{issue.severity}] line {issue.line}: {issue.message}")
```

### Delay Test

Adds +1 bar latency. If PnL drops > 50%, the strategy is timing-sensitive (likely has look-ahead bias):

```python
from replaybt.validation.stress import DelayTest

result = DelayTest(
    strategy_factory=MyStrategy,
    data=data,
    config=config,
    delay_bars=1,
).run()
print(result.verdict)  # "PASS" or "FAIL"
```

### Out-of-Sample Split

Splits data 50/50. If win rate diverges > 10pp or test PnL < 25% of train, it's overfitting:

```python
from replaybt.validation.stress import OOSSplit

result = OOSSplit(
    strategy_factory=MyStrategy,
    data=data,
    config=config,
    split_ratio=0.5,
).run()
print(result.verdict)  # "PASS" or "FAIL"
```

## Optimization

```python
from replaybt.optimize.sweep import ParameterSweep

sweep = ParameterSweep(
    strategy_class=MyStrategy,
    data=CSVProvider("ETH_1m.csv"),
    base_config={"initial_equity": 10_000},
    param_grid={
        "take_profit_pct": [0.04, 0.06, 0.08, 0.10, 0.12],
        "stop_loss_pct": [0.02, 0.025, 0.03, 0.035, 0.04],
    },
    n_workers=10,
)
results = sweep.run()
print(results.summary(top_n=10))

# Access results programmatically
best = results.best("net_pnl", n=5)
df = results.to_dataframe()
```

## API Reference

### Engine

| Class | Description |
|-------|-------------|
| `BacktestEngine` | Main backtest runner — takes strategy + data + config, returns `BacktestResults` |
| `StepEngine` | Gym-like step/reset interface for RL agents |
| `ExecutionModel` | Handles slippage, fees, gap protection |
| `Portfolio` | Tracks positions, equity, and trade history |

### Orders

| Class | Description |
|-------|-------------|
| `MarketOrder` | Fills at next bar's open + slippage |
| `LimitOrder` | Price-triggered with timeout, maker fees, min-position guard |
| `CancelPendingLimitsOrder` | Sentinel to cancel all pending limit orders |

### Data

| Class | Description |
|-------|-------------|
| `CSVProvider` | Reads CSV/Parquet OHLCV files, supports date filtering |
| `ReplayProvider` | Wraps any provider, streams at Nx wall-clock speed |
| `HyperliquidProvider` | Async live data from Hyperliquid |
| `LighterProvider` | Async live data from Lighter |

### Strategy

| Class | Description |
|-------|-------------|
| `Strategy` | Base class — implement `on_bar()`, optionally `on_fill()`, `on_exit()` |
| `DeclarativeStrategy` | JSON-config strategy, no subclassing needed |
| `StrategyConfig` | Per-symbol config with defaults + overrides |

### Reporting

| Class | Description |
|-------|-------------|
| `BacktestResults` | PnL, drawdown, win rate, fees, equity curve, monthly breakdown |

### Validation

| Class / Function | Description |
|------------------|-------------|
| `audit_file()` | Static source code auditor (11 bias checks) |
| `BacktestAuditor` | Auditor class for programmatic access |
| `DelayTest` | +N bar latency stress test |
| `OOSSplit` | Train/test out-of-sample split |

### Optimization

| Class | Description |
|-------|-------------|
| `ParameterSweep` | Parallel grid search with multiprocessing |
| `SweepResults` | Ranked results with `.best()`, `.filter()`, `.to_dataframe()` |

## License

MIT
