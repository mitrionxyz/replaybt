# Optimization

Tools for finding good parameters and testing their robustness.

| Tool | Purpose |
|------|---------|
| [Parameter Sweep](parameter-sweep.md) | Parallel grid search across parameter combinations |
| [Walk-Forward](walk-forward.md) | Rolling train/test optimization |
| [Monte Carlo](monte-carlo.md) | Randomized robustness analysis |

## Philosophy

Optimization is dangerous. The best parameters on historical data are often the worst parameters going forward. replaybt provides optimization tools alongside validation tools to help you distinguish robust parameters from overfit ones.

**Recommended workflow:**

1. **Sweep** — find parameter regions that work
2. **Walk-forward** — test if the best parameters are stable across time windows
3. **Monte Carlo** — estimate the range of outcomes and probability of ruin
4. **OOS split** — final blind validation on held-out data
