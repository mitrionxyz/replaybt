"""Integration tests: sizer wired through engine → portfolio."""

import pytest
from datetime import datetime, timedelta
from typing import List

from replaybt.data.types import Bar, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import MarketOrder
from replaybt.strategy.base import Strategy
from replaybt.sizing import FixedSizer, EquityPctSizer, RiskPctSizer


class ListProvider(DataProvider):
    def __init__(self, bars: List[Bar], sym: str = "TEST"):
        self._bars = bars
        self._sym = sym

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return "1m"


def make_bars(n, base_price=100.0):
    bars = []
    price = base_price
    for i in range(n):
        bars.append(Bar(
            timestamp=datetime(2024, 1, 1) + timedelta(minutes=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1000, symbol="TEST", timeframe="1m",
        ))
    return bars


class BuyOnceStrategy(Strategy):
    def __init__(self):
        self.bar_count = 0

    def on_bar(self, bar, indicators, positions):
        self.bar_count += 1
        if self.bar_count == 2 and not positions:
            return MarketOrder(
                side=Side.LONG,
                stop_loss_pct=0.50,
                take_profit_pct=0.50,
            )
        return None


class TestSizerIntegration:

    def test_fixed_sizer_via_config(self):
        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=BuyOnceStrategy(),
            data=ListProvider(bars),
            config={
                "sizer": FixedSizer(size_usd=7777),
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()
        assert engine.portfolio.positions[0].size_usd == 7777

    def test_equity_pct_sizer_via_config(self):
        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=BuyOnceStrategy(),
            data=ListProvider(bars),
            config={
                "initial_equity": 20000,
                "sizer": EquityPctSizer(pct=0.25),
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()
        # 25% of 20000 = 5000
        assert engine.portfolio.positions[0].size_usd == 5000

    def test_risk_pct_sizer_via_config(self):
        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=BuyOnceStrategy(),
            data=ListProvider(bars),
            config={
                "initial_equity": 10000,
                "sizer": RiskPctSizer(risk_pct=0.02, default_sl_pct=0.05),
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()
        # Order has stop_loss_pct=0.50, risk 2% of 10000 = 200, /0.50 = 400
        assert engine.portfolio.positions[0].size_usd == 400

    def test_order_size_overrides_sizer(self):
        """When order.size_usd is set, sizer is NOT used."""

        class ExplicitSizeStrategy(Strategy):
            def __init__(self):
                self.bar_count = 0

            def on_bar(self, bar, indicators, positions):
                self.bar_count += 1
                if self.bar_count == 2 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=1234,  # explicit
                        stop_loss_pct=0.50,
                        take_profit_pct=0.50,
                    )
                return None

        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=ExplicitSizeStrategy(),
            data=ListProvider(bars),
            config={
                "sizer": EquityPctSizer(pct=0.50),  # would give 5000
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()
        assert engine.portfolio.positions[0].size_usd == 1234
