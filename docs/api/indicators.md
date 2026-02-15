# Indicators

## IndicatorManager

Manages multiple indicators with automatic multi-timeframe resampling.

```python
from replaybt import IndicatorManager

manager = IndicatorManager({
    "ema_fast": {"type": "ema", "period": 15, "timeframe": "30m", "source": "close"},
    "rsi_7":   {"type": "rsi", "period": 7, "method": "wilder"},
    "atr_14":  {"type": "atr", "period": 14, "timeframe": "1h"},
})
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `update(bar)` | `None` | Feed a 1m bar |
| `get(name)` | `Any` | Get indicator value |
| `all()` | `Dict[str, Any]` | All values as dict |
| `ready()` | `bool` | All indicators ready |
| `reset()` | `None` | Reset all state |

---

## Indicator (ABC)

Base class for all indicators.

### Constructor

```python
Indicator(name: str, period: int = 14)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `update(bar)` | `None` | Process completed bar |
| `value()` | `Any` | Current value |
| `reset()` | `None` | Reset state |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `ready` | `bool` | Enough data for valid output |

### Static Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `batch_ema(series, period)` | `Series` | EMA on pandas Series |
| `batch_rsi_wilder(closes, period)` | `Series` | Wilder's RSI |
| `batch_rsi_simple(closes, period)` | `Series` | Simple RSI |

---

## EMA

Exponential Moving Average.

```python
{"type": "ema", "period": 15, "source": "close", "timeframe": "30m"}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | `int` | `14` | EMA window |
| `source` | `str` | `"close"` | Price field (`close`, `open`, `high`, `low`) |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

**Value:** `Optional[float]`

---

## SMA

Simple Moving Average.

```python
{"type": "sma", "period": 14, "source": "close", "timeframe": "30m"}
```

Same parameters as EMA. **Value:** `Optional[float]`

---

## RSI

Relative Strength Index. Supports Wilder's exponential or simple rolling.

```python
{"type": "rsi", "period": 7, "method": "wilder", "source": "close", "timeframe": "30m"}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | `int` | `14` | RSI window |
| `method` | `str` | `"wilder"` | `"wilder"` (exponential) or `"simple"` (rolling) |
| `source` | `str` | `"close"` | Price field |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

**Value:** `Optional[float]` (0-100)

---

## ATR

Average True Range.

```python
{"type": "atr", "period": 14, "mode": "sma", "timeframe": "1h"}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | `int` | `14` | ATR window |
| `mode` | `str` | `"sma"` | `"sma"` or `"wilder"` |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

**Value:** `Optional[float]`

---

## CHOP

Choppiness Index. High values = choppy/ranging, low values = trending.

```python
{"type": "chop", "period": 14, "atr_mode": "sma", "timeframe": "1h"}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | `int` | `14` | Window |
| `atr_mode` | `str` | `"sma"` | ATR calculation mode |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

**Value:** `Optional[float]` (expressed as ATR/Close ratio)

---

## BollingerBands

Upper, middle, lower bands + bandwidth + %B.

```python
{"type": "bollinger", "period": 20, "num_std": 2.0, "source": "close"}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | `int` | `20` | SMA window |
| `num_std` | `float` | `2.0` | Standard deviation multiplier |
| `source` | `str` | `"close"` | Price field |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

**Value:** `Optional[Dict[str, float]]` with keys: `upper`, `middle`, `lower`, `bandwidth`, `pct_b`

---

## MACD

Moving Average Convergence Divergence.

```python
{"type": "macd", "fast_period": 12, "slow_period": 26, "signal_period": 9, "source": "close"}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `fast_period` | `int` | `12` | Fast EMA period |
| `slow_period` | `int` | `26` | Slow EMA period |
| `signal_period` | `int` | `9` | Signal line period |
| `source` | `str` | `"close"` | Price field |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

**Value:** `Optional[Dict[str, float]]` with keys: `macd`, `signal`, `histogram`

---

## Stochastic

Stochastic Oscillator (%K and %D).

```python
{"type": "stochastic", "k_period": 14, "d_period": 3, "smooth_k": 3}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `k_period` | `int` | `14` | %K lookback |
| `d_period` | `int` | `3` | %D smoothing |
| `smooth_k` | `int` | `3` | %K smoothing (1 = fast stochastic) |
| `timeframe` | `str` | `"1m"` | Bar timeframe |

**Value:** `Optional[Dict[str, float]]` with keys: `k`, `d`

---

## VWAP

Volume-Weighted Average Price. Resets daily at midnight UTC.

```python
{"type": "vwap"}
```

**Value:** `Optional[float]`

---

## OBV

On-Balance Volume. Running sum: +volume on up bars, -volume on down bars.

```python
{"type": "obv"}
```

**Value:** `float`

---

## Resampler

Batch resampling utilities for DataFrame-based workflows.

### Static Methods

```python
from replaybt import Resampler

# Resample 1m DataFrame to higher timeframe
df_30m = Resampler.resample(df_1m, "30m")

# Add indicators
df = Resampler.add_ema(df, period=15, col="close", name="ema_15")
df = Resampler.add_rsi_wilder(df, period=14, col="close", name="rsi_14")
df = Resampler.add_rsi_simple(df, period=14, col="close", name="rsi_14_simple")
df = Resampler.add_chop(df, period=14, name="chop_14")
```

| Method | Description |
|--------|-------------|
| `resample(df, timeframe)` | Resample to `"5m"`, `"15m"`, `"30m"`, `"1h"`, `"2h"`, `"4h"`, `"1d"` |
| `add_ema(df, period, col, name)` | Add EMA column |
| `add_rsi_wilder(df, period, col, name)` | Add Wilder's RSI column |
| `add_rsi_simple(df, period, col, name)` | Add Simple RSI column |
| `add_chop(df, period, name)` | Add CHOP column |
