"""Tests for LimitOrder execution in the engine loop."""

import pytest
from datetime import datetime, timedelta
from typing import List, Optional

from replaybt.data.types import Bar, Fill, Position, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import LimitOrder, MarketOrder, CancelPendingLimitsOrder
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


class TestLimitOrderExecution:
    def test_limit_buy_fills_when_price_dips(self):
        """LONG limit at 98 fills when bar low <= 98."""

        class LimitBuyStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return LimitOrder(
                        side=Side.LONG,
                        limit_price=98.0,
                        take_profit_pct=0.05,
                        stop_loss_pct=0.03,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100.5),   # Signal bar
            make_bar(1, 100, 101, 99.5, 100),    # Low=99.5 > 98 → no fill
            make_bar(2, 99, 99.5, 97.5, 98.5),   # Low=97.5 <= 98 → FILL
            make_bar(3, 98.5, 99, 98, 98.8),
        ]

        engine = BacktestEngine(
            strategy=LimitBuyStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        entry = fills[0]
        assert entry.price == 98.0  # Limit price, no slippage
        assert entry.is_entry is True
        assert entry.timestamp == bars[2].timestamp  # Filled on bar 2

    def test_limit_sell_fills_when_price_spikes(self):
        """SHORT limit at 105 fills when bar high >= 105."""

        class LimitSellStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return LimitOrder(
                        side=Side.SHORT,
                        limit_price=105.0,
                        take_profit_pct=0.05,
                        stop_loss_pct=0.03,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100.5),   # Signal bar
            make_bar(1, 100, 103, 99, 101),      # High=103 < 105 → no fill
            make_bar(2, 101, 106, 100, 104),     # High=106 >= 105 → FILL
            make_bar(3, 104, 105, 103, 104.5),
        ]

        engine = BacktestEngine(
            strategy=LimitSellStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        entry = fills[0]
        assert entry.price == 105.0
        assert entry.timestamp == bars[2].timestamp

    def test_limit_order_timeout(self):
        """Limit order cancels after timeout_bars."""

        class LimitWithTimeoutStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return LimitOrder(
                        side=Side.LONG,
                        limit_price=90.0,  # Very low — won't fill
                        timeout_bars=3,
                        take_profit_pct=0.05,
                        stop_loss_pct=0.03,
                    )
                return None

        bars = [make_bar(i, 100 + i * 0.1, 101, 99, 100) for i in range(10)]

        engine = BacktestEngine(
            strategy=LimitWithTimeoutStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        # Should have no fills — limit never reached and timed out
        assert len(fills) == 0

    def test_limit_order_no_timeout(self):
        """Limit order with timeout_bars=0 stays pending indefinitely."""

        class PersistentLimitStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return LimitOrder(
                        side=Side.LONG,
                        limit_price=95.0,
                        timeout_bars=0,  # No timeout
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

        # Price stays above 95 for 8 bars, then dips to fill
        bars = [make_bar(i, 100, 101, 99, 100) for i in range(8)]
        bars.append(make_bar(8, 96, 96.5, 94, 95.5))  # Low=94 <= 95 → FILL

        engine = BacktestEngine(
            strategy=PersistentLimitStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        assert fills[0].price == 95.0
        assert fills[0].timestamp == bars[8].timestamp

    def test_limit_order_uses_maker_fee(self):
        """Limit fills should charge maker_fee, not taker_fee."""

        class LimitStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return LimitOrder(
                        side=Side.LONG,
                        limit_price=99.0,
                        take_profit_pct=0.05,
                        stop_loss_pct=0.03,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 99, 99.5, 98, 99.2),  # Low=98 <= 99 → FILL
            make_bar(2, 99.2, 100, 99, 99.5),
        ]

        engine = BacktestEngine(
            strategy=LimitStrategy(),
            data=ListProvider(bars),
            config={
                "slippage": 0.0,
                "taker_fee": 0.001,   # 0.1%
                "maker_fee": 0.0,     # 0% maker
            },
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        # Maker fee = 0, so entry fees should be 0
        assert fills[0].fees == 0.0

    def test_limit_not_filled_on_signal_bar(self):
        """Limit order placed at bar T cannot fill until bar T+1."""

        class InstantLimitStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    # Limit at 99 — signal bar has low=95 which would fill
                    return LimitOrder(
                        side=Side.LONG,
                        limit_price=99.0,
                        take_profit_pct=0.05,
                        stop_loss_pct=0.03,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 95, 98),     # Signal bar, low=95 < 99
            make_bar(1, 100, 101, 99.5, 100),  # Low=99.5 > 99 → no fill
            make_bar(2, 100, 101, 98, 99),     # Low=98 <= 99 → FILL here
        ]

        engine = BacktestEngine(
            strategy=InstantLimitStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        # Must NOT fill on bar 0 (signal bar), should fill on bar 2
        assert fills[0].timestamp == bars[2].timestamp

    def test_limit_with_merge_position(self):
        """Limit order entry triggers on_fill which returns merge LimitOrder."""

        class LimitWithMergeStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return LimitOrder(
                        side=Side.LONG,
                        limit_price=98.0,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

            def on_fill(self, fill):
                if fill.is_entry and fill.reason != "MERGE":
                    # Scale-in: 1% dip, 50% size, merge into position
                    limit_price = fill.price * (1 - 0.01)  # 97.02
                    return LimitOrder(
                        side=fill.side,
                        limit_price=limit_price,
                        timeout_bars=10,
                        size_usd=fill.size_usd * 0.5,
                        use_maker_fee=True,
                        merge_position=True,
                        cancel_pending_limits=True,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),
            make_bar(1, 99, 99.5, 97, 98.5),    # Limit fills at 98
            make_bar(2, 98.5, 99, 96.5, 97),     # Merge limit at 97.02 → fills
            make_bar(3, 97, 98, 96.5, 97.5),
        ]

        engine = BacktestEngine(
            strategy=LimitWithMergeStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        # Should have entry + merge
        entry_fills = [f for f in fills if f.reason != "MERGE" and f.is_entry]
        merge_fills = [f for f in fills if f.reason == "MERGE"]
        assert len(entry_fills) >= 1
        assert entry_fills[0].price == 98.0
        assert len(merge_fills) >= 1

    def test_market_order_with_merge_position(self):
        """MarketOrder entry triggers on_fill which returns merge LimitOrder."""

        class MarketWithMergeStrategy(Strategy):
            def __init__(self):
                self.bars_seen = 0

            def on_bar(self, bar, indicators, positions):
                self.bars_seen += 1
                if self.bars_seen == 1 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.10,
                        stop_loss_pct=0.05,
                    )
                return None

            def on_fill(self, fill):
                if fill.is_entry and fill.reason != "MERGE":
                    # Scale-in: 0.2% dip, 50% size
                    limit_price = fill.price * (1 - 0.002)
                    return LimitOrder(
                        side=fill.side,
                        limit_price=limit_price,
                        timeout_bars=10,
                        size_usd=fill.size_usd * 0.5,
                        use_maker_fee=True,
                        merge_position=True,
                    )
                return None

        bars = [
            make_bar(0, 100, 101, 99, 100),     # Signal bar
            make_bar(1, 100, 101, 99, 100.5),   # MarketOrder fills at open=100
            make_bar(2, 99.5, 100, 99, 99.5),   # Merge limit at 99.8 → low=99 fills
            make_bar(3, 99.5, 100, 99, 99.8),
        ]

        engine = BacktestEngine(
            strategy=MarketWithMergeStrategy(),
            data=ListProvider(bars),
            config={"slippage": 0.0, "taker_fee": 0.0, "maker_fee": 0.0},
        )

        fills = []
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        # Should have market entry + merge
        entry_fills = [f for f in fills if f.reason != "MERGE" and f.is_entry]
        merge_fills = [f for f in fills if f.reason == "MERGE"]
        assert len(entry_fills) == 1
        assert entry_fills[0].price == 100.0  # Market fill at bar open
        assert len(merge_fills) == 1
        assert merge_fills[0].price == pytest.approx(100.0 * (1 - 0.002))

        # Position should have merged size and averaged entry
        pos = engine.portfolio.positions[0]
        assert pos.size_usd == 15000.0  # 10000 + 5000
        expected_entry = (100.0 * 10000 + 99.8 * 5000) / 15000
        assert pos.entry_price == pytest.approx(expected_entry)
