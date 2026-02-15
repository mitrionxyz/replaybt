"""Tests for DataValidator, DataIssue, and ValidatedProvider."""

import pytest
from datetime import datetime, timezone

import pandas as pd

from replaybt.data.validation import (
    DataValidator,
    DataIssue,
    ValidatedProvider,
    validate_dataframe,
    validate_provider,
)
from replaybt.data.providers.csv import CSVProvider
from replaybt.data.types import Bar
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_1m.csv"


def _clean_df(n: int = 20) -> pd.DataFrame:
    """Create a clean OHLCV DataFrame with n rows."""
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1min")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [100.0 + i * 0.1 for i in range(n)],
        "high": [101.0 + i * 0.1 for i in range(n)],
        "low": [99.0 + i * 0.1 for i in range(n)],
        "close": [100.5 + i * 0.1 for i in range(n)],
        "volume": [1000.0] * n,
    })


class TestDataValidator:
    def test_clean_data_no_issues(self):
        """Clean data should produce no issues."""
        df = _clean_df()
        issues = DataValidator("1m").validate(df)
        assert len(issues) == 0

    def test_duplicate_timestamps(self):
        """Duplicate timestamps should produce ERROR."""
        df = _clean_df()
        df.loc[5, "timestamp"] = df.loc[4, "timestamp"]
        issues = DataValidator("1m").validate(df)
        errors = [i for i in issues if i.severity == "ERROR" and i.check == "duplicates"]
        assert len(errors) > 0

    def test_non_monotonic_timestamps(self):
        """Non-monotonic timestamps should produce ERROR."""
        df = _clean_df()
        # Swap rows 3 and 4
        df.loc[3, "timestamp"], df.loc[4, "timestamp"] = (
            df.loc[4, "timestamp"],
            df.loc[3, "timestamp"],
        )
        issues = DataValidator("1m").validate(df)
        errors = [i for i in issues if i.severity == "ERROR" and i.check == "monotonic"]
        assert len(errors) > 0

    def test_nan_in_close(self):
        """NaN in close column should produce ERROR."""
        df = _clean_df()
        df.loc[3, "close"] = float("nan")
        issues = DataValidator("1m").validate(df)
        errors = [i for i in issues if i.severity == "ERROR" and i.check == "nulls"]
        assert len(errors) > 0
        assert "close" in errors[0].message

    def test_high_less_than_low(self):
        """high < low should produce ERROR."""
        df = _clean_df()
        df.loc[5, "high"] = 98.0  # Below low of 99.5
        df.loc[5, "low"] = 99.5
        issues = DataValidator("1m").validate(df)
        errors = [i for i in issues if i.severity == "ERROR" and i.check == "ohlc"]
        assert len(errors) > 0

    def test_negative_volume(self):
        """Negative volume should produce WARNING."""
        df = _clean_df()
        df.loc[7, "volume"] = -100.0
        issues = DataValidator("1m").validate(df)
        warnings = [i for i in issues if i.severity == "WARNING" and i.check == "volume"]
        assert len(warnings) == 1

    def test_gap_in_data(self):
        """Missing bars should produce WARNING."""
        df = _clean_df()
        # Create a 5-minute gap by shifting timestamp
        df.loc[10, "timestamp"] = df.loc[9, "timestamp"] + pd.Timedelta(minutes=5)
        # Fix remaining timestamps
        for i in range(11, len(df)):
            df.loc[i, "timestamp"] = df.loc[i - 1, "timestamp"] + pd.Timedelta(minutes=1)
        issues = DataValidator("1m").validate(df)
        warnings = [i for i in issues if i.severity == "WARNING" and i.check == "gaps"]
        assert len(warnings) > 0

    def test_report_clean(self):
        """Report for clean data shows CLEAN."""
        validator = DataValidator("1m")
        report = validator.report([])
        assert "CLEAN" in report

    def test_report_with_issues(self):
        """Report includes severity and check name."""
        issues = [DataIssue("ERROR", "duplicates", "2 duplicate timestamps", row_index=5)]
        validator = DataValidator("1m")
        report = validator.report(issues)
        assert "ERROR" in report
        assert "duplicates" in report


class TestValidatedProvider:
    def test_clean_provider_iterates(self):
        """ValidatedProvider passes through clean data."""
        inner = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        provider = ValidatedProvider(inner)
        bars = list(provider)
        assert len(bars) == 20
        assert isinstance(bars[0], Bar)

    def test_strict_raises_on_error(self, tmp_path):
        """Strict mode raises ValueError when errors are found."""
        # Create bad CSV with high < low
        df = _clean_df(5)
        df.loc[2, "high"] = 90.0  # way below low
        csv_path = tmp_path / "bad.csv"
        df.to_csv(csv_path, index=False)

        inner = CSVProvider(csv_path, symbol_name="TEST")
        provider = ValidatedProvider(inner, strict=True)

        with pytest.raises(ValueError, match="validation failed"):
            list(provider)

    def test_symbol_and_timeframe_delegation(self):
        """Symbol and timeframe delegate to inner provider."""
        inner = CSVProvider(FIXTURE_PATH, symbol_name="ETH", timeframe="5m")
        provider = ValidatedProvider(inner)
        assert provider.symbol() == "ETH"
        assert provider.timeframe() == "5m"


class TestConvenienceFunctions:
    def test_validate_dataframe(self):
        """validate_dataframe returns issues list."""
        df = _clean_df()
        issues = validate_dataframe(df)
        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_validate_provider(self):
        """validate_provider returns issues list."""
        inner = CSVProvider(FIXTURE_PATH, symbol_name="TEST")
        issues = validate_provider(inner)
        assert isinstance(issues, list)
