"""Tests for trailing stop functionality."""

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


class TestTrailingStop:
    def test_trailing_stop_long_ratchets_sl_up(self):
        """Trailing stop should move SL up as price rises for LONG."""

        class TrailStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.10,
                        trailing_stop_pct=0.05,  # 5% trail
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),     # Signal bar
            make_bar(1, 100, 101, 99, 100),      # Entry at open=100, SL=90
            make_bar(2, 101, 110, 100, 109),     # High=110, trail SL = 110*0.95=104.5
            make_bar(3, 109, 111, 108, 110),     # High=111, trail SL = 111*0.95=105.45
            make_bar(4, 108, 108, 104, 105),     # Low=104 < 105.45 → TRAILING_STOP
        ]

        engine = BacktestEngine(
            strategy=TrailStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        trade = results.trades[0]
        assert trade.reason == "TRAILING_STOP"
        assert trade.exit_price == pytest.approx(111 * 0.95)  # 105.45

    def test_trailing_stop_short_ratchets_sl_down(self):
        """Trailing stop should move SL down as price falls for SHORT."""

        class TrailShortStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.SHORT,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.10,
                        trailing_stop_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100, SL=110
            make_bar(2, 99, 100, 90, 91),         # Low=90, trail SL=90*1.05=94.5
            make_bar(3, 91, 92, 88, 89),          # Low=88, trail SL=88*1.05=92.4
            make_bar(4, 90, 93, 89, 92),          # High=93 >= 92.4 → TRAILING_STOP
        ]

        engine = BacktestEngine(
            strategy=TrailShortStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        trade = results.trades[0]
        assert trade.reason == "TRAILING_STOP"
        assert trade.exit_price == pytest.approx(88 * 1.05)

    def test_trailing_stop_with_activation(self):
        """Trailing stop only activates after reaching activation_pct profit."""

        class ActivatedTrailStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.10,
                        trailing_stop_pct=0.03,
                        trailing_stop_activation_pct=0.05,  # Need 5% profit first
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100
            make_bar(2, 101, 103, 100, 102),     # +3% profit — below 5% activation
            make_bar(3, 102, 106, 101, 105),     # +6% profit — ACTIVATED, trail SL=106*0.97=102.82
            make_bar(4, 104, 104, 102, 103),     # Low=102 < 102.82 → TRAILING_STOP
        ]

        engine = BacktestEngine(
            strategy=ActivatedTrailStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        assert results.trades[0].reason == "TRAILING_STOP"
        assert results.trades[0].exit_price == pytest.approx(106 * 0.97)

    def test_trailing_stop_never_loosens(self):
        """Trailing SL should only move in profitable direction, never back."""

        class TrailNeverLoosenStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.10,
                        trailing_stop_pct=0.05,
                    )
                return None

        # Trail SL from bar N's extremes applies starting bar N+1
        # position_high after bar 1: 101 → trail SL = 101*0.95 = 95.95 → SL = max(90, 95.95) = 95.95
        # position_high after bar 2: 110 → trail SL = 110*0.95 = 104.5 → SL = max(95.95, 104.5) = 104.5
        # position_high after bar 3: 110 (unchanged) → trail SL = 104.5 (unchanged)
        # bar 4: open=106 > 104.5, low=104 < 104.5 → exit at 104.5
        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100
            make_bar(2, 101, 110, 100, 109),     # High=110, position_high updated to 110 AFTER checks
            make_bar(3, 108, 108, 107, 107.5),   # Trail SL now 104.5 from position_high=110
            make_bar(4, 106, 107, 104, 105),     # Low=104 < 104.5 → exit at 104.5
        ]

        engine = BacktestEngine(
            strategy=TrailNeverLoosenStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        assert results.trades[0].exit_price == pytest.approx(104.5)

    def test_trailing_stop_gap_through(self):
        """Open gapped past trailing SL → exit at open (worse fill)."""

        class TrailGapStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.10,
                        trailing_stop_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100
            make_bar(2, 101, 120, 100, 119),     # High=120, trail SL=114
            make_bar(3, 110, 111, 109, 110),     # Open=110 < 114 → GAP
        ]

        engine = BacktestEngine(
            strategy=TrailGapStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        assert results.trades[0].reason == "TRAILING_STOP_GAP"
        assert results.trades[0].exit_price == 110.0  # Gap fill at open

    def test_trailing_stop_coexists_with_breakeven(self):
        """Trailing stop can work alongside breakeven — trailing wins if higher SL."""

        class TrailBreakevenStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.50,
                        stop_loss_pct=0.10,
                        trailing_stop_pct=0.03,
                        trailing_stop_activation_pct=0.0,
                        breakeven_trigger_pct=0.02,
                        breakeven_lock_pct=0.005,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100
            make_bar(2, 101, 105, 100, 104),     # BE trigger at +2%, lock at 100.5
                                                  # Trail SL = 105*0.97=101.85
                                                  # Trail > BE lock, so SL=101.85
            make_bar(3, 103, 103, 101, 102),     # Low=101 < 101.85 → TRAILING_STOP
        ]

        engine = BacktestEngine(
            strategy=TrailBreakevenStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        assert results.trades[0].reason == "TRAILING_STOP"

    def test_no_trailing_stop_by_default(self):
        """Without trailing_stop_pct, SL should not ratchet."""

        class NoTrailStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        stop_loss_pct=0.10,
                        take_profit_pct=0.20,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),      # Entry at 100, SL=90
            make_bar(2, 101, 115, 100, 114),     # High=115, SL stays 90
            make_bar(3, 110, 111, 89, 90),       # Low=89 < 90 → STOP_LOSS at 90
        ]

        engine = BacktestEngine(
            strategy=NoTrailStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        assert results.trades[0].reason == "STOP_LOSS"
        assert results.trades[0].exit_price == 90.0

    def test_trailing_stop_immediate_activation(self):
        """When activation_pct is 0/None, trail starts immediately."""

        class ImmediateTrailStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.50,
                        trailing_stop_pct=0.02,  # 2% trail, no activation
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 102, 99, 101),      # Entry at 100. High=102, trail SL=102*0.98=99.96
            make_bar(2, 101, 101, 99, 100),      # Low=99 < 99.96 → TRAILING_STOP
        ]

        engine = BacktestEngine(
            strategy=ImmediateTrailStrategy(), data=ListProvider(bars), config=NO_COST,
        )
        results = engine.run()
        assert len(results.trades) == 1
        assert results.trades[0].reason == "TRAILING_STOP"
        assert results.trades[0].exit_price == pytest.approx(102 * 0.98)
