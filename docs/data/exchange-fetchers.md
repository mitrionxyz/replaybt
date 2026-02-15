# Exchange Fetchers

Fetch historical OHLCV data directly from exchange APIs.

```bash
pip install replaybt[data]  # requires requests
```

## BinanceProvider

```python
from replaybt import BinanceProvider

data = BinanceProvider(
    symbol="ETHUSDT",
    timeframe="1m",
    start="2024-01-01",
    end="2024-12-31",
)

# Use like any other provider
engine = BacktestEngine(strategy=my_strategy, data=data, config=config)
results = engine.run()
```

### Parameters

```python
BinanceProvider(
    symbol="ETHUSDT",       # Binance trading pair
    timeframe="1m",         # "1m", "5m", "15m", "30m", "1h", "4h", "1d"
    start="2024-01-01",     # start date (inclusive)
    end="2024-12-31",       # end date (inclusive)
)
```

## BybitProvider

```python
from replaybt import BybitProvider

data = BybitProvider(
    symbol="ETHUSDT",
    timeframe="1m",
    start="2024-01-01",
    end="2024-12-31",
)
```

### Parameters

Same interface as `BinanceProvider`:

```python
BybitProvider(
    symbol="ETHUSDT",       # Bybit trading pair
    timeframe="1m",         # "1m", "5m", "15m", "30m", "1h", "4h", "1d"
    start="2024-01-01",     # start date (inclusive)
    end="2024-12-31",       # end date (inclusive)
)
```

## Rate Limits

Both providers handle pagination automatically. For large date ranges with 1m data, fetching may take a few minutes due to API rate limits.

## Combining with CachedProvider

Avoid re-fetching on repeated runs:

```python
from replaybt import CachedProvider

data = CachedProvider(
    BinanceProvider("ETHUSDT", start="2024-01-01", end="2024-12-31")
)
```

The first run fetches from the API; subsequent iterations use the cached bars.
