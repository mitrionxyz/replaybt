# RL Agent

`StepEngine` provides a gym-like `step(action)` / `reset()` interface for reinforcement learning agents.

## Complete Example

```python
from replaybt import StepEngine, CSVProvider, MarketOrder, Side


def simple_agent(obs):
    """Trivial agent: go long when no position."""
    if not obs.positions:
        return MarketOrder(
            side=Side.LONG,
            take_profit_pct=0.02,
            stop_loss_pct=0.01,
        )
    return None


env = StepEngine(
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    config={
        "initial_equity": 10_000,
        "indicators": {
            "ema_fast": {"type": "ema", "period": 5, "source": "close"},
        },
    },
)

obs = env.reset()
total_reward = 0.0

while not obs.done:
    action = simple_agent(obs)
    result = env.step(action)
    obs = result.observation
    total_reward += result.reward

    if result.done:
        break

print(f"Steps: {obs.step_count}, Reward: {total_reward:.2f}")
print(f"Final equity: ${obs.equity:,.2f}")
```

## StepObservation

Available on every step:

```python
obs.bar          # current Bar (timestamp, OHLCV, symbol)
obs.indicators   # dict of indicator values
obs.positions    # list of open Position objects
obs.equity       # current portfolio equity
obs.step_count   # number of steps taken
obs.done         # True if data is exhausted
```

## StepResult

Returned by `step()`:

```python
result.observation  # StepObservation (next state)
result.reward       # float — PnL change this step
result.done         # bool — episode finished
result.info         # dict — metadata
```

## Actions

Pass an `Order` or `None`:

```python
# Do nothing
result = env.step(None)

# Enter a position
result = env.step(MarketOrder(side=Side.LONG, take_profit_pct=0.03))

# Place a limit order
result = env.step(LimitOrder(side=Side.LONG, limit_price=2300.0))
```

## Episode Loop

```python
for episode in range(100):
    obs = env.reset()
    episode_reward = 0.0

    while not obs.done:
        # Your RL policy here
        action = policy(obs)
        result = env.step(action)
        obs = result.observation
        episode_reward += result.reward

    print(f"Episode {episode}: reward={episode_reward:.2f}")
```

## With a Custom Strategy

You can also pass a `Strategy` to the `StepEngine` to handle indicator-based signals while using the step interface for observation:

```python
env = StepEngine(
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    config={"initial_equity": 10_000},
    strategy=MyStrategy(),
)
```

When a strategy is provided, calling `env.step(None)` lets the strategy generate signals via `on_bar()`.

## Building Feature Vectors

Use `obs.indicators` and `obs.bar` to build feature vectors for your RL model:

```python
import numpy as np

def obs_to_features(obs):
    bar = obs.bar
    return np.array([
        bar.close,
        bar.volume,
        obs.indicators.get("ema_fast") or 0,
        obs.indicators.get("rsi") or 50,
        obs.equity / 10_000,  # normalized equity
        1.0 if obs.positions else 0.0,
    ])
```
