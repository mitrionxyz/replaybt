# Per-Symbol Config

`StrategyConfig` provides defaults with per-symbol overrides. Useful when the same strategy runs on multiple assets with different parameters.

## Quick Start

```python
from replaybt import StrategyConfig

config = StrategyConfig(
    defaults={
        "ema_fast": 15,
        "ema_slow": 35,
        "tp": 0.08,
        "sl": 0.035,
        "chop": 0.011,
    },
    overrides={
        "ETH": {"ema_fast": 10, "ema_slow": 30, "tp": 0.12, "sl": 0.04},
        "SUI": {"ema_fast": 8, "tp": 0.12},
    },
)
```

## Accessing Values

```python
# With symbol — checks overrides first, falls back to defaults
config.get("tp", symbol="ETH")   # 0.12 (ETH override)
config.get("tp", symbol="SOL")   # 0.08 (default — no SOL override)
config.get("chop", symbol="ETH") # 0.011 (default — ETH doesn't override chop)

# Without symbol — always returns default
config.get("tp")  # 0.08

# With fallback
config.get("missing_key", default=42)  # 42
```

## Merged Config for a Symbol

```python
merged = config.for_symbol("ETH")
# {"ema_fast": 10, "ema_slow": 30, "tp": 0.12, "sl": 0.04, "chop": 0.011}

merged = config.for_symbol("SOL")
# {"ema_fast": 15, "ema_slow": 35, "tp": 0.08, "sl": 0.035, "chop": 0.011}
```

## Listing Symbols

```python
config.symbols()  # ["ETH", "SUI"]
```

## Using in a Strategy

```python
from replaybt import Strategy, StrategyConfig, MarketOrder, Side

class TrendMaster(Strategy):
    def configure(self, config):
        self._params = StrategyConfig(
            defaults={"tp": 0.08, "sl": 0.035},
            overrides={
                "ETH": {"tp": 0.12, "sl": 0.04},
                "SUI": {"tp": 0.12},
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
    strategy=TrendMaster(),
    assets={
        "ETH": CSVProvider("ETH_1m.csv", symbol_name="ETH"),
        "SOL": CSVProvider("SOL_1m.csv", symbol_name="SOL"),
        "SUI": CSVProvider("SUI_1m.csv", symbol_name="SUI"),
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
