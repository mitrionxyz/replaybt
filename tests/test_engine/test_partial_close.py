"""Tests for partial close functionality."""

import pytest
from datetime import datetime, timedelta
from typing import List, Optional

from replaybt.data.types import Bar, Fill, Position, Side
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


NO_COST = {"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0}


class TestPartialTP:
    def test_partial_tp_closes_fraction(self):
        """Partial TP should close 50% at TP and keep remainder open."""

        class PartialTPStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                        partial_tp_pct=0.5,  # Close 50% at TP
                        partial_tp_new_tp_pct=0.30,  # New TP at +30% for remainder
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),     # Signal
            make_bar(1, 100, 101, 99, 100),      # Entry at 100, TP=110
            make_bar(2, 105, 111, 104, 110),     # High=111 >= 110 → partial TP, new TP=130
            make_bar(3, 110, 112, 109, 111),     # Position still open (TP=130 now)
            make_bar(4, 111, 112, 108, 109),
        ]

        engine = BacktestEngine(
            strategy=PartialTPStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        # Should have a partial trade
        partial_trades = [t for t in results.trades if t.is_partial]
        assert len(partial_trades) == 1
        assert partial_trades[0].reason == "PARTIAL_TP"
        assert partial_trades[0].size_usd == pytest.approx(5000.0)  # 50% of 10k
        assert partial_trades[0].exit_price == pytest.approx(110.0)

        # Position should still be open with remaining 50%
        assert len(engine.portfolio.positions) == 1
        assert engine.portfolio.positions[0].size_usd == pytest.approx(5000.0)

    def test_partial_tp_new_tp_for_remainder(self):
        """After partial TP, remainder gets new TP level."""

        class PartialTPNewTPStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.10,     # TP at +10%
                        stop_loss_pct=0.05,
                        partial_tp_pct=0.5,
                        partial_tp_new_tp_pct=0.20,  # Remainder TP at +20%
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100, TP=110
            make_bar(2, 105, 111, 104, 110),     # Partial TP at 110, new TP=120
            make_bar(3, 110, 121, 109, 120),     # Full TP at 120
        ]

        engine = BacktestEngine(
            strategy=PartialTPNewTPStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        assert len(results.trades) == 2
        # First: partial close
        assert results.trades[0].is_partial is True
        assert results.trades[0].reason == "PARTIAL_TP"
        assert results.trades[0].size_usd == 5000.0
        # Second: full close at new TP
        assert results.trades[1].is_partial is False
        assert results.trades[1].reason == "TAKE_PROFIT"
        assert results.trades[1].exit_price == 120.0
        assert results.trades[1].size_usd == 5000.0

    def test_partial_tp_only_fires_once(self):
        """Partial TP should only trigger once, not every time price hits TP."""

        class OncePartialTPStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.20,
                        partial_tp_pct=0.5,
                        partial_tp_new_tp_pct=0.30,  # High new TP
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100
            make_bar(2, 105, 111, 104, 110),     # Partial TP
            make_bar(3, 108, 109, 107, 108),     # No exit
            make_bar(4, 108, 108, 95, 96),       # SL at 95 for remainder
        ]

        engine = BacktestEngine(
            strategy=OncePartialTPStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        partial_trades = [t for t in results.trades if t.reason == "PARTIAL_TP"]
        assert len(partial_trades) == 1  # Only once

    def test_partial_tp_short(self):
        """Partial TP works for SHORT positions."""

        class PartialTPShortStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.SHORT,
                        size_usd=10000.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                        partial_tp_pct=0.5,
                        partial_tp_new_tp_pct=0.30,  # New TP at 70 for remainder
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100, TP=90
            make_bar(2, 95, 96, 89, 90),         # Low=89 <= 90 → partial TP, new TP=70
            make_bar(3, 90, 91, 89, 90.5),       # Position still open (TP=70 now)
        ]

        engine = BacktestEngine(
            strategy=PartialTPShortStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        partial_trades = [t for t in results.trades if t.is_partial]
        assert len(partial_trades) == 1
        assert partial_trades[0].exit_price == pytest.approx(90.0)
        assert partial_trades[0].size_usd == pytest.approx(5000.0)
        assert engine.portfolio.positions[0].size_usd == pytest.approx(5000.0)

    def test_no_partial_tp_by_default(self):
        """Without partial_tp_pct, TP should fully close position."""

        class FullTPStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),
            make_bar(2, 105, 111, 104, 110),     # Full TP
        ]

        engine = BacktestEngine(
            strategy=FullTPStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        assert len(results.trades) == 1
        assert results.trades[0].is_partial is False
        assert results.trades[0].reason == "TAKE_PROFIT"
        assert len(engine.portfolio.positions) == 0

    def test_sl_closes_remainder_after_partial_tp(self):
        """After partial TP, SL should close the remaining fraction."""

        class PartialThenSLStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                        partial_tp_pct=0.5,
                        partial_tp_new_tp_pct=0.30,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100, TP=110, SL=95
            make_bar(2, 105, 111, 104, 110),     # Partial TP: close 5k
            make_bar(3, 108, 109, 94, 95),       # SL hit at 95, close remaining 5k
        ]

        engine = BacktestEngine(
            strategy=PartialThenSLStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        assert len(results.trades) == 2
        # First: partial TP
        assert results.trades[0].reason == "PARTIAL_TP"
        assert results.trades[0].size_usd == 5000.0
        assert results.trades[0].pnl_usd > 0
        # Second: SL on remainder
        assert results.trades[1].reason == "STOP_LOSS"
        assert results.trades[1].size_usd == 5000.0
        assert results.trades[1].pnl_usd < 0
        assert len(engine.portfolio.positions) == 0


class TestStrategyPartialClose:
    def test_check_exits_partial_close(self):
        """Strategy can return 4-tuple from check_exits for partial close."""

        class PartialExitStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0
                self.partial_done = False

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.20,
                    )
                return None

            def check_exits(self, bar, positions):
                if positions and bar.high >= 110 and not self.partial_done:
                    self.partial_done = True
                    return [(0, 110.0, "MANUAL_PARTIAL", 0.5)]
                return []

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100
            make_bar(2, 105, 111, 104, 110),     # check_exits triggers partial
            make_bar(3, 110, 111, 109, 110),
        ]

        engine = BacktestEngine(
            strategy=PartialExitStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        partial = [t for t in results.trades if t.is_partial]
        assert len(partial) == 1
        assert partial[0].reason == "MANUAL_PARTIAL"
        assert partial[0].size_usd == pytest.approx(5000.0)
        assert len(engine.portfolio.positions) == 1
        assert engine.portfolio.positions[0].size_usd == pytest.approx(5000.0)

    def test_check_exits_full_close_3_tuple(self):
        """Standard 3-tuple from check_exits still works (backward compat)."""

        class FullExitStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.20,
                    )
                return None

            def check_exits(self, bar, positions):
                if positions and bar.close >= 110:
                    return [(0, bar.close, "SIGNAL_EXIT")]
                return []

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),
            make_bar(2, 105, 111, 104, 110),
        ]

        engine = BacktestEngine(
            strategy=FullExitStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()

        assert len(results.trades) == 1
        assert results.trades[0].is_partial is False
        assert results.trades[0].reason == "SIGNAL_EXIT"
        assert len(engine.portfolio.positions) == 0

    def test_partial_close_fees_are_proportional(self):
        """Two 50% closes should have same total fees as one 100% close."""

        class TwoPartialStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        size_usd=10000.0,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.20,
                    )
                return None

            def check_exits(self, bar, positions):
                if positions and bar.close >= 105 and positions[0].size_usd > 6000:
                    return [(0, bar.close, "PARTIAL_1", 0.5)]
                if positions and bar.close >= 108:
                    return [(0, bar.close, "PARTIAL_2")]
                return []

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry
            make_bar(2, 105, 106, 104, 105),     # Partial 50%
            make_bar(3, 108, 109, 107, 108),     # Close remainder
        ]

        taker_fee = 0.001
        engine = BacktestEngine(
            strategy=TwoPartialStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": taker_fee, "maker_fee": 0.0},
        )
        results = engine.run()

        assert len(results.trades) == 2
        # First trade: 5000 * fee * 2 (entry+exit)
        expected_fees_1 = 5000 * taker_fee * 2
        assert results.trades[0].fees == pytest.approx(expected_fees_1)
        # Second trade: 5000 * fee * 2
        expected_fees_2 = 5000 * taker_fee * 2
        assert results.trades[1].fees == pytest.approx(expected_fees_2)
