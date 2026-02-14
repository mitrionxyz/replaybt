"""Tests for CSVProvider."""

import pytest
from pathlib import Path

from replaybt.data.providers.csv import CSVProvider
from replaybt.data.types import Bar


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_1m.csv"


class TestCSVProvider:
    def test_loads_all_bars(self):
        provider = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        bars = list(provider)
        assert len(bars) == 20

    def test_bars_are_bar_type(self):
        provider = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        bar = next(iter(provider))
        assert isinstance(bar, Bar)

    def test_bar_fields_correct(self):
        provider = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        bar = next(iter(provider))
        assert bar.open == 100.0
        assert bar.high == 100.5
        assert bar.low == 99.8
        assert bar.close == 100.2
        assert bar.volume == 1000
        assert bar.symbol == "TEST"
        assert bar.timeframe == "1m"

    def test_chronological_order(self):
        provider = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        bars = list(provider)
        for i in range(1, len(bars)):
            assert bars[i].timestamp > bars[i - 1].timestamp

    def test_date_filtering(self):
        provider = CSVProvider(
            FIXTURE_PATH,
            symbol_name="TEST",
            start="2024-01-01 00:05:00",
            end="2024-01-01 00:10:00",
        )
        bars = list(provider)
        assert len(bars) == 6  # 00:05 through 00:10

    def test_symbol_inference(self):
        provider = CSVProvider(FIXTURE_PATH)
        assert provider.symbol() == "sample"

    def test_explicit_symbol(self):
        provider = CSVProvider(FIXTURE_PATH, symbol_name="ETH")
        assert provider.symbol() == "ETH"

    def test_len(self):
        provider = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        assert len(provider) == 20

    def test_to_dataframe(self):
        provider = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        df = provider.to_dataframe()
        assert len(df) == 20
        assert "open" in df.columns
        assert "close" in df.columns

    def test_re_iteration(self):
        """Provider should support multiple iterations."""
        provider = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        bars1 = list(provider)
        bars2 = list(provider)
        assert len(bars1) == len(bars2)
        assert bars1[0].close == bars2[0].close
