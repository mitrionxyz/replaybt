# Data Validation

Catch data quality issues before they corrupt your backtest results.

## DataValidator

Validate a pandas DataFrame:

```python
import pandas as pd
from replaybt import DataValidator

df = pd.read_csv("ETH_1m.csv", parse_dates=["timestamp"])
validator = DataValidator(df, symbol="ETH", timeframe="1m")

issues = validator.validate()
print(validator.report())
```

### Checks Performed

| Check | Severity | What it catches |
|-------|----------|----------------|
| Missing columns | ERROR | OHLCV columns not present |
| Duplicate timestamps | ERROR | Same timestamp appears twice |
| Time gaps | WARNING | Missing bars in the sequence |
| OHLC violations | WARNING | High < Low, Open/Close outside High/Low range |
| Negative values | ERROR | Negative prices or volume |
| Zero values | WARNING | Zero prices (volume can be zero) |

### DataIssue

Each issue returned has:

```python
issue.severity   # "ERROR", "WARNING", "INFO"
issue.check      # issue type identifier
issue.message    # human-readable description
issue.row_index  # row where issue occurs (if applicable)
issue.timestamp  # timestamp of the row (if applicable)
```

## ValidatedProvider

Wrap any provider to validate bars on the fly:

```python
from replaybt import ValidatedProvider, CSVProvider

data = ValidatedProvider(
    inner=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    stop_on_error=False,  # True = raise on first ERROR
)

# Issues are logged as bars are yielded
engine = BacktestEngine(strategy=my_strategy, data=data, config=config)
results = engine.run()
```

## Convenience Functions

```python
from replaybt import validate_dataframe, validate_provider

# Validate a DataFrame directly
issues = validate_dataframe(df, symbol="ETH", timeframe="1m")

# Validate a provider
issues = validate_provider(CSVProvider("ETH_1m.csv"), symbol="ETH")
```
