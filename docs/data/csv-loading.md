# CSV & Parquet Loading

`CSVProvider` loads OHLCV data from CSV or Parquet files.

## Basic Usage

```python
from replaybt import CSVProvider

data = CSVProvider("ETH_1m.csv", symbol_name="ETH")
```

## Expected Columns

| Column | Required | Type |
|--------|----------|------|
| `timestamp` | yes | datetime string or unix timestamp |
| `open` | yes | float |
| `high` | yes | float |
| `low` | yes | float |
| `close` | yes | float |
| `volume` | yes | float |

Example CSV:

```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,2300.50,2301.20,2299.80,2300.90,125.5
2024-01-01 00:01:00,2300.90,2302.00,2300.50,2301.80,98.3
```

## Parameters

```python
CSVProvider(
    path="ETH_1m.csv",          # path to CSV or Parquet file
    symbol_name="ETH",          # symbol name for Bar objects
    timeframe="1m",             # bar timeframe
    start="2024-01-01",         # optional start date filter
    end="2024-12-31",           # optional end date filter
    timestamp_col="timestamp",  # name of timestamp column
)
```

## Date Filtering

Filter to a specific date range:

```python
# Full year 2024
data = CSVProvider("ETH_1m.csv", symbol_name="ETH", start="2024-01-01", end="2024-12-31")

# Last 6 months
data = CSVProvider("ETH_1m.csv", symbol_name="ETH", start="2024-07-01")
```

## Parquet Files

CSVProvider auto-detects Parquet files by extension:

```python
data = CSVProvider("ETH_1m.parquet", symbol_name="ETH")
```

Parquet loads faster than CSV for large datasets.

## Custom Timestamp Column

If your timestamp column has a different name:

```python
data = CSVProvider("data.csv", timestamp_col="time")
```

## Reset

Call `reset()` to re-iterate from the beginning (useful in parameter sweeps):

```python
data = CSVProvider("ETH_1m.csv", symbol_name="ETH")

# First backtest
engine1 = BacktestEngine(strategy=MyStrategy(), data=data, config=config)
results1 = engine1.run()

# Reset for second backtest
data.reset()
engine2 = BacktestEngine(strategy=OtherStrategy(), data=data, config=config)
results2 = engine2.run()
```
