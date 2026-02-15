# Data Validation

## DataValidator

Validates OHLCV DataFrames for quality issues.

```python
from replaybt import DataValidator

validator = DataValidator(df, symbol="ETH", timeframe="1m")
issues = validator.validate()
print(validator.report())
```

### Constructor

```python
DataValidator(
    df: pd.DataFrame,
    symbol: str = "",
    timeframe: str = "1m",
)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `validate()` | `List[DataIssue]` | Run all checks |
| `report()` | `str` | Formatted report |

### Checks

| Check | Severity | Description |
|-------|----------|-------------|
| Missing columns | ERROR | OHLCV columns not present |
| Duplicate timestamps | ERROR | Same timestamp twice |
| Time gaps | WARNING | Missing bars |
| OHLC violations | WARNING | High < Low, etc. |
| Negative values | ERROR | Negative prices/volume |
| Zero values | WARNING | Zero prices |

---

## DataIssue

A single data quality issue.

| Field | Type | Description |
|-------|------|-------------|
| `severity` | `str` | `"ERROR"`, `"WARNING"`, `"INFO"` |
| `check` | `str` | Issue type identifier |
| `message` | `str` | Human-readable description |
| `row_index` | `Optional[int]` | Row where issue occurs |
| `timestamp` | `Optional[datetime]` | Timestamp of the row |

---

## ValidatedProvider

Wraps a provider and validates bars on the fly.

```python
from replaybt import ValidatedProvider

data = ValidatedProvider(
    inner=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    stop_on_error=False,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inner` | `DataProvider` | required | Provider to validate |
| `symbol` | `str` | `""` | Symbol name |
| `timeframe` | `str` | `"1m"` | Expected timeframe |
| `stop_on_error` | `bool` | `False` | Raise on first ERROR |

---

## Convenience Functions

```python
from replaybt import validate_dataframe, validate_provider

# Validate DataFrame
issues = validate_dataframe(df, symbol="ETH", timeframe="1m")

# Validate provider
issues = validate_provider(my_provider, symbol="ETH")
```
