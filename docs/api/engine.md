# Engine

## BacktestEngine

Main backtest runner. Takes a strategy, data provider, and config; returns `BacktestResults`.

```python
from replaybt import BacktestEngine

engine = BacktestEngine(
    strategy=my_strategy,
    data=my_data,
    config={...},
)
results = engine.run()
```

### Constructor

```python
BacktestEngine(
    strategy: Strategy,
    data: DataProvider,
    config: Optional[Dict] = None,
)
```

### Config Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `initial_equity` | `float` | `10000` | Starting capital |
| `default_size_usd` | `float` | `10000` | Default position size in USD |
| `max_positions` | `int` | `1` | Maximum concurrent positions |
| `slippage` | `float` | `0.0002` | Per-side slippage (0.02%) |
| `taker_fee` | `float` | `0.00015` | Per-side taker fee (0.015%) |
| `maker_fee` | `float` | `0.0` | Per-side maker fee |
| `indicators` | `Dict` | `{}` | Indicator configurations |
| `skip_signal_on_close` | `bool` | `True` | Skip `on_bar` when position closes |
| `same_direction_only` | `bool` | `True` | Reject opposite-direction orders |
| `sizer` | `PositionSizer` | `None` | Custom position sizer |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `BacktestResults` | Execute backtest |
| `on(event, callback)` | `None` | Register event listener |
| `remove_listener(event, callback)` | `None` | Remove event listener |

### Events

| Event | Callback Signature | When |
|-------|-------------------|------|
| `"bar"` | `(bar: Bar)` | Every bar |
| `"fill"` | `(fill: Fill)` | Order fills |
| `"exit"` | `(fill: Fill, trade: Trade)` | Position closes |
| `"signal"` | `(order: Order)` | Signal emitted |

---

## MultiAssetEngine

Multi-symbol runner with time-synchronized bar processing and portfolio-level metrics.

```python
from replaybt import MultiAssetEngine

engine = MultiAssetEngine(
    strategy=my_strategy,
    assets={"ETH": eth_data, "SOL": sol_data},
    config={...},
)
results = engine.run()  # -> MultiAssetResults
```

### Constructor

```python
MultiAssetEngine(
    strategy: Strategy,
    assets: Dict[str, DataProvider],
    config: Optional[Dict] = None,
)
```

### Additional Config Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `symbol_configs` | `Dict[str, Dict]` | `{}` | Per-symbol config overrides |
| `max_total_exposure_usd` | `float` | `None` | Portfolio-level exposure cap |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `MultiAssetResults` | Execute multi-asset backtest |

---

## StepEngine

Gym-like step/reset interface for RL agents.

```python
from replaybt import StepEngine

env = StepEngine(data=my_data, config={...})
obs = env.reset()
while not obs.done:
    result = env.step(action)
    obs = result.observation
```

### Constructor

```python
StepEngine(
    data: DataProvider,
    config: Optional[Dict] = None,
    strategy: Optional[Strategy] = None,
)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `reset()` | `StepObservation` | Start new episode |
| `step(action)` | `StepResult` | Process one bar |
| `done()` | `bool` | Episode finished? |
| `close()` | `None` | Cleanup |

### StepObservation

| Field | Type | Description |
|-------|------|-------------|
| `bar` | `Bar` | Current bar |
| `indicators` | `Dict[str, Any]` | Indicator values |
| `positions` | `List[Position]` | Open positions |
| `equity` | `float` | Current equity |
| `step_count` | `int` | Steps taken |
| `done` | `bool` | Episode finished |

### StepResult

| Field | Type | Description |
|-------|------|-------------|
| `observation` | `StepObservation` | Next state |
| `reward` | `float` | PnL change this step |
| `done` | `bool` | Episode finished |
| `info` | `Dict[str, Any]` | Metadata |

---

## ExecutionModel

Handles slippage, fees, and gap protection.

### Constructor

```python
ExecutionModel(
    slippage: float = 0.0002,
    taker_fee: float = 0.00015,
    maker_fee: float = 0.0,
)
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `apply_entry_slippage(price, side)` | `float` | Adverse entry slippage |
| `apply_exit_slippage(price, side)` | `float` | Adverse exit slippage |
| `calc_fees(size_usd, is_maker)` | `float` | Fee for one side |
| `check_exit(pos, bar)` | `Tuple[Optional[float], Optional[str]]` | Check if position should exit |

---

## Portfolio

Tracks positions, equity, trades, and drawdown.

### Constructor

```python
Portfolio(
    initial_equity: float = 10_000.0,
    default_size_usd: float = 10_000.0,
    execution: Optional[ExecutionModel] = None,
    max_positions: int = 1,
    sizer: Optional[PositionSizer] = None,
)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `has_position` | `bool` | Any open positions |
| `position` | `Optional[Position]` | First position |
| `position_count` | `int` | Number of open positions |
| `equity` | `float` | Current equity |
| `peak_equity` | `float` | Peak equity seen |
| `max_drawdown` | `float` | Max drawdown ratio |
| `positions` | `List[Position]` | Open positions |
| `trades` | `List[Trade]` | Closed trades |
| `fills` | `List[Fill]` | All fills |
| `total_fees` | `float` | Cumulative fees |
| `equity_curve` | `List[Tuple[datetime, float]]` | Equity after each trade |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `can_open(group)` | `bool` | Can open new position |
| `positions_in_group(group)` | `List[Position]` | Positions in group |
| `open_position(bar, order, ...)` | `Fill` | Open position |
| `merge_position(idx, bar, limit_price, ...)` | `Fill` | Merge into existing position |
| `close_position(idx, price, reason, ...)` | `Trade` | Close position |
| `partial_close_position(idx, pct, price, ...)` | `Trade` | Close fraction |
