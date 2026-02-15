# Cookbook

Working recipes for common strategy patterns. Each page leads with a complete, runnable example.

| Recipe | Pattern | Key Concept |
|--------|---------|-------------|
| [EMA Crossover](ema-crossover.md) | Trend following | Basic `on_bar` + `MarketOrder` |
| [Mean Reversion](mean-reversion.md) | RSI-based entries | `skip_signal_on_close=False` |
| [Scale-In](scale-in.md) | DCA / second entries | `on_fill` + `LimitOrder(merge_position=True)` |
| [Breakeven Stop](breakeven.md) | Lock in small profit | `breakeven_trigger_pct` / `breakeven_lock_pct` |
| [Trailing Stop](trailing-stop.md) | Follow price peaks | `trailing_stop_pct` + activation |
| [Multi-Asset](multi-asset.md) | Portfolio backtest | `MultiAssetEngine` + exposure cap |
| [RL Agent](rl-agent.md) | Reinforcement learning | `StepEngine` step/reset |
