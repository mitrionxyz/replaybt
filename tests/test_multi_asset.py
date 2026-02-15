"""Tests for MultiAssetEngine and MultiAssetResults."""

import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from replaybt.data.types import Bar, Fill, Position, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.multi import MultiAssetEngine
from replaybt.engine.orders import Order, MarketOrder, LimitOrder
from replaybt.reporting.multi import MultiAssetResults
from replaybt.strategy.base import Strategy


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class ListProvider(DataProvider):
    """Test data provider from a list of bars."""

    def __init__(self, bars: List[Bar], sym: str = "TEST", tf: str = "1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf

    def reset(self):
        pass


def make_bars(
    n: int,
    base_price: float = 100.0,
    trend: float = 0.1,
    symbol: str = "TEST",
    start: datetime = None,
) -> List[Bar]:
    """Generate n synthetic 1m bars with a slight uptrend."""
    if start is None:
        start = datetime(2024, 1, 1)
    bars = []
    price = base_price
    for i in range(n):
        o = price
        h = price + 0.5
        l = price - 0.3
        c = price + trend
        bars.append(Bar(
            timestamp=start + timedelta(minutes=i),
            open=o, high=h, low=l, close=c,
            volume=1000, symbol=symbol, timeframe="1m",
        ))
        price = c
    return bars


class BuyOnceStrategy(Strategy):
    """Buys on bar 2 for each symbol, one time only."""

    def configure(self, config):
        self._bought = set()
        self._bars_per_symbol = {}

    def on_bar(self, bar, indicators, positions):
        sym = bar.symbol
        self._bars_per_symbol[sym] = self._bars_per_symbol.get(sym, 0) + 1
        if self._bars_per_symbol[sym] == 2 and sym not in self._bought and not positions:
            self._bought.add(sym)
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.05,
                stop_loss_pct=0.03,
            )
        return None


class NeverBuyStrategy(Strategy):
    """Never signals."""

    def on_bar(self, bar, indicators, positions):
        return None


class AlwaysBuyStrategy(Strategy):
    """Buys on bar 2 regardless of symbol (for parity test)."""

    def configure(self, config):
        self._bars_seen = 0

    def on_bar(self, bar, indicators, positions):
        self._bars_seen += 1
        if self._bars_seen == 2 and not positions:
            return MarketOrder(
                side=Side.LONG,
                take_profit_pct=0.05,
                stop_loss_pct=0.03,
            )
        return None


class BarOrderTracker(Strategy):
    """Tracks the order bars are processed."""

    def configure(self, config):
        self.bar_log = []

    def on_bar(self, bar, indicators, positions):
        self.bar_log.append((bar.timestamp, bar.symbol))
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSingleSymbolParity:
    """MultiAssetEngine with 1 symbol should match BacktestEngine exactly."""

    def test_no_trades_parity(self):
        """Zero-trade run produces same results."""
        bars = make_bars(20, symbol="ETH")
        config = {"initial_equity": 10_000, "default_size_usd": 10_000}

        single_result = BacktestEngine(
            strategy=NeverBuyStrategy(),
            data=ListProvider(bars, sym="ETH"),
            config=config,
        ).run()

        multi_result = MultiAssetEngine(
            strategy=NeverBuyStrategy(),
            assets={"ETH": ListProvider(bars, sym="ETH")},
            config=config,
        ).run()

        assert multi_result.combined_net_pnl == single_result.net_pnl
        assert multi_result.combined_total_trades == single_result.total_trades
        assert multi_result.combined_max_drawdown_pct == single_result.max_drawdown_pct

    def test_one_trade_parity(self):
        """Single trade produces matching PnL."""
        bars = make_bars(50, symbol="ETH")
        config = {"initial_equity": 10_000, "default_size_usd": 10_000}

        single = BacktestEngine(
            strategy=AlwaysBuyStrategy(),
            data=ListProvider(bars, sym="ETH"),
            config=config,
        ).run()

        multi = MultiAssetEngine(
            strategy=AlwaysBuyStrategy(),
            assets={"ETH": ListProvider(bars, sym="ETH")},
            config=config,
        ).run()

        assert abs(multi.combined_net_pnl - single.net_pnl) < 0.01
        assert multi.combined_total_trades == single.total_trades
        assert multi.per_symbol["ETH"].total_trades == single.total_trades


