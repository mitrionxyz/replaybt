# Per-Symbol Config

`StrategyConfig` provides defaults with per-symbol overrides. Useful when the same strategy runs on multiple assets with different parameters.

## Quick Start

```python
from replaybt import StrategyConfig

config = StrategyConfig(
    defaults={
        "ema_fast": 10,
        "ema_slow": 50,
        "tp": 0.06,
        "sl": 0.03,
    },
    overrides={
        "ETH": {"ema_fast": 12, "ema_slow": 26, "tp": 0.08, "sl": 0.04},
        "BNB": {"ema_fast": 8, "tp": 0.10},
    },
)
```

## Accessing Values

```python
# With symbol — checks overrides first, falls back to defaults
config.get("tp", symbol="ETH")   # 0.08 (ETH override)
config.get("tp", symbol="SOL")   # 0.06 (default — no SOL override)

# Without symbol — always returns default
config.get("tp")  # 0.06

# With fallback
config.get("missing_key", default=42)  # 42
```

## Merged Config for a Symbol

```python
merged = config.for_symbol("ETH")
# {"ema_fast": 12, "ema_slow": 26, "tp": 0.08, "sl": 0.04}

merged = config.for_symbol("SOL")
# {"ema_fast": 10, "ema_slow": 50, "tp": 0.06, "sl": 0.03}
```

## Listing Symbols

```python
config.symbols()  # ["ETH", "BNB"]
```

## Using in a Strategy

```python
from replaybt import Strategy, StrategyConfig, MarketOrder, Side

class TrendFollower(Strategy):
    def configure(self, config):
        self._params = StrategyConfig(
            defaults={"tp": 0.06, "sl": 0.03},
            overrides={
                "ETH": {"tp": 0.08, "sl": 0.04},
                "BNB": {"tp": 0.10},
            },
        )
        self._prev = {}

    def on_bar(self, bar, indicators, positions):
        sym = bar.symbol
        tp = self._params.get("tp", symbol=sym)
        sl = self._params.get("sl", symbol=sym)

        # ... crossover logic ...

        if not positions and signal:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=tp,
                stop_loss_pct=sl,
            )
        return None
```

## With MultiAssetEngine

`StrategyConfig` pairs naturally with `MultiAssetEngine` for multi-symbol backtests where each asset needs different parameters:

```python
from replaybt import MultiAssetEngine, CSVProvider

engine = MultiAssetEngine(
    strategy=TrendFollower(),
    assets={
        "ETH": CSVProvider("ETH_1m.csv", symbol_name="ETH"),
        "SOL": CSVProvider("SOL_1m.csv", symbol_name="SOL"),
        "BNB": CSVProvider("BNB_1m.csv", symbol_name="BNB"),
    },
    config={
        "initial_equity": 10_000,
        "indicators": {
            "ema_fast": {"type": "ema", "period": 15, "source": "close"},
            "ema_slow": {"type": "ema", "period": 35, "source": "close"},
        },
        "symbol_configs": {
            "ETH": {
                "indicators": {
                    "ema_fast": {"type": "ema", "period": 10, "source": "close"},
                    "ema_slow": {"type": "ema", "period": 30, "source": "close"},
                },
            },
        },
    },
)
```
