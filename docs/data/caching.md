# Caching

`CachedProvider` wraps any data provider and stores bars in memory after the first iteration. Useful for parameter sweeps where you run the same data multiple times.

## Usage

```python
from replaybt import CachedProvider, CSVProvider

data = CachedProvider(CSVProvider("ETH_1m.csv", symbol_name="ETH"))

# First iteration: reads from disk, caches in memory
engine1 = BacktestEngine(strategy=Strategy1(), data=data, config=config)
results1 = engine1.run()

# Second iteration: reads from memory (fast)
data.reset()
engine2 = BacktestEngine(strategy=Strategy2(), data=data, config=config)
results2 = engine2.run()
```

## With Exchange Fetchers

Especially useful with API-based providers to avoid redundant network calls:

```python
from replaybt import CachedProvider, BinanceProvider

data = CachedProvider(
    BinanceProvider("ETHUSDT", start="2024-01-01", end="2024-12-31")
)

# First run fetches from Binance API
# Subsequent runs use cached bars
```

## In Parameter Sweeps

`ParameterSweep` handles caching internally — you don't need to wrap your provider manually:

```python
from replaybt.optimize.sweep import ParameterSweep

sweep = ParameterSweep(
    strategy_class=MyStrategy,
    data=CSVProvider("ETH_1m.csv"),  # loaded once, shared across workers
    base_config=config,
    param_grid=grid,
)
```