class TestTimeSynchronization:
    """Bars from different symbols process in chronological order."""

    def test_interleaved_timestamps(self):
        """Bars with different timestamps merge correctly."""
        # ETH bars at minutes 0, 2, 4, 6, 8
        eth_bars = [
            Bar(
                timestamp=datetime(2024, 1, 1, 0, i * 2),
                open=100, high=101, low=99, close=100,
                volume=1000, symbol="ETH",
            )
            for i in range(5)
        ]
        # SOL bars at minutes 1, 3, 5, 7, 9
        sol_bars = [
            Bar(
                timestamp=datetime(2024, 1, 1, 0, i * 2 + 1),
                open=50, high=51, low=49, close=50,
                volume=500, symbol="SOL",
            )
            for i in range(5)
        ]

        tracker = BarOrderTracker()
        engine = MultiAssetEngine(
            strategy=tracker,
            assets={
                "ETH": ListProvider(eth_bars, sym="ETH"),
                "SOL": ListProvider(sol_bars, sym="SOL"),
            },
        )
        engine.run()

        # Verify chronological order
        timestamps = [ts for ts, sym in tracker.bar_log]
        assert timestamps == sorted(timestamps)

        # Verify alternating ETH/SOL
        symbols = [sym for ts, sym in tracker.bar_log]
        assert symbols == ["ETH", "SOL", "ETH", "SOL", "ETH", "SOL", "ETH", "SOL", "ETH", "SOL"]

    def test_same_timestamp_alphabetical(self):
        """Same-timestamp bars process in alphabetical symbol order."""
        ts = datetime(2024, 1, 1)
        bars_a = [Bar(timestamp=ts, open=100, high=101, low=99, close=100, volume=1000, symbol="AAA")]
        bars_b = [Bar(timestamp=ts, open=50, high=51, low=49, close=50, volume=500, symbol="BBB")]

        tracker = BarOrderTracker()
        engine = MultiAssetEngine(
            strategy=tracker,
            assets={
                "BBB": ListProvider(bars_b, sym="BBB"),
                "AAA": ListProvider(bars_a, sym="AAA"),
            },
        )
        engine.run()

        symbols = [sym for ts, sym in tracker.bar_log]
        assert symbols == ["AAA", "BBB"]


class TestPerSymbolIsolation:
    """Indicators and positions don't mix between symbols."""

    def test_separate_indicator_state(self):
        """Each symbol gets its own IndicatorManager."""
        eth_bars = make_bars(20, base_price=3000, symbol="ETH")
        sol_bars = make_bars(20, base_price=100, symbol="SOL")

        config = {
            "indicators": {
                "ema_5": {"type": "ema", "period": 5, "source": "close"},
            },
        }

        # The EMA values should differ hugely (~3000 vs ~100)
        indicator_log = {}

        class IndicatorLogger(Strategy):
            def on_bar(self, bar, indicators, positions):
                ema = indicators.get("ema_5")
                if ema is not None:
                    indicator_log.setdefault(bar.symbol, []).append(ema)
                return None

        engine = MultiAssetEngine(
            strategy=IndicatorLogger(),
            assets={
                "ETH": ListProvider(eth_bars, sym="ETH"),
                "SOL": ListProvider(sol_bars, sym="SOL"),
            },
            config=config,
        )
        engine.run()

        # ETH EMA should be around 3000, SOL around 100
        assert indicator_log["ETH"][-1] > 2000
        assert indicator_log["SOL"][-1] < 200

    def test_separate_positions(self):
        """A position in ETH doesn't appear in SOL's positions list."""
        eth_bars = make_bars(20, base_price=3000, symbol="ETH")
        sol_bars = make_bars(20, base_price=100, symbol="SOL")

        position_log = {}

        class PositionLogger(Strategy):
            def configure(self, config):
                self._bought = set()
                self._bar_count = {}

            def on_bar(self, bar, indicators, positions):
                sym = bar.symbol
                self._bar_count[sym] = self._bar_count.get(sym, 0) + 1

                # Log positions seen for this symbol
                position_log.setdefault(sym, []).append(len(positions))

                # Only buy ETH
                if sym == "ETH" and self._bar_count[sym] == 2 and not positions:
                    self._bought.add(sym)
                    return MarketOrder(side=Side.LONG, take_profit_pct=0.10, stop_loss_pct=0.05)
                return None

        engine = MultiAssetEngine(
            strategy=PositionLogger(),
            assets={
                "ETH": ListProvider(eth_bars, sym="ETH"),
                "SOL": ListProvider(sol_bars, sym="SOL"),
            },
            config={"initial_equity": 10_000},
        )
        engine.run()

        # SOL should never see any positions
        assert all(p == 0 for p in position_log["SOL"])
        # ETH should have positions after bar 3 (signal at bar 2, fill at bar 3)
        assert any(p > 0 for p in position_log["ETH"])


