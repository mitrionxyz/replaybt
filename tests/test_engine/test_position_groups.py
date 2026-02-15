"""Tests for position group feature."""

import pytest
from datetime import datetime, timedelta
from typing import List, Optional

from replaybt.data.types import Bar, Fill, Position, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import MarketOrder, LimitOrder
from replaybt.engine.portfolio import Portfolio
from replaybt.engine.execution import ExecutionModel
from replaybt.strategy.base import Strategy


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


def make_bars(n, base_price=100.0, trend=0.0):
    bars = []
    price = base_price
    for i in range(n):
        o = price
        h = price + 0.5
        l = price - 0.5
        c = price + trend
        bars.append(Bar(
            timestamp=datetime(2024, 1, 1) + timedelta(minutes=i),
            open=o, high=h, low=l, close=c,
            volume=1000, symbol="TEST", timeframe="1m",
        ))
        price = c
    return bars


class TestPositionGroupField:
    """group field propagation through Position and Trade."""

    def test_position_has_group_none_by_default(self):
        pos = Position(
            side=Side.LONG, entry_price=100, entry_time=datetime.now(),
            size_usd=10000, stop_loss=95, take_profit=110,
        )
        assert pos.group is None

    def test_position_stores_group(self):
        pos = Position(
            side=Side.LONG, entry_price=100, entry_time=datetime.now(),
            size_usd=10000, stop_loss=95, take_profit=110, group="trend",
        )
        assert pos.group == "trend"

    def test_order_group_propagates_to_position(self):
        portfolio = Portfolio(
            initial_equity=10000, default_size_usd=10000,
            execution=ExecutionModel(slippage=0, taker_fee=0, maker_fee=0),
            max_positions=5,
        )
        bar = make_bars(1)[0]
        order = MarketOrder(side=Side.LONG, group="scalper")
        portfolio.open_position(bar, order, apply_slippage=False)
        assert portfolio.positions[0].group == "scalper"

    def test_group_propagates_to_trade(self):
        portfolio = Portfolio(
            initial_equity=10000, default_size_usd=10000,
            execution=ExecutionModel(slippage=0, taker_fee=0, maker_fee=0),
            max_positions=5,
        )
        bar = make_bars(1)[0]
        order = MarketOrder(
            side=Side.LONG, group="trend",
            take_profit_pct=0.10, stop_loss_pct=0.05,
        )
        portfolio.open_position(bar, order, apply_slippage=False)
        trade = portfolio.close_position(0, 105.0, bar, "SIGNAL", apply_slippage=False)
        assert trade.group == "trend"


class TestPortfolioGroupHelpers:
    """positions_in_group and position_count_in_group."""

    def _make_portfolio(self):
        return Portfolio(
            initial_equity=50000, default_size_usd=10000,
            execution=ExecutionModel(slippage=0, taker_fee=0, maker_fee=0),
            max_positions=10,
        )

    def test_positions_in_group_filters(self):
        portfolio = self._make_portfolio()
        bars = make_bars(3)

        # Open two positions in different groups
        portfolio.open_position(
            bars[0], MarketOrder(side=Side.LONG, group="trend"),
            apply_slippage=False,
        )
        portfolio.open_position(
            bars[1], MarketOrder(side=Side.SHORT, group="scalper"),
            apply_slippage=False,
        )
        portfolio.open_position(
            bars[2], MarketOrder(side=Side.LONG, group="trend"),
            apply_slippage=False,
        )

        assert len(portfolio.positions_in_group("trend")) == 2
        assert len(portfolio.positions_in_group("scalper")) == 1
        assert len(portfolio.positions_in_group(None)) == 0
        assert portfolio.position_count_in_group("trend") == 2

    def test_can_open_with_group(self):
        portfolio = Portfolio(
            initial_equity=50000, default_size_usd=10000,
            execution=ExecutionModel(slippage=0, taker_fee=0, maker_fee=0),
            max_positions=1,  # only 1 per group
        )
        bar = make_bars(1)[0]

        portfolio.open_position(
            bar, MarketOrder(side=Side.LONG, group="trend"),
            apply_slippage=False,
        )

        # trend group is full (1/1)
        assert not portfolio.can_open("trend")
        # scalper group is empty (0/1)
        assert portfolio.can_open("scalper")
        # None group is empty (0/1)
        assert portfolio.can_open(None)


