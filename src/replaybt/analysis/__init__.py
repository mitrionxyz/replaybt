"""Analysis utilities: Monte Carlo simulation and walk-forward optimization.

Plots are intentionally NOT imported here to avoid requiring matplotlib.
Import them directly: ``from replaybt.analysis.plots import plot_equity``
"""

from .monte_carlo import MonteCarlo, MonteCarloResult
from .walk_forward import WalkForward, WalkForwardResult, WindowResult

__all__ = [
    "MonteCarlo",
    "MonteCarloResult",
    "WalkForward",
    "WalkForwardResult",
    "WindowResult",
]
