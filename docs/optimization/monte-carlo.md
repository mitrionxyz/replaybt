# Monte Carlo

Randomized simulation to estimate the range of possible outcomes from your trade history.

## Complete Example

```python
from replaybt import BacktestEngine, CSVProvider, MonteCarlo

# Run backtest first
engine = BacktestEngine(strategy=my_strategy, data=data, config=config)
results = engine.run()

# Monte Carlo analysis
mc = MonteCarlo(results, n_simulations=1000)
mc_result = mc.run()
print(mc_result.summary())
```

## What It Does

Monte Carlo runs two types of simulations on your actual trade results:

### Shuffle (Permutation)

Randomly reorder the sequence of trades and replay them. This tests whether your results depend on the specific order of trades or are robust to any ordering.

With 1,000 shuffles, you get a distribution of possible PnL outcomes and drawdowns from the same set of trades.

### Bootstrap (Resampling)

Randomly sample trades **with replacement** to create synthetic trade sequences. This estimates confidence intervals for your performance metrics.

## MonteCarloResult

```python
mc_result = mc.run()

# Shuffle results (trade order randomization)
mc_result.shuffle_pnl_percentiles     # {5: $X, 25: $Y, 50: $Z, 75: $W, 95: $V}
mc_result.shuffle_max_dd_mean         # average max drawdown
mc_result.shuffle_max_dd_percentiles  # {5: X%, 50: Y%, 95: Z%}

# Bootstrap results (resampled trades)
mc_result.bootstrap_pnl_mean          # expected PnL
mc_result.bootstrap_pnl_std           # PnL standard deviation
mc_result.bootstrap_pnl_percentiles   # {5: $X, 25: $Y, 50: $Z, 75: $W, 95: $V}
mc_result.bootstrap_max_dd_mean
mc_result.bootstrap_max_dd_percentiles

# Ruin probability
mc_result.ruin_probability            # fraction of simulations that went to zero
```

## Interpreting Results

```python
print(mc_result.summary())
```

Key things to look for:

| Metric | Good Sign | Warning Sign |
|--------|-----------|-------------|
| Shuffle 5th percentile PnL | Still positive | Negative |
| Ruin probability | 0% | > 5% |
| Bootstrap PnL std | Small vs mean | Larger than mean |
| Shuffle DD 95th pct | < 25% | > 40% |

## Parameters

```python
MonteCarlo(
    results=backtest_results,  # BacktestResults from a completed backtest
    n_simulations=1000,        # number of random simulations
)
```

More simulations give tighter confidence intervals but take longer. 1,000 is usually sufficient.
