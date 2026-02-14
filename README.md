# replaybt

Realistic backtesting engine for algo traders & AI agents.

Engine owns execution. Strategy only emits signals. No look-ahead bias by default.

## Install

```bash
pip install replaybt
```

## Quick Start

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, Bar, MarketOrder, Side

class MyStrategy(Strategy):
    def on_bar(self, bar, indicators, positions):
        # Your logic here — return Order or None
        return None

engine = BacktestEngine(
    strategy=MyStrategy(),
    data=CSVProvider('ETH_1m.csv'),
    config={'initial_equity': 10000},
)
results = engine.run()
print(results.summary())
```
