"""RL agent using StepEngine with gym-like step/reset API.

The StepEngine exposes a step(action) -> (observation, reward, done, info)
interface, making it straightforward to integrate with RL frameworks.
"""

from pathlib import Path

from replaybt import StepEngine, CSVProvider, MarketOrder, Side

DATA = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_1m.csv"


def simple_agent(obs):
    """Trivial agent: go long when no position, hold until exit."""
    if not obs.positions:
        return MarketOrder(side=Side.LONG, take_profit_pct=0.02, stop_loss_pct=0.01)
    return None


def main():
    env = StepEngine(
        data=CSVProvider(str(DATA), symbol_name="TEST"),
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

    print(f"Episode complete — {obs.step_count} steps, total reward: {total_reward:.2f}")
    print(f"Final equity: ${obs.equity:,.2f}")


if __name__ == "__main__":
    main()
