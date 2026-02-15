"""Monte Carlo simulation for backtest robustness analysis.

Two modes:
- **Shuffle** (permute trade order): same total PnL, different equity paths.
  Reveals how sensitive drawdown is to trade ordering.
- **Bootstrap** (sample with replacement): different total PnL.
  Estimates the distribution of outcomes from the same edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

from ..reporting.metrics import BacktestResults


@dataclass(frozen=True)
class MonteCarloResult:
    """Results from a Monte Carlo simulation."""

    n_simulations: int
    n_trades: int
    initial_equity: float

    # Shuffle mode (permuted trade order — same total PnL, different paths)
    shuffle_pnl_percentiles: Dict[int, float]
    shuffle_max_dd_mean: float
    shuffle_max_dd_percentiles: Dict[int, float]

    # Bootstrap mode (sample with replacement — different total PnL)
    bootstrap_pnl_mean: float
    bootstrap_pnl_std: float
    bootstrap_pnl_percentiles: Dict[int, float]
    bootstrap_max_dd_mean: float
    bootstrap_max_dd_percentiles: Dict[int, float]

    # Risk
    ruin_probability: float

    # Raw arrays for downstream plotting
    shuffle_max_dds: Optional[np.ndarray] = field(default=None, repr=False)
    bootstrap_final_pnls: Optional[np.ndarray] = field(default=None, repr=False)
    bootstrap_max_dds: Optional[np.ndarray] = field(default=None, repr=False)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"{'='*60}",
            f"  Monte Carlo Simulation ({self.n_simulations:,} paths, {self.n_trades} trades)",
            f"{'='*60}",
            f"",
            f"  Shuffle Mode (permuted trade order):",
            f"    Max Drawdown (mean):  {self.shuffle_max_dd_mean:.1f}%",
        ]
        for p in sorted(self.shuffle_max_dd_percentiles):
            lines.append(
                f"    Max Drawdown (P{p:02d}):   {self.shuffle_max_dd_percentiles[p]:.1f}%"
            )

        lines += [
            f"",
            f"  Bootstrap Mode (resampled trades):",
            f"    Final PnL (mean):     ${self.bootstrap_pnl_mean:,.2f}",
            f"    Final PnL (std):      ${self.bootstrap_pnl_std:,.2f}",
        ]
        for p in sorted(self.bootstrap_pnl_percentiles):
            lines.append(
                f"    Final PnL (P{p:02d}):      ${self.bootstrap_pnl_percentiles[p]:,.2f}"
            )
        lines.append(f"    Max Drawdown (mean):  {self.bootstrap_max_dd_mean:.1f}%")
        for p in sorted(self.bootstrap_max_dd_percentiles):
            lines.append(
                f"    Max Drawdown (P{p:02d}):   {self.bootstrap_max_dd_percentiles[p]:.1f}%"
            )

        lines += [
            f"",
            f"  Risk:",
            f"    Ruin Probability:     {self.ruin_probability:.2%}",
            f"{'='*60}",
        ]
        return "\n".join(lines)


_PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
_BATCH_SIZE = 1000


def _max_dd_pct(equity_curves: np.ndarray) -> np.ndarray:
    """Compute max drawdown % for each row of equity curves.

    Args:
        equity_curves: 2D array, shape (n_sims, n_trades+1). Each row is
            an equity path starting at initial_equity.

    Returns:
        1D array of max drawdown percentages (0–100 scale).
    """
    running_peak = np.maximum.accumulate(equity_curves, axis=1)
    drawdowns = (running_peak - equity_curves) / np.where(
        running_peak > 0, running_peak, 1.0
    )
    return np.max(drawdowns, axis=1) * 100


class MonteCarlo:
    """Monte Carlo simulation on backtest results.

    Usage::

        mc = MonteCarlo(results, n_simulations=10_000, seed=42)
        result = mc.run()
        print(result.summary())

    Args:
        results: A ``BacktestResults`` instance with trades.
        n_simulations: Number of simulation paths.
        seed: Optional RNG seed for reproducibility.
        ruin_threshold: Equity level below which the account is "ruined".
            Default 0.0 (total wipeout).
        keep_distributions: If True, attach raw numpy arrays to result for
            downstream plotting.
    """

    def __init__(
        self,
        results: BacktestResults,
        n_simulations: int = 10_000,
        seed: Optional[int] = None,
        ruin_threshold: float = 0.0,
        keep_distributions: bool = True,
    ):
        self._results = results
        self._n_simulations = n_simulations
        self._seed = seed
        self._ruin_threshold = ruin_threshold
        self._keep_distributions = keep_distributions

    def run(self) -> MonteCarloResult:
        """Run both shuffle and bootstrap simulations."""
        trades = self._results.trades
        n_trades = len(trades)
        initial_equity = self._results.initial_equity
        rng = np.random.default_rng(self._seed)

        if n_trades == 0:
            empty_pct: Dict[int, float] = {p: 0.0 for p in _PERCENTILES}
            return MonteCarloResult(
                n_simulations=self._n_simulations,
                n_trades=0,
                initial_equity=initial_equity,
                shuffle_pnl_percentiles=dict(empty_pct),
                shuffle_max_dd_mean=0.0,
                shuffle_max_dd_percentiles=dict(empty_pct),
                bootstrap_pnl_mean=0.0,
                bootstrap_pnl_std=0.0,
                bootstrap_pnl_percentiles=dict(empty_pct),
                bootstrap_max_dd_mean=0.0,
                bootstrap_max_dd_percentiles=dict(empty_pct),
                ruin_probability=0.0,
                shuffle_max_dds=None,
                bootstrap_final_pnls=None,
                bootstrap_max_dds=None,
            )

        pnls = np.array([t.pnl_usd for t in trades], dtype=np.float64)
        n_sims = self._n_simulations

        # --- Shuffle mode ---
        shuffle_dds = self._run_shuffle(pnls, initial_equity, n_sims, rng)

        # Shuffle final PnL is invariant (all paths sum to the same total)
        total_pnl = float(pnls.sum())
        shuffle_pnl_pcts: Dict[int, float] = {p: total_pnl for p in _PERCENTILES}

        shuffle_dd_pcts: Dict[int, float] = {
            p: float(np.percentile(shuffle_dds, p)) for p in _PERCENTILES
        }

        # Ruin probability from shuffle paths
        ruin_count = self._count_ruin(
            pnls, initial_equity, n_sims, rng, self._ruin_threshold
        )
        ruin_prob = ruin_count / n_sims

        # --- Bootstrap mode ---
        boot_pnls, boot_dds = self._run_bootstrap(
            pnls, initial_equity, n_sims, rng
        )

        boot_pnl_pcts: Dict[int, float] = {
            p: float(np.percentile(boot_pnls, p)) for p in _PERCENTILES
        }
        boot_dd_pcts: Dict[int, float] = {
            p: float(np.percentile(boot_dds, p)) for p in _PERCENTILES
        }

        return MonteCarloResult(
            n_simulations=n_sims,
            n_trades=n_trades,
            initial_equity=initial_equity,
            shuffle_pnl_percentiles=shuffle_pnl_pcts,
            shuffle_max_dd_mean=float(shuffle_dds.mean()),
            shuffle_max_dd_percentiles=shuffle_dd_pcts,
            bootstrap_pnl_mean=float(boot_pnls.mean()),
            bootstrap_pnl_std=float(boot_pnls.std()),
            bootstrap_pnl_percentiles=boot_pnl_pcts,
            bootstrap_max_dd_mean=float(boot_dds.mean()),
            bootstrap_max_dd_percentiles=boot_dd_pcts,
            ruin_probability=ruin_prob,
            shuffle_max_dds=shuffle_dds if self._keep_distributions else None,
            bootstrap_final_pnls=boot_pnls if self._keep_distributions else None,
            bootstrap_max_dds=boot_dds if self._keep_distributions else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_shuffle(
        pnls: np.ndarray,
        initial_equity: float,
        n_sims: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Run shuffle simulations in batches. Returns max DD % array."""
        n_trades = len(pnls)
        all_dds = []

        for start in range(0, n_sims, _BATCH_SIZE):
            batch = min(_BATCH_SIZE, n_sims - start)
            # Create index arrays and permute each row
            indices = np.tile(np.arange(n_trades), (batch, 1))
            rng.permuted(indices, axis=1, out=indices)
            shuffled_pnls = pnls[indices]  # (batch, n_trades)

            # Build equity curves
            equity = np.empty((batch, n_trades + 1), dtype=np.float64)
            equity[:, 0] = initial_equity
            np.cumsum(shuffled_pnls, axis=1, out=equity[:, 1:])
            equity[:, 1:] += initial_equity

            all_dds.append(_max_dd_pct(equity))

        return np.concatenate(all_dds)

    @staticmethod
    def _run_bootstrap(
        pnls: np.ndarray,
        initial_equity: float,
        n_sims: int,
        rng: np.random.Generator,
    ) -> tuple:
        """Run bootstrap simulations in batches. Returns (final_pnls, max_dds)."""
        n_trades = len(pnls)
        all_final_pnls = []
        all_dds = []

        for start in range(0, n_sims, _BATCH_SIZE):
            batch = min(_BATCH_SIZE, n_sims - start)
            indices = rng.integers(0, n_trades, size=(batch, n_trades))
            sampled_pnls = pnls[indices]

            # Build equity curves
            equity = np.empty((batch, n_trades + 1), dtype=np.float64)
            equity[:, 0] = initial_equity
            np.cumsum(sampled_pnls, axis=1, out=equity[:, 1:])
            equity[:, 1:] += initial_equity

            all_final_pnls.append(sampled_pnls.sum(axis=1))
            all_dds.append(_max_dd_pct(equity))

        return np.concatenate(all_final_pnls), np.concatenate(all_dds)

    @staticmethod
    def _count_ruin(
        pnls: np.ndarray,
        initial_equity: float,
        n_sims: int,
        rng: np.random.Generator,
        threshold: float,
    ) -> int:
        """Count paths where equity ever drops below threshold (shuffle mode)."""
        n_trades = len(pnls)
        ruin_count = 0

        for start in range(0, n_sims, _BATCH_SIZE):
            batch = min(_BATCH_SIZE, n_sims - start)
            indices = np.tile(np.arange(n_trades), (batch, 1))
            rng.permuted(indices, axis=1, out=indices)
            shuffled_pnls = pnls[indices]

            equity = np.empty((batch, n_trades + 1), dtype=np.float64)
            equity[:, 0] = initial_equity
            np.cumsum(shuffled_pnls, axis=1, out=equity[:, 1:])
            equity[:, 1:] += initial_equity

            ruin_count += int(np.any(equity < threshold, axis=1).sum())

        return ruin_count
