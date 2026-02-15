"""Validation tools: static auditor, delay test, and OOS split.

Demonstrates three ways to verify a backtest isn't fooling you:
1. Static auditor — scans source code for common bias patterns
2. Delay test — adds +1 bar latency to detect timing sensitivity
3. OOS split — train/test split to detect overfitting
"""

from pathlib import Path

from replaybt import (
    CSVProvider,
    Strategy,
    MarketOrder,
    Side,
)
from replaybt.validation.auditor import audit_file
from replaybt.validation.stress import DelayTest, OOSSplit

EXAMPLE_SCRIPT = Path(__file__).resolve().parent / "01_basic_backtest.py"
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
            return MarketOrder(side=Side.LONG, take_profit_pct=0.05, stop_loss_pct=0.03)
        return None


ENGINE_CONFIG = {
    "initial_equity": 10_000,
    "indicators": {
        "ema_fast": {"type": "ema", "period": 5, "source": "close"},
        "ema_slow": {"type": "ema", "period": 10, "source": "close"},
    },
}


def main():
    # --- 1. Static Audit ---
    print("=" * 60)
    print("1. STATIC AUDIT")
    print("=" * 60)
    issues = audit_file(str(EXAMPLE_SCRIPT))
    if not issues:
        print("  No issues found.")
    for issue in issues:
        print(f"  [{issue.severity}] line {issue.line}: {issue.message}")
    print()

    # --- 2. Delay Test (+1 bar) ---
    print("=" * 60)
    print("2. DELAY TEST (+1 bar)")
    print("=" * 60)
    data = CSVProvider(str(DATA), symbol_name="TEST")
    delay = DelayTest(
        strategy_factory=EMACrossover,
        data=data,
        config=ENGINE_CONFIG,
        delay_bars=1,
    )
    delay_result = delay.run()
    print(f"  Normal PnL:  ${delay_result.normal.net_pnl:,.2f}")
    print(f"  Delayed PnL: ${delay_result.delayed.net_pnl:,.2f}")
    print(f"  PnL change:  {delay_result.pnl_change_pct:+.1f}%")
    print(f"  Verdict:     {delay_result.verdict}")
    print()

    # --- 3. Out-of-Sample Split ---
    print("=" * 60)
    print("3. OUT-OF-SAMPLE SPLIT (50/50)")
    print("=" * 60)
    data.reset()
    oos = OOSSplit(
        strategy_factory=EMACrossover,
        data=data,
        config=ENGINE_CONFIG,
        split_ratio=0.5,
    )
    oos_result = oos.run()
    print(f"  Train PnL:      ${oos_result.train.net_pnl:,.2f}")
    print(f"  Test PnL:       ${oos_result.test.net_pnl:,.2f}")
    print(f"  WR divergence:  {oos_result.wr_divergence:+.1f}pp")
    print(f"  PnL ratio:      {oos_result.pnl_ratio:.2f}")
    print(f"  Verdict:        {oos_result.verdict}")


if __name__ == "__main__":
    main()
