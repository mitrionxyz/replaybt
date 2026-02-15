# Validation

## BacktestAuditor

Static source code auditor. Scans Python files for 11 common backtest bias patterns.

```python
from replaybt import BacktestAuditor

auditor = BacktestAuditor(source_code, filename="my_backtest.py")
issues = auditor.audit()
print(auditor.report())
```

### Constructor

```python
BacktestAuditor(source: str, filename: str = "<unknown>")
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `audit()` | `List[Issue]` | Run all checks |
| `report()` | `str` | Formatted report |

### Checks

| # | Check | Severity | Description |
|---|-------|----------|-------------|
| 1 | Same-bar execution | CRITICAL | Signal and entry on same bar |
| 2 | Indicator lookahead | WARNING | Pre-calculated without exclusion |
| 3 | Exit price assumptions | WARNING | No gap protection |
| 4 | Missing pending_order | CRITICAL | No pending order system |
| 5 | Time alignment | WARNING | Incomplete bar lookup |
| 6 | Missing fees | WARNING | No slippage/fees |
| 7 | Future data access | CRITICAL | `iloc[i+1]` |
| 8 | Signal/exit same iter | WARNING | Signal and exit in same loop |
| 9 | Missing 1m data | INFO | Not using 1m bars |
| 10 | Wrapper delegation | INFO | Script delegates to another |
| 11 | Scale-in bias | WARNING | Scale-in without timing guard |

---

## Issue

A single audit finding. Frozen dataclass.

| Field | Type | Description |
|-------|------|-------------|
| `severity` | `str` | `"CRITICAL"`, `"WARNING"`, `"INFO"` |
| `line` | `int` | Source line number |
| `code` | `str` | Code snippet |
| `message` | `str` | Explanation |
| `fix` | `str` | Suggested fix |

---

## audit_file

Convenience function to audit a file by path.

```python
from replaybt.validation.auditor import audit_file

issues = audit_file("my_backtest.py")
for issue in issues:
    print(f"[{issue.severity}] line {issue.line}: {issue.message}")
```

---

## DelayTest

Adds +N bar latency to detect timing sensitivity. If PnL drops significantly, the strategy may have look-ahead bias.

```python
from replaybt import DelayTest

result = DelayTest(
    strategy_factory=MyStrategy,   # CLASS, not instance
    data=data_provider,
    config=engine_config,
    delay_bars=1,
    fail_threshold=0.50,           # 50% PnL drop = FAIL
).run()
```

### Constructor

```python
DelayTest(
    strategy_factory: Callable[[], Strategy],
    data: DataProvider,
    config: dict,
    delay_bars: int = 1,
    fail_threshold: float = 0.50,
)
```

### DelayTestResult

| Field | Type | Description |
|-------|------|-------------|
| `normal` | `BacktestResults` | Normal backtest |
| `delayed` | `BacktestResults` | +N bar delay |
| `delay_bars` | `int` | Bars of delay added |
| `pnl_change_pct` | `float` | PnL change percent |
| `wr_change` | `float` | Win rate change |
| `verdict` | `str` | `"PASS"` or `"FAIL"` |

---

## OOSSplit

Train/test out-of-sample split. Detects overfitting by comparing performance on train vs test periods.

```python
from replaybt import OOSSplit

result = OOSSplit(
    strategy_factory=MyStrategy,
    data=data_provider,
    config=engine_config,
    split_ratio=0.5,
    fail_wr_divergence=0.10,
    fail_oos_pct=0.25,
).run()
```

### Constructor

```python
OOSSplit(
    strategy_factory: Callable[[], Strategy],
    data: DataProvider,
    config: dict,
    split_ratio: float = 0.5,
    fail_wr_divergence: float = 0.10,
    fail_oos_pct: float = 0.25,
)
```

### OOSResult

| Field | Type | Description |
|-------|------|-------------|
| `train` | `BacktestResults` | Training period |
| `test` | `BacktestResults` | Test period |
| `split_ratio` | `float` | Split ratio used |
| `verdict` | `str` | `"PASS"` or `"FAIL"` |
| `issues` | `List[str]` | Failure reasons |
