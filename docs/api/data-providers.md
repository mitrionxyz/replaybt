# Data Providers

## DataProvider (ABC)

Abstract base for all data providers. Implement `__iter__`, `symbol`, and `timeframe`.

```python
from replaybt import DataProvider, Bar

class MyProvider(DataProvider):
    def __iter__(self):
        yield Bar(...)

    def symbol(self):
        return "MY_ASSET"

    def timeframe(self):
        return "1m"

    def reset(self):
        pass  # optional: reset to beginning
```

### Abstract Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `__iter__()` | `Iterator[Bar]` | Yield bars chronologically |
| `symbol()` | `str` | Asset symbol |
| `timeframe()` | `str` | Base timeframe |

### Optional Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `reset()` | `None` | Reset to beginning |

---

## CSVProvider

Load OHLCV data from CSV or Parquet files.

```python
from replaybt import CSVProvider

data = CSVProvider(
    path="ETH_1m.csv",
    symbol_name="ETH",
    timeframe="1m",
    start="2024-01-01",
    end="2024-12-31",
    timestamp_col="timestamp",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str \| Path` | required | File path (CSV or Parquet) |
| `symbol_name` | `str` | `""` | Symbol name for Bar objects |
| `timeframe` | `str` | `"1m"` | Bar timeframe |
| `start` | `Optional[str]` | `None` | Start date filter |
| `end` | `Optional[str]` | `None` | End date filter |
| `timestamp_col` | `str` | `"timestamp"` | Timestamp column name |

---

## CachedProvider

Wraps any provider. Caches bars in memory after first iteration.

```python
from replaybt import CachedProvider

data = CachedProvider(CSVProvider("ETH_1m.csv", symbol_name="ETH"))
```

---

## BinanceProvider

Fetch historical data from Binance API. Requires `pip install replaybt[data]`.

```python
from replaybt import BinanceProvider

data = BinanceProvider(
    symbol="ETHUSDT",
    timeframe="1m",
    start="2024-01-01",
    end="2024-12-31",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | `str` | required | Trading pair |
| `timeframe` | `str` | `"1m"` | Bar timeframe |
| `start` | `Optional[str]` | `None` | Start date |
| `end` | `Optional[str]` | `None` | End date |

---

## BybitProvider

Fetch historical data from Bybit API. Requires `pip install replaybt[data]`.

```python
from replaybt import BybitProvider

data = BybitProvider(
    symbol="ETHUSDT",
    timeframe="1m",
    start="2024-01-01",
    end="2024-12-31",
)
```

Same parameters as `BinanceProvider`.

---

## ReplayProvider

Wraps any provider. Adds `time.sleep()` between bars for Nx speed replay.

```python
from replaybt import ReplayProvider

data = ReplayProvider(
    inner=CSVProvider("ETH_1m.csv"),
    speed=60,       # 60x speed
    on_bar=None,    # optional callback
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inner` | `DataProvider` | required | Wrapped provider |
| `speed` | `float` | `60` | Replay speed multiplier |
| `on_bar` | `Optional[Callable[[Bar], None]]` | `None` | Per-bar callback |

---

## AsyncDataProvider

Base class for async live data providers.

---

## HyperliquidProvider

Real-time data from Hyperliquid exchange. Requires `pip install replaybt[live]`.

---

## LighterProvider

Real-time data from Lighter exchange. Requires `pip install replaybt[live]`.