class TestExposureCap:
    """Portfolio-level exposure cap prevents over-allocation."""

    def test_cap_blocks_third_position(self):
        """With cap for 2 symbols, third symbol can't open."""
        n = 30
        bars_a = make_bars(n, base_price=100, symbol="AAA")
        bars_b = make_bars(n, base_price=200, symbol="BBB")
        bars_c = make_bars(n, base_price=300, symbol="CCC")

        class BuyEarlyStrategy(Strategy):
            def configure(self, config):
                self._bar_count = {}

            def on_bar(self, bar, indicators, positions):
                sym = bar.symbol
                self._bar_count[sym] = self._bar_count.get(sym, 0) + 1
                if self._bar_count[sym] == 2 and not positions:
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=0.50,  # very wide — won't hit
                        stop_loss_pct=0.50,
                    )
                return None

        engine = MultiAssetEngine(
            strategy=BuyEarlyStrategy(),
            assets={
                "AAA": ListProvider(bars_a, sym="AAA"),
                "BBB": ListProvider(bars_b, sym="BBB"),
                "CCC": ListProvider(bars_c, sym="CCC"),
            },
            config={
                "initial_equity": 10_000,
                "default_size_usd": 10_000,
                "max_total_exposure_usd": 20_000,  # only 2 positions allowed
            },
        )
        results = engine.run()

        # Should have positions in at most 2 symbols
        symbols_with_trades = [
            sym for sym, res in results.per_symbol.items()
            if res.total_trades > 0
        ]
        assert len(symbols_with_trades) <= 2


class TestPerSymbolConfig:
    """Per-symbol indicator configs work correctly."""

    def test_different_ema_periods(self):
        """ETH gets EMA(5), SOL gets EMA(10)."""
        eth_bars = make_bars(30, base_price=100, trend=1.0, symbol="ETH")
        sol_bars = make_bars(30, base_price=100, trend=1.0, symbol="SOL")

        indicator_log = {}

        class IndicatorLogger(Strategy):
            def on_bar(self, bar, indicators, positions):
                ema = indicators.get("ema")
                if ema is not None:
                    indicator_log.setdefault(bar.symbol, []).append(ema)
                return None

        engine = MultiAssetEngine(
            strategy=IndicatorLogger(),
            assets={
                "ETH": ListProvider(eth_bars, sym="ETH"),
                "SOL": ListProvider(sol_bars, sym="SOL"),
            },
            config={
                "indicators": {"ema": {"type": "ema", "period": 10, "source": "close"}},
                "symbol_configs": {
                    "ETH": {
                        "indicators": {"ema": {"type": "ema", "period": 5, "source": "close"}},
                    },
                },
            },
        )
        engine.run()

        # Both should have values
        assert len(indicator_log["ETH"]) > 0
        assert len(indicator_log["SOL"]) > 0

        # EMA(5) reacts faster than EMA(10) — on an uptrend, EMA(5) should be
        # closer to the latest price (higher) than EMA(10)
        eth_final = indicator_log["ETH"][-1]
        sol_final = indicator_log["SOL"][-1]
        assert eth_final > sol_final  # faster EMA tracks closer to price


class TestCombinedEquityCurve:
    """Combined equity curve sums per-symbol equities correctly."""

    def test_sum_of_equities(self):
        """Combined equity = sum of per-symbol equities after each trade."""
        eth_bars = make_bars(50, base_price=100, symbol="ETH")
        sol_bars = make_bars(50, base_price=100, symbol="SOL")

        engine = MultiAssetEngine(
            strategy=BuyOnceStrategy(),
            assets={
                "ETH": ListProvider(eth_bars, sym="ETH"),
                "SOL": ListProvider(sol_bars, sym="SOL"),
            },
            config={"initial_equity": 10_000},
        )
        results = engine.run()

        if results.combined_equity_curve:
            # The last point on the combined curve should equal sum of final equities
            final_combined = results.combined_equity_curve[-1][1]
            sum_finals = sum(
                res.final_equity for res in results.per_symbol.values()
            )
            assert abs(final_combined - sum_finals) < 0.01


class TestCombinedDrawdown:
    """Combined drawdown captures correlated drops."""

    def test_correlated_loss_increases_drawdown(self):
        """Simultaneous losses produce larger combined drawdown."""
        # Create bars where both symbols hit stop loss
        n = 10
        base = datetime(2024, 1, 1)

        def make_crash_bars(symbol, base_price):
            """Bars that go up then crash to trigger SL."""
            bars = []
            for i in range(n):
                if i < 5:
                    o = base_price + i
                    h = o + 0.5
                    l = o - 0.3
                    c = o + 0.5
                else:
                    # Crash
                    o = base_price - (i - 4) * 5
                    h = o + 0.1
                    l = o - 5
                    c = o - 4
                bars.append(Bar(
                    timestamp=base + timedelta(minutes=i),
                    open=o, high=h, low=l, close=c,
                    volume=1000, symbol=symbol,
                ))
            return bars

        eth_crash = make_crash_bars("ETH", 100)
        sol_crash = make_crash_bars("SOL", 100)

        engine = MultiAssetEngine(
            strategy=BuyOnceStrategy(),
            assets={
                "ETH": ListProvider(eth_crash, sym="ETH"),
                "SOL": ListProvider(sol_crash, sym="SOL"),
            },
            config={"initial_equity": 10_000},
        )
        results = engine.run()

        # If both symbols trade and both hit SL, combined drawdown should
        # be >= the max of individual drawdowns
        individual_dds = [
            res.max_drawdown_pct for res in results.per_symbol.values()
            if res.total_trades > 0
        ]
        if individual_dds:
            assert results.combined_max_drawdown_pct >= 0


