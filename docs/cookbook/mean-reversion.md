# Mean Reversion

An RSI-based mean reversion strategy: buy when RSI dips below oversold, sell when it rises above overbought.

## Complete Example

```python
from replaybt import BacktestEngine, CSVProvider, Strategy, MarketOrder, Side


class RSIScalper(Strategy):
    def configure(self, config):
        self._prev_rsi = None

    def on_bar(self, bar, indicators, positions):
        rsi = indicators.get("rsi")
        if rsi is None:
            return None

        prev = self._prev_rsi
        self._prev_rsi = rsi

        if prev is None:
            return None

        if not positions:
            # Long when RSI crosses below 25 (oversold)
            if rsi < 25 and prev >= 25:
                return MarketOrder(
                    side=Side.LONG,
                    take_profit_pct=0.04,
                    stop_loss_pct=0.05,
                )
            # Short when RSI crosses above 75 (overbought)
            if rsi > 75 and prev <= 75:
                return MarketOrder(
                    side=Side.SHORT,
                    take_profit_pct=0.04,
                    stop_loss_pct=0.05,
                )
        return None


engine = BacktestEngine(
    strategy=RSIScalper(),
    data=CSVProvider("ETH_1m.csv", symbol_name="ETH"),
    config={
        "initial_equity": 10_000,
        "skip_signal_on_close": False,  # allow re-entry after exit
        "indicators": {
            "rsi": {"type": "rsi", "period": 7, "method": "wilder"},
        },
    },
)
results = engine.run()
print(results.summary())
```

## Key Differences from Trend Following

### skip_signal_on_close = False

Mean reversion strategies often want to re-enter immediately after an exit. Setting `skip_signal_on_close=False` allows `on_bar()` to run even on bars where a position just closed.

```python
config = {
    "skip_signal_on_close": False,  # re-entry on same bar as exit
}
```

### RSI Method: Wilder's vs Simple

```python
# Wilder's exponential RSI (recommended for volatile assets)
"rsi": {"type": "rsi", "period": 7, "method": "wilder"}

# Simple rolling RSI
"rsi": {"type": "rsi", "period": 7, "method": "simple"}
```

Wilder's RSI reacts faster to recent price changes due to exponential weighting. On volatile assets like meme coins, it generates different entry times that often catch more profitable mean reversion opportunities.

### Wider SL Than TP

Mean reversion strategies typically use a wider stop loss than take profit. The idea is that most entries are near extremes and will revert, but you need room for the occasional continuation move:

```python
MarketOrder(
    side=Side.LONG,
    take_profit_pct=0.04,   # 4% TP (tight — capture the reversion)
    stop_loss_pct=0.05,     # 5% SL (wider — tolerate noise)
)
```

## Adaptive TP/SL with Volatility Regime

Adjust TP/SL based on recent volatility:

```python
class AdaptiveScalper(Strategy):
    def configure(self, config):
        self._prev_rsi = None

    def on_bar(self, bar, indicators, positions):
        rsi = indicators.get("rsi")
        atr = indicators.get("atr")

        if rsi is None or atr is None:
            self._prev_rsi = rsi
            return None

        prev = self._prev_rsi
        self._prev_rsi = rsi

        if prev is None or positions:
            return None

        # High vol → wide TP/SL, low vol → tight TP/SL
        vol_ratio = atr / bar.close
        if vol_ratio > 0.0012:  # high volatility
            tp, sl = 0.04, 0.05
        else:
            tp, sl = 0.025, 0.03

        if rsi < 25 and prev >= 25:
            return MarketOrder(side=Side.LONG, take_profit_pct=tp, stop_loss_pct=sl)
        if rsi > 75 and prev <= 75:
            return MarketOrder(side=Side.SHORT, take_profit_pct=tp, stop_loss_pct=sl)
        return None
```
