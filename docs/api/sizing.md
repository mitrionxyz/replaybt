# Sizing

## PositionSizer (ABC)

Abstract base for position sizing strategies.

```python
from replaybt import PositionSizer

class MySizer(PositionSizer):
    def get_size(self, equity, side, price, symbol="", stop_loss_pct=0.0):
        return equity * 0.1  # 10% of equity
```

### Abstract Method

```python
def get_size(
    self,
    equity: float,       # current portfolio equity
    side: str,            # "LONG" or "SHORT"
    price: float,         # current price
    symbol: str = "",     # asset symbol
    stop_loss_pct: float = 0.0,  # SL distance (for risk-based sizing)
) -> float:  # position size in USD
```

---

## FixedSizer

Constant USD position size.

```python
from replaybt import FixedSizer

sizer = FixedSizer(size_usd=10_000)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `size_usd` | `float` | `10_000` | Fixed size |

---

## EquityPctSizer

Size as a percentage of current equity.

```python
from replaybt import EquityPctSizer

sizer = EquityPctSizer(pct=0.10, min_size=100, max_size=50_000)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pct` | `float` | `0.10` | Fraction of equity (0.10 = 10%) |
| `min_size` | `float` | `100` | Minimum position size |
| `max_size` | `float` | `0` | Maximum size (0 = no cap) |

---

## RiskPctSizer

Size so that a stop-loss hit loses at most `risk_pct` of equity.

**Formula:** `size = (equity * risk_pct) / stop_loss_pct`

```python
from replaybt import RiskPctSizer

sizer = RiskPctSizer(risk_pct=0.01, default_sl_pct=0.035)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `risk_pct` | `float` | `0.01` | Max equity at risk per trade (1%) |
| `min_size` | `float` | `100` | Minimum position size |
| `max_size` | `float` | `0` | Maximum size (0 = no cap) |
| `default_sl_pct` | `float` | `0.035` | Default SL if none provided |

**Example:** With $10,000 equity, 1% risk, and 3.5% SL:

`size = ($10,000 * 0.01) / 0.035 = $2,857`

If the trade hits SL, you lose $2,857 * 3.5% = $100 = 1% of equity.

---

## KellySizer

Position sizing using the Kelly criterion.

**Formula:** `f* = win_rate - (1 - win_rate) / payoff_ratio`

```python
from replaybt import KellySizer

sizer = KellySizer(
    win_rate=0.60,
    avg_win=0.08,
    avg_loss=0.035,
    fraction=0.25,  # quarter-Kelly
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `win_rate` | `float` | `0.60` | Historical win rate (0-1) |
| `avg_win` | `float` | `0.08` | Avg winning trade % |
| `avg_loss` | `float` | `0.035` | Avg losing trade % |
| `fraction` | `float` | `0.25` | Kelly fraction (1.0 = full Kelly) |
| `min_size` | `float` | `100` | Minimum size |
| `max_size` | `float` | `0` | Maximum size (0 = no cap) |
| `max_equity_pct` | `float` | `0.25` | Max fraction of equity |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `kelly_fraction` | `float` | Raw Kelly before fractional multiplier |

## Using a Sizer

Pass to the engine config:

```python
engine = BacktestEngine(
    strategy=my_strategy,
    data=data,
    config={
        "initial_equity": 10_000,
        "sizer": RiskPctSizer(risk_pct=0.01),
    },
)
```

When a sizer is set, `default_size_usd` is ignored and the sizer determines position size for each trade.
