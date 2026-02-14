"""Sweep result aggregation, sorting, and formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SweepResults:
    """Results from a parameter sweep.

    Each combo is a dict containing the swept parameter values
    plus standard metrics (net_pnl, win_rate, max_drawdown_pct, etc.).
    """
    combos: List[dict] = field(default_factory=list)

    def best(self, metric: str = "net_pnl", n: int = 10) -> List[dict]:
        """Top N combos by metric (descending)."""
        return sorted(
            self.combos, key=lambda c: c.get(metric, 0), reverse=True,
        )[:n]

    def worst(self, metric: str = "net_pnl", n: int = 10) -> List[dict]:
        """Bottom N combos by metric (ascending)."""
        return sorted(
            self.combos, key=lambda c: c.get(metric, 0),
        )[:n]

    def filter(self, **kwargs) -> "SweepResults":
        """Filter combos by param values.

        Example: results.filter(ema_fast=15, ema_slow=35)
        """
        filtered = [
            c for c in self.combos
            if all(c.get(k) == v for k, v in kwargs.items())
        ]
        return SweepResults(combos=filtered)

    def to_dataframe(self):
        """Export as pandas DataFrame.

        Raises ImportError if pandas is not installed.
        """
        import pandas as pd
        return pd.DataFrame(self.combos)

    def summary(
        self, metric: str = "net_pnl", top_n: int = 20,
    ) -> str:
        """Formatted summary table string."""
        if not self.combos:
            return "No results."

        top = self.best(metric=metric, n=top_n)

        # Determine param keys (everything that's not a metric)
        metric_keys = {
            "net_pnl", "net_return_pct", "max_drawdown_pct",
            "total_trades", "win_rate", "profit_factor",
            "total_fees", "avg_win", "avg_loss",
        }
        all_keys = set()
        for c in top:
            all_keys.update(c.keys())
        param_keys = sorted(all_keys - metric_keys)

        # Build header
        cols = param_keys + ["net_pnl", "win_rate", "max_drawdown_pct", "total_trades"]
        header = " | ".join(f"{c:>14s}" for c in cols)
        sep = "-" * len(header)

        lines = [
            f"Parameter Sweep Results (top {min(top_n, len(self.combos))}"
            f" of {len(self.combos)} by {metric})",
            sep,
            header,
            sep,
        ]

        for combo in top:
            vals = []
            for c in cols:
                v = combo.get(c, "")
                if isinstance(v, float):
                    vals.append(f"{v:>14.2f}")
                elif isinstance(v, int):
                    vals.append(f"{v:>14d}")
                else:
                    vals.append(f"{str(v):>14s}")
            lines.append(" | ".join(vals))

        lines.append(sep)
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.combos)
