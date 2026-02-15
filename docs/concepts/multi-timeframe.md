# Multi-Timeframe

## The Approach

Feed 1-minute data to the engine. Compute indicators on higher timeframes (5m, 15m, 30m, 1h, etc.) automatically. The engine handles resampling internally.

```python
config = {
    "indicators": {
        # Computed on 30-minute bars (resampled from 1m)
        "ema_fast": {"type": "ema", "period": 15, "timeframe": "30m", "source": "close"},
        "ema_slow": {"type": "ema", "period": 35, "timeframe": "30m", "source": "close"},

        # Computed on 1-hour bars
        "chop": {"type": "chop", "period": 14, "timeframe": "1h"},

        # Computed on 1-minute bars (default — no timeframe key needed)
        "rsi": {"type": "rsi", "period": 7},
    },
}
```

## How Resampling Works

The `IndicatorManager` accumulates 1-minute bars and builds higher-timeframe bars internally:

```
1m bars arrive:  [00:00, 00:01, ..., 00:29]
                          ↓
30m bar formed:  [00:00 open, max(highs), min(lows), 00:29 close, sum(volumes)]
                          ↓
Indicator updated with completed 30m bar
                          ↓
Value available in indicators dict
```

Indicators on higher timeframes update only when a complete higher-timeframe bar forms. Between updates, they return the previous value.

## Supported Timeframes

`"1m"`, `"5m"`, `"15m"`, `"30m"`, `"1h"`, `"2h"`, `"4h"`, `"1d"`

## Completed Bar Rule

Indicators always use the **last completed** higher-timeframe bar, never the in-progress one:

```
Time: 10:15
  30m indicator uses the bar [09:30 - 10:00]  (completed)
  NOT the bar [10:00 - 10:30]  (still forming)
```

This is enforced automatically by the `IndicatorManager`. You don't need to manage offsets yourself.

## Batch Resampling

For pre-computing indicators on DataFrames (useful in parameter sweeps), use the `Resampler` utility:

```python
from replaybt import Resampler
import pandas as pd

df_1m = pd.read_csv("ETH_1m.csv", parse_dates=["timestamp"])

# Resample to 30m bars
df_30m = Resampler.resample(df_1m, "30m")

# Add indicators to the resampled DataFrame
df_30m = Resampler.add_ema(df_30m, period=15, col="close", name="ema_fast")
df_30m = Resampler.add_ema(df_30m, period=35, col="close", name="ema_slow")
df_30m = Resampler.add_rsi_wilder(df_30m, period=14, name="rsi_14")
df_30m = Resampler.add_chop(df_30m, period=14, name="chop_14")
```

## Mixing Timeframes

You can mix indicators from different timeframes freely. The engine tracks each timeframe's resampling state independently:

```python
config = {
    "indicators": {
        "ema_30m": {"type": "ema", "period": 15, "timeframe": "30m", "source": "close"},
        "rsi_1h":  {"type": "rsi", "period": 14, "timeframe": "1h"},
        "atr_1m":  {"type": "atr", "period": 14},  # 1m default
    },
}
```

In `on_bar()`, all indicator values are available in a single dict:

```python
def on_bar(self, bar, indicators, positions):
    ema = indicators.get("ema_30m")      # updates every 30 bars
    rsi = indicators.get("rsi_1h")       # updates every 60 bars
    atr = indicators.get("atr_1m")       # updates every bar
```
