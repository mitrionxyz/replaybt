# Live Providers

Stream real-time data from exchanges for live trading or replay at accelerated speed.

```bash
pip install replaybt[live]  # requires aiohttp, websockets
```

## ReplayProvider

Replay historical data at Nx wall-clock speed. Useful for visual debugging or demo purposes.

```python
from replaybt import ReplayProvider, CSVProvider

data = ReplayProvider(
    inner=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    speed=60,  # 60x speed: 1m bar = 1 second wall-clock
)

for bar in data:
    print(f"{bar.timestamp} close={bar.close}")
    # Each bar arrives 1 second apart at 60x speed
```

### Speed Settings

| Speed | Meaning |
|-------|---------|
| `0` | Instant (no delay) |
| `1` | Real-time (1m bar = 60s delay) |
| `60` | 60x speed (1m bar = 1s delay) |
| `3600` | 3600x speed (1h of data per second) |

### Callback

Execute a function on each bar:

```python
data = ReplayProvider(
    inner=CSVProvider("ETH_1m.csv"),
    speed=60,
    on_bar=lambda bar: print(f"Price: {bar.close}"),
)
```

## HyperliquidProvider

Async real-time data streaming from Hyperliquid exchange:

```python
from replaybt import HyperliquidProvider

provider = HyperliquidProvider()
```

## LighterProvider

Async real-time data streaming from Lighter exchange:

```python
from replaybt import LighterProvider

provider = LighterProvider()
```

## AsyncDataProvider

Base class for building custom async live data providers:

```python
from replaybt import AsyncDataProvider

class MyLiveProvider(AsyncDataProvider):
    # Implement async data streaming
    ...
```

!!! note
    Live providers are designed for integration with live trading bots. For backtesting, use `CSVProvider` or exchange fetchers with historical data.