class TestGroupDirectionEnforcement:
    """Direction enforcement scoped within groups."""

    def test_opposite_direction_different_groups_allowed(self):
        """LONG group=trend + SHORT group=scalper should both open."""

        class DualGroupStrategy(Strategy):
            def __init__(self):
                self.bar_count = 0

            def on_bar(self, bar, indicators, positions):
                self.bar_count += 1
                if self.bar_count == 2:
                    return MarketOrder(side=Side.LONG, group="trend",
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                if self.bar_count == 4:
                    return MarketOrder(side=Side.SHORT, group="scalper",
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                return None

        bars = make_bars(10)
        strategy = DualGroupStrategy()
        engine = BacktestEngine(
            strategy=strategy,
            data=ListProvider(bars),
            config={
                "max_positions": 5,
                "same_direction_only": True,
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()

        assert len(engine.portfolio.positions) == 2
        sides = {p.group: p.side for p in engine.portfolio.positions}
        assert sides["trend"] == Side.LONG
        assert sides["scalper"] == Side.SHORT

    def test_same_direction_enforced_within_group(self):
        """Two opposite-direction orders in same group — second rejected."""

        class ConflictStrategy(Strategy):
            def __init__(self):
                self.bar_count = 0

            def on_bar(self, bar, indicators, positions):
                self.bar_count += 1
                if self.bar_count == 2:
                    return MarketOrder(side=Side.LONG, group="trend",
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                if self.bar_count == 4:
                    # Opposite direction, same group — should be rejected
                    return MarketOrder(side=Side.SHORT, group="trend",
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                return None

        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=ConflictStrategy(),
            data=ListProvider(bars),
            config={
                "max_positions": 5,
                "same_direction_only": True,
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()

        # Only the first LONG should exist
        assert len(engine.portfolio.positions) == 1
        assert engine.portfolio.positions[0].side == Side.LONG

    def test_merge_targets_correct_group(self):
        """Merge limit order merges into position of matching group."""

        class MergeGroupStrategy(Strategy):
            def __init__(self):
                self.bar_count = 0

            def on_bar(self, bar, indicators, positions):
                self.bar_count += 1
                if self.bar_count == 2:
                    return MarketOrder(side=Side.LONG, size_usd=5000, group="A",
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                if self.bar_count == 4:
                    return MarketOrder(side=Side.SHORT, size_usd=3000, group="B",
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                return None

            def on_fill(self, fill):
                # After group A fills, queue a merge into A
                if fill.is_entry and fill.reason != "MERGE" and fill.side == Side.LONG:
                    return LimitOrder(
                        side=Side.LONG, size_usd=2000, group="A",
                        limit_price=fill.price - 0.3,
                        merge_position=True,
                    )
                return None

        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=MergeGroupStrategy(),
            data=ListProvider(bars),
            config={
                "max_positions": 5,
                "same_direction_only": True,
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()

        # Group A should have merged (5000 + 2000 = 7000)
        group_a = [p for p in engine.portfolio.positions if p.group == "A"]
        group_b = [p for p in engine.portfolio.positions if p.group == "B"]
        assert len(group_a) == 1
        assert len(group_b) == 1
        assert group_a[0].size_usd == 7000
        assert group_b[0].size_usd == 3000


class TestBackwardCompatibility:
    """All group=None (default) behaves identically to pre-group code."""

    def test_default_group_none_direction_enforcement(self):
        """Without groups, direction enforcement works as before."""

        class OppositeStrategy(Strategy):
            def __init__(self):
                self.bar_count = 0

            def on_bar(self, bar, indicators, positions):
                self.bar_count += 1
                if self.bar_count == 2:
                    return MarketOrder(side=Side.LONG,
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                if self.bar_count == 4:
                    return MarketOrder(side=Side.SHORT,
                                       take_profit_pct=0.50, stop_loss_pct=0.50)
                return None

        bars = make_bars(10)
        engine = BacktestEngine(
            strategy=OppositeStrategy(),
            data=ListProvider(bars),
            config={
                "max_positions": 5,
                "same_direction_only": True,
                "slippage": 0, "taker_fee": 0,
            },
        )
        engine.run()

        # SHORT should be rejected (same group=None, opposite direction)
        assert len(engine.portfolio.positions) == 1
        assert engine.portfolio.positions[0].side == Side.LONG
