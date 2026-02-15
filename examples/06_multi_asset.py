"""Multi-asset backtest with per-symbol config and exposure cap.

Demonstrates running the same strategy on multiple symbols in a single
time-synchronized loop, with per-symbol indicator overrides and a
portfolio-level exposure cap.
"""

from pathlib import Path

from replaybt import (
    MultiAssetEngine,
    CSVProvider,
    Strategy,
    MarketOrder,
    Side,
)

DATA = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_1m.csv"


class EMACrossover(Strategy):
    """EMA crossover strategy that tracks state per symbol."""

    def configure(self, config):
        self._prev = {}  # {symbol: (fast, slow)}

    def on_bar(self, bar, indicators, positions):
        sym = bar.symbol
        fast = indicators.get("ema_fast")
        slow = indicators.get("ema_slow")

        prev = self._prev.get(sym)
        self._prev[sym] = (fast, slow)

        if fast is None or slow is None or prev is None:
            return None

        prev_fast, prev_slow = prev
        if prev_fast is None or prev_slow is None:
            return None

        crossed_up = fast > slow and prev_fast <= prev_slow
        crossed_down = fast < slow and prev_fast >= prev_slow

        if not positions:
            if crossed_up:
                return MarketOrder(
                    side=Side.LONG,
                    take_profit_pct=0.05,
                    stop_loss_pct=0.03,
                )
            if crossed_down:
                return MarketOrder(
                    side=Side.SHORT,
                    take_profit_pct=0.05,
                    stop_loss_pct=0.03,
                )
        return None


def main():
    # Use the same CSV for both symbols (demo purposes)
    assets = {
        "ASSET_A": CSVProvider(str(DATA), symbol_name="ASSET_A"),
        "ASSET_B": CSVProvider(str(DATA), symbol_name="ASSET_B"),
    }

    engine = MultiAssetEngine(
        strategy=EMACrossover(),
        assets=assets,
        config={
            "initial_equity": 10_000,
            "default_size_usd": 10_000,
            # Default indicators for all symbols
            "indicators": {
                "ema_fast": {"type": "ema", "period": 5, "source": "close"},
                "ema_slow": {"type": "ema", "period": 10, "source": "close"},
            },
            # Per-symbol overrides
            "symbol_configs": {
                "ASSET_B": {
                    "indicators": {
                        "ema_fast": {"type": "ema", "period": 8, "source": "close"},
                        "ema_slow": {"type": "ema", "period": 15, "source": "close"},
                    },
                },
            },
            # Portfolio-level exposure cap (optional)
            "max_total_exposure_usd": 15_000,
        },
    )

    results = engine.run()
    print(results.summary())
    print()
    print(results.monthly_table())


if __name__ == "__main__":
    main()