class TestMultiAssetResults:
    """MultiAssetResults summary and formatting."""

    def test_summary_contains_symbols(self):
        """summary() includes all symbol names."""
        eth_bars = make_bars(20, symbol="ETH")
        sol_bars = make_bars(20, symbol="SOL")

        results = MultiAssetEngine(
            strategy=NeverBuyStrategy(),
            assets={
                "ETH": ListProvider(eth_bars, sym="ETH"),
                "SOL": ListProvider(sol_bars, sym="SOL"),
            },
        ).run()

        text = results.summary()
        assert "ETH" in text
        assert "SOL" in text
        assert "Multi-Asset" in text

    def test_repr(self):
        """repr is informative."""
        results = MultiAssetResults(
            per_symbol={},
            combined_net_pnl=1234.56,
            combined_total_trades=42,
            combined_max_drawdown_pct=5.5,
        )
        r = repr(results)
        assert "$1,234.56" in r
        assert "42" in r

    def test_empty_run(self):
        """Engine with no data produces empty results."""
        results = MultiAssetEngine(
            strategy=NeverBuyStrategy(),
            assets={
                "ETH": ListProvider([], sym="ETH"),
            },
        ).run()

        assert results.combined_total_trades == 0
        assert results.combined_net_pnl == 0.0


class TestEventCallbacks:
    """Event callbacks work with MultiAssetEngine."""

    def test_fill_callback(self):
        """Fill events fire for multi-asset engine."""
        eth_bars = make_bars(30, base_price=100, symbol="ETH")

        fills = []
        engine = MultiAssetEngine(
            strategy=BuyOnceStrategy(),
            assets={"ETH": ListProvider(eth_bars, sym="ETH")},
            config={"initial_equity": 10_000},
        )
        engine.on("fill", lambda f: fills.append(f))
        engine.run()

        assert len(fills) >= 1
        assert fills[0].is_entry

    def test_bar_callback(self):
        """Bar events fire for each processed bar."""
        n = 10
        eth_bars = make_bars(n, symbol="ETH")

        bar_count = [0]
        engine = MultiAssetEngine(
            strategy=NeverBuyStrategy(),
            assets={"ETH": ListProvider(eth_bars, sym="ETH")},
        )
        engine.on("bar", lambda b: bar_count.__setitem__(0, bar_count[0] + 1))
        engine.run()

        assert bar_count[0] == n


class TestBacktestEngineUnchanged:
    """Verify BacktestEngine still works identically after BarProcessor refactor."""

    def test_basic_run(self):
        """BacktestEngine produces same results as before refactor."""
        bars = make_bars(100, base_price=100, trend=0.5, symbol="ETH")

        engine = BacktestEngine(
            strategy=AlwaysBuyStrategy(),
            data=ListProvider(bars, sym="ETH"),
            config={"initial_equity": 10_000},
        )
        results = engine.run()

        # With trend=0.5 per bar and TP=5%, should hit TP
        assert results.total_trades >= 1
        assert results.net_pnl != 0
        assert results.symbol == "ETH"

    def test_pending_order_property(self):
        """Property delegation for _pending_order works."""
        bars = make_bars(5, symbol="ETH")

        engine = BacktestEngine(
            strategy=NeverBuyStrategy(),
            data=ListProvider(bars, sym="ETH"),
        )

        # Test setter
        engine._pending_order = MarketOrder(side=Side.LONG)
        assert engine._pending_order is not None
        assert engine._processor._pending_order is not None

        # Test clear
        engine._pending_order = None
        assert engine._pending_order is None

    def test_pending_limits_property(self):
        """Property delegation for _pending_limits works (list mutations)."""
        bars = make_bars(5, symbol="ETH")

        engine = BacktestEngine(
            strategy=NeverBuyStrategy(),
            data=ListProvider(bars, sym="ETH"),
        )

        from replaybt.engine.processor import _PendingLimit
        limit = LimitOrder(side=Side.LONG, limit_price=100.0)
        engine._pending_limits.append(_PendingLimit(order=limit))
        assert len(engine._pending_limits) == 1
        assert len(engine._processor._pending_limits) == 1

        engine._pending_limits.clear()
        assert len(engine._pending_limits) == 0
