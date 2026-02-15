# Data

replaybt works with any source of OHLCV bars. Data providers are iterators that yield `Bar` objects — implement one method and plug in any data source.

## Provider Types

| Provider | Source | Install |
|----------|--------|---------|
| [CSVProvider](csv-loading.md) | CSV or Parquet files | included |
| [BinanceProvider](exchange-fetchers.md) | Binance API | `pip install replaybt[data]` |
| [BybitProvider](exchange-fetchers.md) | Bybit API | `pip install replaybt[data]` |
| [CachedProvider](caching.md) | Wraps any provider with caching | included |
| [ValidatedProvider](validation.md) | Wraps any provider with quality checks | included |
| [ReplayProvider](live-providers.md) | Nx speed replay for debugging | included |
| [HyperliquidProvider](live-providers.md) | Live Hyperliquid stream | `pip install replaybt[live]` |
| [LighterProvider](live-providers.md) | Live Lighter stream | `pip install replaybt[live]` |

## Expected Data Format

All providers must yield `Bar` objects with:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `datetime` | Bar open time |
| `open` | `float` | Open price |
| `high` | `float` | High price |
| `low` | `float` | Low price |
| `close` | `float` | Close price |
| `volume` | `float` | Volume |
| `symbol` | `str` | Asset symbol |
| `timeframe` | `str` | Bar timeframe (e.g., `"1m"`) |

## Custom Provider

Implement `DataProvider` to use any data source:

```python
from replaybt import DataProvider, Bar

class MyProvider(DataProvider):
    def __init__(self, data):
        self._data = data

    def __iter__(self):
        for row in self._data:
            yield Bar(
                timestamp=row["time"],
                open=row["o"],
                high=row["h"],
                low=row["l"],
                close=row["c"],
                volume=row["v"],
                symbol="MY_ASSET",
            )

    def symbol(self):
        return "MY_ASSET"

    def timeframe(self):
        return "1m"
```
