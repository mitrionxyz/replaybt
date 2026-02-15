"""Declarative strategy from JSON config.

No Python strategy class needed — define entry conditions, exit levels,
and indicators entirely in a JSON file.
"""

from pathlib import Path

from replaybt import BacktestEngine, CSVProvider, DeclarativeStrategy

DATA = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_1m.csv"
CONFIG = Path(__file__).resolve().parent / "trend_follower.json"


def main():
    strategy = DeclarativeStrategy.from_json(str(CONFIG))

    engine = BacktestEngine(
        strategy=strategy,
        data=CSVProvider(str(DATA), symbol_name="TEST"),
        config={
            "initial_equity": 10_000,
            "indicators": strategy.indicator_config(),
        },
    )
    results = engine.run()
    print(results.summary())


if __name__ == "__main__":
    main()
