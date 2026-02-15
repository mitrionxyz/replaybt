# API Reference

Complete reference for all public classes, methods, and parameters.

## Module Map

| Module | Classes |
|--------|---------|
| [Engine](engine.md) | `BacktestEngine`, `MultiAssetEngine`, `StepEngine`, `ExecutionModel`, `Portfolio` |
| [Orders](orders.md) | `Order`, `MarketOrder`, `LimitOrder`, `StopOrder`, `CancelPendingLimitsOrder` |
| [Data Types](data-types.md) | `Bar`, `Fill`, `Position`, `Trade`, `Side`, `OrderType`, `ExitReason`, `PendingOrder` |
| [Data Providers](data-providers.md) | `DataProvider`, `CSVProvider`, `CachedProvider`, `BinanceProvider`, `BybitProvider`, `ReplayProvider` |
| [Data Validation](data-validation.md) | `DataValidator`, `DataIssue`, `ValidatedProvider` |
| [Indicators](indicators.md) | `EMA`, `SMA`, `RSI`, `ATR`, `CHOP`, `BollingerBands`, `MACD`, `Stochastic`, `VWAP`, `OBV`, `IndicatorManager`, `Resampler` |
| [Strategy](strategy.md) | `Strategy`, `DeclarativeStrategy`, `StrategyConfig` |
| [Reporting](reporting.md) | `BacktestResults`, `MultiAssetResults`, `MonthStats` |
| [Validation](validation.md) | `BacktestAuditor`, `Issue`, `DelayTest`, `OOSSplit` |
| [Optimization](optimization.md) | `ParameterSweep`, `SweepResults` |
| [Sizing](sizing.md) | `PositionSizer`, `FixedSizer`, `EquityPctSizer`, `RiskPctSizer`, `KellySizer` |
| [Analysis](analysis.md) | `MonteCarlo`, `WalkForward` |
| [Plots](plots.md) | `plot_equity`, `plot_drawdown`, `plot_trades`, `plot_monthly_heatmap`, `plot_exit_breakdown`, `plot_multi_equity`, `plot_sweep_heatmap` |

## Import Paths

All public classes are importable from `replaybt` directly:

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, MarketOrder, Side
```

For less common imports:

```python
from replaybt.validation.auditor import audit_file
from replaybt.validation.stress import DelayTest, OOSSplit
from replaybt.optimize.sweep import ParameterSweep
from replaybt.analysis.plots import plot_equity
```
