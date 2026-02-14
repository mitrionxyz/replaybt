"""Tests for equity curve and buy-and-hold comparison."""

import pytest
from datetime import datetime, timedelta
from typing import List

from replaybt.data.types import Bar, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import MarketOrder
from replaybt.strategy.base import Strategy


class ListProvider(DataProvider):
    def __init__(self, bars, sym="TEST", tf="1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf


def make_bar(i, o, h, l, c, vol=1000):
    return Bar(
        datetime(2024, 1, 1) + timedelta(minutes=i),
        o, h, l, c, vol, "TEST",
    )


class TestEquityCurve:
    def test_equity_curve_populated_on_trades(self):
        """Equity curve gets a point after each trade close."""

        class BuyAndTPStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.03,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100.5),
            make_bar(2, 100.5, 104, 100, 103.5),  # TP hit
            make_bar(3, 103.5, 104, 103, 103.8),
        ]

        engine = BacktestEngine(
            strategy=BuyAndTPStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        results = engine.run()
        assert len(results.equity_curve) >= 1
        # Each point is (timestamp, equity)
        ts, eq = results.equity_curve[0]
        assert eq > 10000  # Won the trade

    def test_equity_curve_empty_no_trades(self):
        """No trades → empty equity curve."""

        class NoTradeStrategy(Strategy):
            def on_bar(self, bar, indicators, positions):
                return None

        bars = [make_bar(i, 100, 101, 99, 100) for i in range(5)]
        engine = BacktestEngine(
            strategy=NoTradeStrategy(),
            data=ListProvider(bars),
        )
        results = engine.run()
        assert results.equity_curve == []

    def test_equity_curve_multiple_trades(self):
        """Multiple trades produce multiple equity curve points."""

        class RepeatBuyStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.02,
                        stop_loss_pct=0.10,
                    )
                return None

        # Create bars that hit TP twice
        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100.5),    # Entry 1
            make_bar(2, 100.5, 103, 100, 102.5),  # TP hit
            # just_closed on bar 2 → signal on bar 3
            make_bar(3, 102.5, 103, 102, 102.8),
            make_bar(4, 102.8, 103, 102, 103),    # Entry 2
            make_bar(5, 103, 106, 102.5, 105.5),  # TP hit
        ]

        engine = BacktestEngine(
            strategy=RepeatBuyStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        results = engine.run()
        assert len(results.equity_curve) >= 2


class TestBuyAndHold:
    def test_buy_hold_return_calculated(self):
        """Buy-and-hold return computed from first/last bar closes."""

        class NoTradeStrategy(Strategy):
            def on_bar(self, bar, indicators, positions):
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),    # First close = 100
            make_bar(1, 100, 102, 99, 101),
            make_bar(2, 101, 103, 100, 120),   # Last close = 120
        ]

        engine = BacktestEngine(
            strategy=NoTradeStrategy(),
            data=ListProvider(bars),
        )
        results = engine.run()

        assert results.buy_hold_return_pct == pytest.approx(20.0)
        assert results.first_price == 100.0
        assert results.last_price == 120.0

    def test_buy_hold_in_summary(self):
        """summary() includes buy-and-hold when available."""

        class NoTradeStrategy(Strategy):
            def on_bar(self, bar, indicators, positions):
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 102, 99, 150),  # +50% B&H
        ]

        engine = BacktestEngine(
            strategy=NoTradeStrategy(),
            data=ListProvider(bars),
        )
        results = engine.run()

        summary = results.summary()
        assert "Buy & Hold" in summary
        assert "Alpha" in summary

    def test_buy_hold_negative(self):
        """Buy-and-hold can be negative."""

        class NoTradeStrategy(Strategy):
            def on_bar(self, bar, indicators, positions):
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 80, 82, 78, 80),  # -20% B&H
        ]

        engine = BacktestEngine(
            strategy=NoTradeStrategy(),
            data=ListProvider(bars),
        )
        results = engine.run()

        assert results.buy_hold_return_pct == pytest.approx(-20.0)
