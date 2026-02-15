"""Parallel parameter sweep over TP/SL combinations.

Uses multiprocessing to evaluate all parameter combinations in parallel,
then prints the top results ranked by net PnL.
"""

from pathlib import Path

from replaybt import (
    CSVProvider,
    Strategy,
    MarketOrder,
    Side,
)
from replaybt.optimize.sweep import ParameterSweep

DATA = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_1m.csv"


class EMACrossover(Strategy):
    def configure(self, config):
        self._prev_fast = None
        self._prev_slow = None

    def on_bar(self, bar, indicators, positions):
        fast = indicators.get("ema_fast")
        slow = indicators.get("ema_slow")
        if fast is None or slow is None or self._prev_fast is None:
            self._prev_fast, self._prev_slow = fast, slow
            return None

        crossed_up = fast > slow and self._prev_fast <= self._prev_slow
        self._prev_fast, self._prev_slow = fast, slow

        if not positions and crossed_up:
            return MarketOrder(side=Side.LONG)
        return None


def main():
    sweep = ParameterSweep(
        strategy_class=EMACrossover,
        data=CSVProvider(str(DATA), symbol_name="TEST"),
        base_config={
            "initial_equity": 10_000,
            "indicators": {
                "ema_fast": {"type": "ema", "period": 5, "source": "close"},
                "ema_slow": {"type": "ema", "period": 10, "source": "close"},
            },
        },
        param_grid={
            "take_profit_pct": [0.02, 0.04, 0.06, 0.08],
            "stop_loss_pct": [0.01, 0.02, 0.03],
        },
        n_workers=4,
    )

    results = sweep.run()
    print(results.summary(top_n=5))


if __name__ == "__main__":
    main()
