"""Basic EMA crossover backtest.

Demonstrates the simplest possible strategy: go long when a fast EMA
crosses above a slow EMA, with fixed take-profit and stop-loss.
"""

from pathlib import Path

from replaybt import BacktestEngine, CSVProvider, Strategy, Bar, MarketOrder, Side

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
        crossed_down = fast < slow and self._prev_fast >= self._prev_slow
        self._prev_fast, self._prev_slow = fast, slow

        if not positions:
            if crossed_up:
                return MarketOrder(side=Side.LONG, take_profit_pct=0.05, stop_loss_pct=0.03)
            if crossed_down:
                return MarketOrder(side=Side.SHORT, take_profit_pct=0.05, stop_loss_pct=0.03)
        return None


def main():
    data = CSVProvider(str(DATA), symbol_name="TEST")
    engine = BacktestEngine(
        strategy=EMACrossover(),
        data=data,
        config={
            "initial_equity": 10_000,
            "indicators": {
                "ema_fast": {"type": "ema", "period": 5, "source": "close"},
                "ema_slow": {"type": "ema", "period": 10, "source": "close"},
            },
        },
    )
    results = engine.run()
    print(results.summary())


if __name__ == "__main__":
    main()
