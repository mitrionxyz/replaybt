"""Tests for StopOrder execution in the engine loop."""

import pytest
from datetime import datetime, timedelta
from typing import List, Optional

from replaybt.data.types import Bar, Fill, Position, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import StopOrder, MarketOrder
from replaybt.engine.step import StepEngine
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


class TestStopOrders:
    def test_long_stop_fills_on_breakout(self):
        """LONG stop at 105 fills when bar high >= 105."""

        class StopBuyStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return StopOrder(
                        side=Side.LONG,
                        stop_price=105.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),     # Signal bar
            make_bar(1, 100, 103, 99, 102),      # High=103 < 105 → no fill
            make_bar(2, 102, 106, 101, 105),     # High=106 >= 105 → FILL at 105
            make_bar(3, 105, 106, 104, 105.5),
        ]

        engine = BacktestEngine(
            strategy=StopBuyStrategy(), data=ListProvider(bars), config=NO_COST,
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        assert fills[0].price == 105.0
        assert fills[0].is_entry is True
        assert fills[0].timestamp == bars[2].timestamp

    def test_short_stop_fills_on_breakdown(self):
        """SHORT stop at 95 fills when bar low <= 95."""

        class StopSellStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return StopOrder(
                        side=Side.SHORT,
                        stop_price=95.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 97, 98),       # Low=97 > 95 → no fill
            make_bar(2, 98, 99, 94, 95),         # Low=94 <= 95 → FILL at 95
            make_bar(3, 95, 96, 94, 95.5),
        ]

        engine = BacktestEngine(
            strategy=StopSellStrategy(), data=ListProvider(bars), config=NO_COST,
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        assert fills[0].price == 95.0
        assert fills[0].timestamp == bars[2].timestamp

    def test_long_stop_gap_through(self):
        """LONG stop at 105 — open at 108 (gapped past) → fill at open."""

        class GapStopStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return StopOrder(
                        side=Side.LONG,
                        stop_price=105.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 103, 99, 102),      # No fill
            make_bar(2, 108, 110, 107, 109),     # Open=108 >= 105 → fill at 108 (gap)
            make_bar(3, 109, 110, 108, 109.5),
        ]

        engine = BacktestEngine(
            strategy=GapStopStrategy(), data=ListProvider(bars), config=NO_COST,
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        assert fills[0].price == 108.0  # Gap-through fill at open

    def test_short_stop_gap_through(self):
        """SHORT stop at 95 — open at 92 (gapped past) → fill at open."""

        class GapShortStopStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return StopOrder(
                        side=Side.SHORT,
                        stop_price=95.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 97, 98),
            make_bar(2, 92, 93, 91, 92.5),       # Open=92 <= 95 → fill at 92
            make_bar(3, 92.5, 93, 92, 92.5),
        ]

        engine = BacktestEngine(
            strategy=GapShortStopStrategy(), data=ListProvider(bars), config=NO_COST,
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        assert fills[0].price == 92.0

    def test_stop_order_timeout(self):
        """Stop order cancels after timeout_bars."""

        class StopTimeoutStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return StopOrder(
                        side=Side.LONG,
                        stop_price=120.0,  # Very high — won't fill
                        timeout_bars=3,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [make_bar(i, 100, 101, 99, 100) for i in range(10)]

        engine = BacktestEngine(
            strategy=StopTimeoutStrategy(), data=ListProvider(bars), config=NO_COST,
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) == 0

    def test_stop_order_no_timeout(self):
        """Stop order with timeout_bars=0 stays pending indefinitely."""

        class PersistentStopStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return StopOrder(
                        side=Side.LONG,
                        stop_price=110.0,
                        timeout_bars=0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [make_bar(i, 100, 101, 99, 100) for i in range(8)]
        bars.append(make_bar(8, 100, 112, 99, 111))  # High=112 >= 110 → FILL

        engine = BacktestEngine(
            strategy=PersistentStopStrategy(), data=ListProvider(bars), config=NO_COST,
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        assert fills[0].price == 110.0
        assert fills[0].timestamp == bars[8].timestamp

    def test_stop_order_respects_same_direction(self):
        """Stop order in opposite direction to existing position is rejected."""

        class ConflictStopStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    # First: market LONG entry
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.20,
                        stop_loss_pct=0.20,
                    )
                if self.bars_seen == 2:
                    # Then: stop SHORT (conflict)
                    return StopOrder(
                        side=Side.SHORT,
                        stop_price=95.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),   # Market LONG fills
            make_bar(2, 100, 101, 99, 100),   # StopOrder SHORT placed
            make_bar(3, 99, 100, 93, 94),     # Low=93 <= 95, but rejected
        ]

        engine = BacktestEngine(
            strategy=ConflictStopStrategy(),
            data=ListProvider(bars),
            config=NO_COST,
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        # Only the market LONG entry should fill (stop is rejected)
        entry_fills = [f for f in fills if f.is_entry]
        assert len(entry_fills) == 1
        assert entry_fills[0].side == Side.LONG

    def test_stop_order_in_step_mode(self):
        """StopOrder injected via step() fills correctly."""
        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 100, 101, 99, 100),
            make_bar(2, 100, 106, 99, 105),     # High=106 >= 105 → FILL
            make_bar(3, 105, 106, 104, 105.5),
        ]

        env = StepEngine(data=ListProvider(bars), config=NO_COST)
        obs = env.reset()

        # Place stop order on first step
        stop = StopOrder(
            side=Side.LONG,
            stop_price=105.0,
            take_profit_pct=0.10,
            stop_loss_pct=0.05,
        )
        r1 = env.step(stop)
        assert len(r1.info["fills"]) == 0  # Not yet triggered

        r2 = env.step(None)
        assert len(r2.info["fills"]) >= 1
        assert r2.info["fills"][0].price == 105.0
