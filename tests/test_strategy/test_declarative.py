"""Tests for DeclarativeStrategy."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Iterator

import pytest

from replaybt.data.types import Bar, Side, Position
from replaybt.data.providers.base import DataProvider
from replaybt.engine.loop import BacktestEngine
from replaybt.engine.orders import MarketOrder
from replaybt.strategy.declarative import (
    CompareCondition,
    CrossoverCondition,
    DeclarativeStrategy,
    ThresholdCondition,
    evaluate_all,
    evaluate_condition,
    parse_condition,
    parse_conditions,
    resolve_operand,
)


def _bar(close=100.0, open_=100.0, high=101.0, low=99.0):
    """Helper to create a test bar."""
    return Bar(
        timestamp=datetime(2025, 1, 1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        symbol="TEST",
        timeframe="1m",
    )


# ── resolve_operand ──────────────────────────────────────────────────────


class TestResolveOperand:
    def test_bar_close(self):
        bar = _bar(close=105.0)
        assert resolve_operand("bar.close", bar, {}) == 105.0

    def test_bar_open(self):
        bar = _bar(open_=99.5)
        assert resolve_operand("bar.open", bar, {}) == 99.5

    def test_bar_high(self):
        bar = _bar(high=110.0)
        assert resolve_operand("bar.high", bar, {}) == 110.0

    def test_indicator_name(self):
        assert resolve_operand("ema_fast", _bar(), {"ema_fast": 50.0}) == 50.0

    def test_missing_indicator(self):
        assert resolve_operand("nonexistent", _bar(), {}) is None

    def test_invalid_bar_attr(self):
        assert resolve_operand("bar.nonexistent", _bar(), {}) is None


# ── evaluate_condition ───────────────────────────────────────────────────


class TestEvaluateCondition:
    def test_crossover_triggers(self):
        cond = CrossoverCondition(fast="ema_f", slow="ema_s")
        prev = {"ema_f": 10.0, "ema_s": 11.0}  # fast < slow
        curr = {"ema_f": 12.0, "ema_s": 11.0}  # fast > slow
        assert evaluate_condition(cond, _bar(), curr, prev) is True

    def test_crossover_no_trigger(self):
        cond = CrossoverCondition(fast="ema_f", slow="ema_s")
        prev = {"ema_f": 12.0, "ema_s": 11.0}  # already above
        curr = {"ema_f": 13.0, "ema_s": 11.0}  # still above
        assert evaluate_condition(cond, _bar(), curr, prev) is False

    def test_crossunder_triggers(self):
        cond = CrossoverCondition(fast="ema_f", slow="ema_s", is_crossunder=True)
        prev = {"ema_f": 12.0, "ema_s": 11.0}  # fast > slow
        curr = {"ema_f": 10.0, "ema_s": 11.0}  # fast < slow
        assert evaluate_condition(cond, _bar(), curr, prev) is True

    def test_above(self):
        cond = CompareCondition(left="bar.close", right="ema", op="above")
        assert evaluate_condition(cond, _bar(close=105), {"ema": 100}, {}) is True
        assert evaluate_condition(cond, _bar(close=95), {"ema": 100}, {}) is False

    def test_below(self):
        cond = CompareCondition(left="bar.close", right="ema", op="below")
        assert evaluate_condition(cond, _bar(close=95), {"ema": 100}, {}) is True

    def test_above_threshold(self):
        cond = ThresholdCondition(indicator="chop", value=1.1, op="above_threshold")
        assert evaluate_condition(cond, _bar(), {"chop": 1.5}, {}) is True
        assert evaluate_condition(cond, _bar(), {"chop": 0.9}, {}) is False

    def test_below_threshold(self):
        cond = ThresholdCondition(indicator="chop", value=1.1, op="below_threshold")
        assert evaluate_condition(cond, _bar(), {"chop": 0.9}, {}) is True
        assert evaluate_condition(cond, _bar(), {"chop": 1.1}, {}) is True  # <= 1.1

    def test_crosses_below(self):
        cond = ThresholdCondition(indicator="rsi", value=30.0, op="crosses_below")
        prev = {"rsi": 35.0}
        curr = {"rsi": 25.0}
        assert evaluate_condition(cond, _bar(), curr, prev) is True

    def test_crosses_above(self):
        cond = ThresholdCondition(indicator="rsi", value=70.0, op="crosses_above")
        prev = {"rsi": 65.0}
        curr = {"rsi": 75.0}
        assert evaluate_condition(cond, _bar(), curr, prev) is True

    def test_none_operand_returns_false(self):
        cond = CrossoverCondition(fast="missing", slow="also_missing")
        assert evaluate_condition(cond, _bar(), {}, {}) is False

    def test_threshold_none_returns_false(self):
        cond = ThresholdCondition(indicator="missing", value=1.0, op="above_threshold")
        assert evaluate_condition(cond, _bar(), {}, {}) is False


# ── parse_conditions ─────────────────────────────────────────────────────


class TestParseConditions:
    def test_crossover(self):
        cond = parse_condition({"type": "crossover", "fast": "a", "slow": "b"})
        assert isinstance(cond, CrossoverCondition)
        assert cond.fast == "a"
        assert cond.is_crossunder is False

    def test_crossunder(self):
        cond = parse_condition({"type": "crossunder", "fast": "a", "slow": "b"})
        assert isinstance(cond, CrossoverCondition)
        assert cond.is_crossunder is True

    def test_above(self):
        cond = parse_condition({"type": "above", "left": "x", "right": "y"})
        assert isinstance(cond, CompareCondition)
        assert cond.op == "above"

    def test_below_threshold(self):
        cond = parse_condition(
            {"type": "below_threshold", "indicator": "chop", "value": 1.1}
        )
        assert isinstance(cond, ThresholdCondition)
        assert cond.value == 1.1

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown condition type"):
            parse_condition({"type": "invalid_type"})

    def test_parse_list(self):
        raw = [
            {"type": "crossover", "fast": "a", "slow": "b"},
            {"type": "above", "left": "x", "right": "y"},
        ]
        conds = parse_conditions(raw)
        assert len(conds) == 2
        assert isinstance(conds[0], CrossoverCondition)
        assert isinstance(conds[1], CompareCondition)


# ── evaluate_all ─────────────────────────────────────────────────────────


class TestEvaluateAll:
    def test_all_pass(self):
        conds = [
            CompareCondition(left="bar.close", right="ema", op="above"),
            ThresholdCondition(indicator="chop", value=1.1, op="below_threshold"),
        ]
        indicators = {"ema": 95.0, "chop": 0.9}
        assert evaluate_all(conds, _bar(close=100), indicators, {}) is True

    def test_one_fails(self):
        """3 of 4 pass = no signal."""
        conds = [
            CompareCondition(left="bar.close", right="ema", op="above"),
            ThresholdCondition(indicator="chop", value=1.1, op="below_threshold"),
            ThresholdCondition(indicator="rsi", value=70.0, op="below_threshold"),
            CompareCondition(left="ema_fast", right="ema_slow", op="above"),
        ]
        indicators = {"ema": 95.0, "chop": 0.9, "rsi": 50.0, "ema_fast": 10, "ema_slow": 20}
        # ema_fast < ema_slow → fails
        assert evaluate_all(conds, _bar(close=100), indicators, {}) is False

    def test_empty_conditions(self):
        assert evaluate_all([], _bar(), {}, {}) is False


# ── DeclarativeStrategy ─────────────────────────────────────────────────


def _make_config(**overrides):
    """Build a minimal TrendMaster-like config."""
    config = {
        "name": "TestStrategy",
        "indicators": {
            "ema_fast": {"type": "ema", "timeframe": "1m", "period": 3},
            "ema_slow": {"type": "ema", "timeframe": "1m", "period": 5},
        },
        "entry": {
            "long": {
                "conditions": [
                    {"type": "crossover", "fast": "ema_fast", "slow": "ema_slow"},
                ]
            },
            "short": {
                "conditions": [
                    {"type": "crossunder", "fast": "ema_fast", "slow": "ema_slow"},
                ]
            },
        },
        "exit": {
            "take_profit_pct": 0.08,
            "stop_loss_pct": 0.035,
        },
    }
    config.update(overrides)
    return config


class TestDeclarativeStrategy:
    def test_crossover_long(self):
        """EMA cross triggers LONG."""
        strat = DeclarativeStrategy(_make_config())
        bar = _bar(close=105)
        prev = {"ema_fast": 10.0, "ema_slow": 11.0}
        curr = {"ema_fast": 12.0, "ema_slow": 11.0}

        # Set prev values
        strat._prev_values = prev
        order = strat.on_bar(bar, curr, [])

        assert order is not None
        assert order.side == Side.LONG

    def test_crossover_short(self):
        """EMA cross triggers SHORT."""
        strat = DeclarativeStrategy(_make_config())
        bar = _bar(close=95)
        prev = {"ema_fast": 12.0, "ema_slow": 11.0}
        curr = {"ema_fast": 10.0, "ema_slow": 11.0}

        strat._prev_values = prev
        order = strat.on_bar(bar, curr, [])

        assert order is not None
        assert order.side == Side.SHORT

    def test_no_signal_without_crossover(self):
        """Same state = no signal."""
        strat = DeclarativeStrategy(_make_config())
        bar = _bar()
        prev = {"ema_fast": 12.0, "ema_slow": 11.0}
        curr = {"ema_fast": 13.0, "ema_slow": 11.0}  # still above, no cross

        strat._prev_values = prev
        order = strat.on_bar(bar, curr, [])
        assert order is None

    def test_threshold_blocks(self):
        """CHOP > threshold blocks signal."""
        config = _make_config()
        config["entry"]["long"]["conditions"].append(
            {"type": "below_threshold", "indicator": "chop", "value": 1.1}
        )
        strat = DeclarativeStrategy(config)

        prev = {"ema_fast": 10.0, "ema_slow": 11.0, "chop": 1.5}
        curr = {"ema_fast": 12.0, "ema_slow": 11.0, "chop": 1.5}  # CHOP too high

        strat._prev_values = prev
        order = strat.on_bar(_bar(), curr, [])
        assert order is None

    def test_threshold_passes(self):
        """CHOP <= threshold allows signal."""
        config = _make_config()
        config["entry"]["long"]["conditions"].append(
            {"type": "below_threshold", "indicator": "chop", "value": 1.1}
        )
        strat = DeclarativeStrategy(config)

        prev = {"ema_fast": 10.0, "ema_slow": 11.0, "chop": 0.9}
        curr = {"ema_fast": 12.0, "ema_slow": 11.0, "chop": 0.9}

        strat._prev_values = prev
        order = strat.on_bar(_bar(), curr, [])
        assert order is not None
        assert order.side == Side.LONG

    def test_price_above_indicator(self):
        """bar.close > ema evaluates correctly."""
        config = _make_config()
        config["entry"]["long"]["conditions"].append(
            {"type": "above", "left": "bar.close", "right": "ema_fast"}
        )
        strat = DeclarativeStrategy(config)

        prev = {"ema_fast": 10.0, "ema_slow": 11.0}
        curr = {"ema_fast": 95.0, "ema_slow": 11.0}  # bar.close=100 > ema_fast=95

        strat._prev_values = prev
        order = strat.on_bar(_bar(close=100), curr, [])
        assert order is not None

    def test_exit_config_on_order(self):
        """TP/SL/breakeven on MarketOrder."""
        config = _make_config(exit={
            "take_profit_pct": 0.12,
            "stop_loss_pct": 0.04,
            "breakeven_trigger_pct": 0.015,
            "breakeven_lock_pct": 0.005,
        })
        strat = DeclarativeStrategy(config)

        prev = {"ema_fast": 10.0, "ema_slow": 11.0}
        curr = {"ema_fast": 12.0, "ema_slow": 11.0}

        strat._prev_values = prev
        order = strat.on_bar(_bar(), curr, [])

        assert order.take_profit_pct == 0.12
        assert order.stop_loss_pct == 0.04
        assert order.breakeven_trigger_pct == 0.015
        assert order.breakeven_lock_pct == 0.005

    def test_scale_in_on_order(self):
        """Scale-in params on MarketOrder."""
        config = _make_config(scale_in={
            "enabled": True,
            "dip_pct": 0.002,
            "size_pct": 0.5,
            "timeout": 48,
        })
        strat = DeclarativeStrategy(config)

        prev = {"ema_fast": 10.0, "ema_slow": 11.0}
        curr = {"ema_fast": 12.0, "ema_slow": 11.0}

        strat._prev_values = prev
        order = strat.on_bar(_bar(), curr, [])

        assert order.scale_in_enabled is True
        assert order.scale_in_dip_pct == 0.002
        assert order.scale_in_size_pct == 0.5
        assert order.scale_in_timeout == 48

    def test_no_signal_with_positions(self):
        """Skip when positions exist."""
        strat = DeclarativeStrategy(_make_config())

        prev = {"ema_fast": 10.0, "ema_slow": 11.0}
        curr = {"ema_fast": 12.0, "ema_slow": 11.0}

        strat._prev_values = prev
        fake_pos = Position(
            side=Side.LONG, entry_price=100.0,
            entry_time=datetime(2025, 1, 1), size_usd=10000.0,
            stop_loss=96.5, take_profit=108.0,
        )
        order = strat.on_bar(_bar(), curr, [fake_pos])
        assert order is None

    def test_indicator_config_extraction(self):
        """indicator_config() returns dict."""
        config = _make_config()
        strat = DeclarativeStrategy(config)
        ic = strat.indicator_config()

        assert "ema_fast" in ic
        assert ic["ema_fast"]["type"] == "ema"
        assert ic["ema_fast"]["period"] == 3

    def test_from_json(self):
        """Load from JSON file."""
        config = _make_config()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
        ) as f:
            json.dump(config, f)
            f.flush()
            path = f.name

        try:
            strat = DeclarativeStrategy.from_json(path)
            assert strat._name == "TestStrategy"
            assert len(strat._long_conds) == 1
        finally:
            os.unlink(path)

    def test_null_indicator_safe(self):
        """None values don't trigger signals."""
        strat = DeclarativeStrategy(_make_config())

        # All indicators None (warmup period)
        order = strat.on_bar(_bar(), {}, [])
        assert order is None

    def test_crosses_below_threshold(self):
        """RSI crossing below value."""
        cond = parse_condition(
            {"type": "crosses_below", "indicator": "rsi", "value": 25.0}
        )
        prev = {"rsi": 30.0}
        curr = {"rsi": 20.0}
        assert evaluate_condition(cond, _bar(), curr, prev) is True

        # Not crossing (already below)
        prev2 = {"rsi": 20.0}
        assert evaluate_condition(cond, _bar(), curr, prev2) is False

    def test_crosses_above_threshold(self):
        """RSI crossing above value."""
        cond = parse_condition(
            {"type": "crosses_above", "indicator": "rsi", "value": 75.0}
        )
        prev = {"rsi": 70.0}
        curr = {"rsi": 80.0}
        assert evaluate_condition(cond, _bar(), curr, prev) is True

    def test_end_to_end_with_engine(self):
        """Full run with synthetic bars produces trades."""

        class _RisingFallingProvider(DataProvider):
            """Bars that oscillate to trigger EMA crossovers."""

            def __iter__(self) -> Iterator[Bar]:
                base = datetime(2025, 1, 1)
                # Phase 1: rising (triggers long crossover)
                for i in range(30):
                    p = 100 + i * 2.0
                    yield Bar(
                        timestamp=base + timedelta(minutes=i),
                        open=p, high=p + 1, low=p - 1, close=p,
                        volume=1000.0, symbol="TEST", timeframe="1m",
                    )
                # Phase 2: falling (triggers short crossover, closes long via SL/TP)
                for i in range(30):
                    p = 160 - i * 2.0
                    yield Bar(
                        timestamp=base + timedelta(minutes=30 + i),
                        open=p, high=p + 1, low=p - 1, close=p,
                        volume=1000.0, symbol="TEST", timeframe="1m",
                    )

            def symbol(self) -> str:
                return "TEST"

            def timeframe(self) -> str:
                return "1m"

        config = _make_config()
        strat = DeclarativeStrategy(config)

        engine = BacktestEngine(
            strategy=strat,
            data=_RisingFallingProvider(),
            config={
                "indicators": strat.indicator_config(),
                "slippage": 0.0,
                "taker_fee": 0.0,
            },
        )
        results = engine.run()

        # Should produce at least one trade from crossovers
        assert results.total_trades >= 1

    def test_prev_values_updated(self):
        """_prev_values updated at end of every on_bar() call."""
        strat = DeclarativeStrategy(_make_config())

        curr = {"ema_fast": 12.0, "ema_slow": 11.0}
        strat.on_bar(_bar(), curr, [])

        assert strat._prev_values == curr
