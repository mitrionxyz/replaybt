"""Grid Market Making backtest example.

Demonstrates running a grid MM strategy through CSVProvider data
with volatility guard enabled.
"""

from pathlib import Path

from replaybt import GridBacktestEngine, GridConfig
from replaybt.data.providers import CSVProvider

DATA = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_1m.csv"


def main():
    data = CSVProvider(str(DATA), symbol_name="TEST")
    config = GridConfig(
        capital=10_000,
        spread_pct=0.001,
        concentration=0.5,
        range_pct=0.15,
        num_levels=20,
        tick_size=0.01,
        vol_guard_enabled=True,
        vol_guard_atr_period=5,
        vol_guard_threshold_pct=1.0,
        vol_guard_cooldown=15,
        snapshot_interval=5,
    )

    engine = GridBacktestEngine(data=data, config=config)
    results = engine.run()
    print(results.summary())

    # Convert to standard BacktestResults for comparison
    bt = results.to_backtest_results()
    print("\nAs BacktestResults:")
    print(bt.summary())


if __name__ == "__main__":
    main()
