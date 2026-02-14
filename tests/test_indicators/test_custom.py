"""Tests for custom indicator registration and the IndicatorManager."""

import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from replaybt.data.types import Bar
from replaybt.indicators.base import Indicator, IndicatorManager


# --- Custom indicator: Highest High over N bars ---

class HighestHigh(Indicator):
    """Custom indicator: tracks highest high over a rolling window."""

    def __init__(self, name: str, period: int = 14):
        super().__init__(name, period)
        self._highs = []
        self._value: Optional[float] = None

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "HighestHigh":
        return cls(name=name, period=config.get("period", 14))

    def update(self, bar: Bar) -> None:
        self._highs.append(bar.high)
        if len(self._highs) > self.period:
            self._highs.pop(0)
        if len(self._highs) >= self.period:
            self._value = max(self._highs)
            self._ready = True

    def value(self) -> Optional[float]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._highs.clear()
        self._value = None


# --- Custom indicator: spread between two prices ---

class Spread(Indicator):
    """Custom indicator: high - low of each bar."""

    def __init__(self, name: str, period: int = 1):
        super().__init__(name, period)
        self._value: Optional[float] = None

    @classmethod
    def from_config(cls, name: str, config: Dict) -> "Spread":
        return cls(name=name)

    def update(self, bar: Bar) -> None:
        self._value = bar.high - bar.low
        self._ready = True

    def value(self) -> Optional[float]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._value = None


def make_bars(n):
    return [
        Bar(datetime(2024, 1, 1) + timedelta(minutes=i),
            100 + i, 102 + i, 98 + i, 101 + i, 1000)
        for i in range(n)
    ]


class TestCustomIndicatorRegistration:
    def test_register_and_use_custom(self):
        """Register a custom indicator type, then use it via config."""
        IndicatorManager.register("highest_high", HighestHigh)

        mgr = IndicatorManager({
            "hh_5": {"type": "highest_high", "period": 5, "timeframe": "1m"},
        })

        bars = make_bars(10)
        for b in bars:
            mgr.update(b)

        val = mgr.get("hh_5")
        assert val is not None
        # Last 5 bars: highs are 107, 108, 109, 110, 111
        assert val == 111.0

    def test_register_multiple_custom(self):
        """Register multiple custom types."""
        IndicatorManager.register("highest_high", HighestHigh)
        IndicatorManager.register("spread", Spread)

        mgr = IndicatorManager({
            "hh": {"type": "highest_high", "period": 3, "timeframe": "1m"},
            "sp": {"type": "spread", "timeframe": "1m"},
        })

        bars = make_bars(5)
        for b in bars:
            mgr.update(b)

        values = mgr.values()
        assert "hh" in values
        assert "sp" in values
        assert values["sp"] == 4.0  # high - low = (102+4) - (98+4) = 4

    def test_custom_alongside_builtin(self):
        """Custom indicators work alongside built-in ones."""
        IndicatorManager.register("spread", Spread)

        mgr = IndicatorManager({
            "my_ema": {"type": "ema", "period": 5, "timeframe": "1m"},
            "my_spread": {"type": "spread", "timeframe": "1m"},
        })

        bars = make_bars(10)
        for b in bars:
            mgr.update(b)

        values = mgr.values()
        assert values["my_ema"] is not None
        assert values["my_spread"] is not None

    def test_unknown_type_gives_helpful_error(self):
        """Requesting an unregistered type gives a clear error with available types."""
        with pytest.raises(ValueError, match="Unknown indicator type"):
            IndicatorManager({
                "bad": {"type": "foobar_indicator", "timeframe": "1m"},
            })

    def test_custom_with_higher_tf(self):
        """Custom indicators work with resampled timeframes."""
        IndicatorManager.register("spread", Spread)

        mgr = IndicatorManager({
            "spread_5m": {"type": "spread", "timeframe": "5m"},
        })

        # Feed 10 minutes of 1m bars → should get 2 completed 5m bars
        bars = make_bars(11)  # Need 11 to complete the second 5m bar
        for b in bars:
            mgr.update(b)

        val = mgr.get("spread_5m")
        assert val is not None


class TestIndicatorManagerBuiltins:
    def test_all_builtin_types_registered(self):
        """All built-in indicator types should be available."""
        mgr = IndicatorManager({})
        expected = {"ema", "sma", "rsi", "atr", "chop", "bollinger", "bb",
                    "macd", "stochastic", "stoch", "vwap", "obv"}
        for t in expected:
            assert t in mgr._registry, f"Missing built-in type: {t}"

    def test_config_with_all_types(self):
        """Can create one of each built-in type."""
        mgr = IndicatorManager({
            "my_ema": {"type": "ema", "period": 10, "timeframe": "1m"},
            "my_sma": {"type": "sma", "period": 10, "timeframe": "1m"},
            "my_rsi": {"type": "rsi", "period": 7, "mode": "wilder", "timeframe": "1m"},
            "my_atr": {"type": "atr", "period": 14, "timeframe": "1m"},
            "my_chop": {"type": "chop", "period": 14, "timeframe": "1m"},
            "my_bb": {"type": "bollinger", "period": 20, "timeframe": "1m"},
            "my_macd": {"type": "macd", "fast_period": 12, "slow_period": 26, "timeframe": "1m"},
            "my_stoch": {"type": "stochastic", "k_period": 14, "timeframe": "1m"},
            "my_vwap": {"type": "vwap", "timeframe": "1m"},
            "my_obv": {"type": "obv", "timeframe": "1m"},
        })

        bars = make_bars(30)
        for b in bars:
            mgr.update(b)

        values = mgr.values()
        assert len(values) == 10
        # At least EMA and OBV should be ready after 30 bars
        assert values["my_ema"] is not None
        assert values["my_obv"] is not None
