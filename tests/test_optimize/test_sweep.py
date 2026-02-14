"""Tests for ParameterSweep and SweepResults."""

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from replaybt.data.types import Bar, Side
from replaybt.data.providers.base import DataProvider
from replaybt.engine.orders import MarketOrder
from replaybt.strategy.base import Strategy
from replaybt.optimize.sweep import ParameterSweep
from replaybt.optimize.results import SweepResults


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


def make_bars(n=50, base=100.0, trend=0.05):
    bars = []
    price = base
    for i in range(n):
        o = price
        h = price + 0.5
        l = price - 0.3
        c = price + trend
        bars.append(Bar(
            timestamp=datetime(2024, 1, 1) + timedelta(minutes=i),
            open=o, high=h, low=l, close=c,
            volume=1000, symbol="TEST", timeframe="1m",
        ))
        price = c
    return bars


class SweepableStrategy(Strategy):
    """Strategy that reads TP/SL from config."""

    def __init__(self):
        self._tp = 0.05
        self._sl = 0.03
        self._entry_bar = 3

    def configure(self, config):
        self._tp = config.get("take_profit_pct", 0.05)
        self._sl = config.get("stop_loss_pct", 0.03)
        self._entry_bar = config.get("entry_bar", 3)

    def on_bar(self, bar, indicators, positions):
        if bar.timestamp == datetime(2024, 1, 1) + timedelta(minutes=self._entry_bar):
            if not positions:
                return MarketOrder(
                    side=Side.LONG,
                    take_profit_pct=self._tp,
                    stop_loss_pct=self._sl,
                )
        return None


class TestParameterSweep:
    def test_sweep_runs(self):
        bars = make_bars(30)
        sweep = ParameterSweep(
            strategy_class=SweepableStrategy,
            data=ListProvider(bars),
            base_config={"initial_equity": 10000},
            param_grid={
                "take_profit_pct": [0.04, 0.08],
                "stop_loss_pct": [0.02, 0.04],
            },
            n_workers=1,
        )
        results = sweep.run()
        assert isinstance(results, SweepResults)
        assert len(results) > 0

    def test_sweep_combo_count(self):
        bars = make_bars(30)
        sweep = ParameterSweep(
            strategy_class=SweepableStrategy,
            data=ListProvider(bars),
            base_config={"initial_equity": 10000},
            param_grid={
                "take_profit_pct": [0.04, 0.06, 0.08],
                "stop_loss_pct": [0.02, 0.03],
            },
            n_workers=1,
        )
        results = sweep.run()
        # 3 x 2 = 6 combos
        assert len(results) == 6

    def test_sweep_single_worker(self):
        bars = make_bars(30)
        sweep = ParameterSweep(
            strategy_class=SweepableStrategy,
            data=ListProvider(bars),
            base_config={"initial_equity": 10000},
            param_grid={
                "take_profit_pct": [0.04, 0.08],
            },
            n_workers=1,
        )
        results = sweep.run()
        assert len(results) == 2

    def test_sweep_params_in_results(self):
        bars = make_bars(30)
        sweep = ParameterSweep(
            strategy_class=SweepableStrategy,
            data=ListProvider(bars),
            base_config={"initial_equity": 10000},
            param_grid={
                "take_profit_pct": [0.04, 0.08],
                "stop_loss_pct": [0.02, 0.04],
            },
            n_workers=1,
        )
        results = sweep.run()
        for combo in results.combos:
            assert "take_profit_pct" in combo
            assert "stop_loss_pct" in combo
            assert "net_pnl" in combo
            assert "win_rate" in combo
            assert "max_drawdown_pct" in combo

    def test_sweep_params_in_config(self):
        """Swept params should be accessible to strategy via configure()."""
        bars = make_bars(30)
        sweep = ParameterSweep(
            strategy_class=SweepableStrategy,
            data=ListProvider(bars),
            base_config={"initial_equity": 10000},
            param_grid={
                "take_profit_pct": [0.02, 0.10],
            },
            n_workers=1,
        )
        results = sweep.run()
        # Both should have run with different TP values
        tp_values = {c["take_profit_pct"] for c in results.combos}
        assert tp_values == {0.02, 0.10}


class TestSweepResults:
    @pytest.fixture
    def sample_results(self):
        return SweepResults(combos=[
            {"tp": 0.04, "sl": 0.02, "net_pnl": 100, "win_rate": 60.0,
             "max_drawdown_pct": 5.0, "total_trades": 10},
            {"tp": 0.06, "sl": 0.02, "net_pnl": 200, "win_rate": 65.0,
             "max_drawdown_pct": 8.0, "total_trades": 12},
            {"tp": 0.08, "sl": 0.02, "net_pnl": -50, "win_rate": 40.0,
             "max_drawdown_pct": 15.0, "total_trades": 8},
            {"tp": 0.04, "sl": 0.03, "net_pnl": 150, "win_rate": 70.0,
             "max_drawdown_pct": 4.0, "total_trades": 11},
            {"tp": 0.06, "sl": 0.03, "net_pnl": 300, "win_rate": 72.0,
             "max_drawdown_pct": 6.0, "total_trades": 14},
        ])

    def test_best(self, sample_results):
        top = sample_results.best(metric="net_pnl", n=3)
        assert len(top) == 3
        assert top[0]["net_pnl"] == 300
        assert top[1]["net_pnl"] == 200
        assert top[2]["net_pnl"] == 150

    def test_worst(self, sample_results):
        bottom = sample_results.worst(metric="net_pnl", n=2)
        assert len(bottom) == 2
        assert bottom[0]["net_pnl"] == -50
        assert bottom[1]["net_pnl"] == 100

    def test_filter(self, sample_results):
        filtered = sample_results.filter(sl=0.03)
        assert len(filtered) == 2
        for c in filtered.combos:
            assert c["sl"] == 0.03

    def test_filter_no_match(self, sample_results):
        filtered = sample_results.filter(sl=0.99)
        assert len(filtered) == 0

    def test_summary(self, sample_results):
        text = sample_results.summary(metric="net_pnl", top_n=3)
        assert "Parameter Sweep Results" in text
        assert "net_pnl" in text
        assert len(text) > 50

    def test_summary_empty(self):
        empty = SweepResults(combos=[])
        assert empty.summary() == "No results."

    def test_len(self, sample_results):
        assert len(sample_results) == 5

    def test_to_dataframe(self, sample_results):
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")
        df = sample_results.to_dataframe()
        assert len(df) == 5
        assert "net_pnl" in df.columns
        assert "tp" in df.columns
