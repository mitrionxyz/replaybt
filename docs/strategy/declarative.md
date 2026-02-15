# Declarative Strategy

Define a strategy entirely in JSON — no Python subclassing needed. Useful for AI agents, config-driven systems, or non-programmers.

## Quick Start

```python
from replaybt import BacktestEngine, CSVProvider, DeclarativeStrategy

strategy = DeclarativeStrategy.from_json("trend_follower.json")
engine = BacktestEngine(
    strategy=strategy,
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    config={
        "initial_equity": 10_000,
        "indicators": strategy.indicator_config(),
    },
)
results = engine.run()
```

## JSON Format

```json
{
  "name": "TrendFollower",
  "indicators": {
    "ema_fast": {"type": "ema", "period": 10, "timeframe": "15m", "source": "close"},
    "ema_slow": {"type": "ema", "period": 50, "timeframe": "15m", "source": "close"},
    "ema_fast_1h": {"type": "ema", "period": 20, "timeframe": "1h", "source": "close"},
    "ema_slow_1h": {"type": "ema", "period": 50, "timeframe": "1h", "source": "close"}
  },
  "entry": {
    "long": {
      "conditions": [
        {"type": "crossover", "fast": "ema_fast", "slow": "ema_slow"},
        {"type": "above", "left": "ema_fast_1h", "right": "ema_slow_1h"}
      ]
    },
    "short": {
      "conditions": [
        {"type": "crossunder", "fast": "ema_fast", "slow": "ema_slow"},
        {"type": "below", "left": "ema_fast_1h", "right": "ema_slow_1h"}
      ]
    }
  },
  "exit": {
    "take_profit_pct": 0.06,
    "stop_loss_pct": 0.03,
    "breakeven_trigger_pct": 0.02,
    "breakeven_lock_pct": 0.005
  }
}
```

## Condition Types

### Crossover / Crossunder

Signal when one indicator crosses above/below another:

```json
{"type": "crossover", "fast": "ema_fast", "slow": "ema_slow"}
{"type": "crossunder", "fast": "ema_fast", "slow": "ema_slow"}
```

### Comparison

Compare two indicator values:

```json
{"type": "above", "left": "ema_fast_1h", "right": "ema_slow_1h"}
{"type": "below", "left": "ema_fast_1h", "right": "ema_slow_1h"}
```

You can also compare against `bar.close`, `bar.open`, `bar.high`, `bar.low`:

```json
{"type": "above", "left": "ema_fast", "right": "bar.close"}
```

### Threshold

Compare an indicator against a fixed value:

```json
{"type": "above_threshold", "indicator": "rsi", "threshold": 70}
{"type": "below_threshold", "indicator": "rsi", "threshold": 30}
{"type": "crosses_above", "indicator": "rsi", "threshold": 25}
{"type": "crosses_below", "indicator": "rsi", "threshold": 75}
```

## Exit Configuration

```json
{
  "exit": {
    "take_profit_pct": 0.06,
    "stop_loss_pct": 0.03,
    "breakeven_trigger_pct": 0.02,
    "breakeven_lock_pct": 0.005,
    "trailing_stop_pct": 0.02,
    "trailing_stop_activation_pct": 0.03,
    "partial_tp_pct": 0.5,
    "partial_tp_new_tp_pct": 0.12
  }
}
```

## Loading Methods

```python
# From JSON file
strategy = DeclarativeStrategy.from_json("config.json")

# From Python dict
strategy = DeclarativeStrategy.from_config({
    "name": "MyStrategy",
    "indicators": {...},
    "entry": {...},
    "exit": {...},
})
```

## Getting Indicator Config

`indicator_config()` returns the indicators dict in the format expected by the engine:

```python
strategy = DeclarativeStrategy.from_json("config.json")
indicator_cfg = strategy.indicator_config()
# {"ema_fast": {"type": "ema", "period": 15, ...}, ...}
```

Pass it to the engine config:

```python
engine = BacktestEngine(
    strategy=strategy,
    data=data,
    config={"indicators": strategy.indicator_config()},
)
```
