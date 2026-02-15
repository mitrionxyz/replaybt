"""Data validation for OHLCV DataFrames and DataProviders."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator, List, Optional

import pandas as pd

from .providers.base import DataProvider
from .types import Bar

logger = logging.getLogger(__name__)

# Timeframe to timedelta mapping
_TIMEFRAME_DELTAS = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "6h": timedelta(hours=6),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}


@dataclass(frozen=True)
class DataIssue:
    """A single data quality issue found during validation.

    Attributes:
        severity: 'ERROR', 'WARNING', or 'INFO'.
        check: Short identifier (e.g. 'gaps', 'duplicates', 'ohlc').
        message: Human-readable description.
        row_index: DataFrame row index if applicable.
        timestamp: Bar timestamp if applicable.
    """

    severity: str
    check: str
    message: str
    row_index: Optional[int] = None
    timestamp: Optional[datetime] = None


class DataValidator:
    """Validate OHLCV DataFrames for common data quality issues.

    Checks for duplicates, ordering, NaN values, OHLC consistency,
    negative volume, gaps, and timezone mixing.

    Args:
        timeframe: Expected bar interval (for gap detection).
        max_gap_ratio: Gaps larger than timeframe * ratio trigger warnings.
    """

    def __init__(self, timeframe: str = "1m", max_gap_ratio: float = 2.0):
        self._timeframe = timeframe
        self._max_gap_ratio = max_gap_ratio

    def validate(self, df: pd.DataFrame) -> List[DataIssue]:
        """Run all checks on a DataFrame.

        Args:
            df: Must have columns: timestamp, open, high, low, close, volume.

        Returns:
            List of DataIssue objects (may be empty if clean).
        """
        issues: List[DataIssue] = []

        if len(df) == 0:
            issues.append(DataIssue("WARNING", "empty", "DataFrame is empty"))
            return issues

        self._check_duplicates(df, issues)
        self._check_monotonic(df, issues)
        self._check_nulls(df, issues)
        self._check_ohlc(df, issues)
        self._check_volume(df, issues)
        self._check_gaps(df, issues)
        self._check_timezone(df, issues)

        return issues

    def _check_duplicates(self, df: pd.DataFrame, issues: List[DataIssue]) -> None:
        """Check for duplicate timestamps."""
        dupes = df[df["timestamp"].duplicated(keep=False)]
        if len(dupes) > 0:
            first_idx = dupes.index[0]
            ts = dupes.iloc[0]["timestamp"]
            issues.append(DataIssue(
                "ERROR", "duplicates",
                f"{len(dupes)} duplicate timestamps found (first at row {first_idx})",
                row_index=int(first_idx),
                timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
            ))

    def _check_monotonic(self, df: pd.DataFrame, issues: List[DataIssue]) -> None:
        """Check that timestamps are strictly increasing."""
        timestamps = df["timestamp"]
        if not timestamps.is_monotonic_increasing:
            # Find first violation
            diffs = timestamps.diff()
            bad = diffs[diffs <= pd.Timedelta(0)]
            if len(bad) > 0:
                idx = bad.index[0]
                ts = df.loc[idx, "timestamp"]
                issues.append(DataIssue(
                    "ERROR", "monotonic",
                    f"Timestamps not strictly increasing (first violation at row {idx})",
                    row_index=int(idx),
                    timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
                ))

    def _check_nulls(self, df: pd.DataFrame, issues: List[DataIssue]) -> None:
        """Check for NaN/None in OHLCV columns."""
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                issues.append(DataIssue("ERROR", "nulls", f"Missing column: {col}"))
                continue
            nulls = df[df[col].isna()]
            if len(nulls) > 0:
                first_idx = nulls.index[0]
                ts = df.loc[first_idx, "timestamp"]
                issues.append(DataIssue(
                    "ERROR", "nulls",
                    f"{len(nulls)} NaN values in '{col}' (first at row {first_idx})",
                    row_index=int(first_idx),
                    timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
                ))

    def _check_ohlc(self, df: pd.DataFrame, issues: List[DataIssue]) -> None:
        """Check OHLC consistency: high >= low, high >= open/close, low <= open/close."""
        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return

        bad_hl = df[df["high"] < df["low"]]
        if len(bad_hl) > 0:
            first_idx = bad_hl.index[0]
            ts = df.loc[first_idx, "timestamp"]
            issues.append(DataIssue(
                "ERROR", "ohlc",
                f"{len(bad_hl)} bars where high < low (first at row {first_idx})",
                row_index=int(first_idx),
                timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
            ))

        bad_ho = df[(df["high"] < df["open"]) | (df["high"] < df["close"])]
        if len(bad_ho) > 0:
            first_idx = bad_ho.index[0]
            ts = df.loc[first_idx, "timestamp"]
            issues.append(DataIssue(
                "ERROR", "ohlc",
                f"{len(bad_ho)} bars where high < open or high < close (first at row {first_idx})",
                row_index=int(first_idx),
                timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
            ))

        bad_lo = df[(df["low"] > df["open"]) | (df["low"] > df["close"])]
        if len(bad_lo) > 0:
            first_idx = bad_lo.index[0]
            ts = df.loc[first_idx, "timestamp"]
            issues.append(DataIssue(
                "ERROR", "ohlc",
                f"{len(bad_lo)} bars where low > open or low > close (first at row {first_idx})",
                row_index=int(first_idx),
                timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
            ))

    def _check_volume(self, df: pd.DataFrame, issues: List[DataIssue]) -> None:
        """Check for negative volume."""
        if "volume" not in df.columns:
            return
        neg = df[df["volume"] < 0]
        if len(neg) > 0:
            first_idx = neg.index[0]
            ts = df.loc[first_idx, "timestamp"]
            issues.append(DataIssue(
                "WARNING", "volume",
                f"{len(neg)} bars with negative volume (first at row {first_idx})",
                row_index=int(first_idx),
                timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
            ))

    def _check_gaps(self, df: pd.DataFrame, issues: List[DataIssue]) -> None:
        """Check for missing bars (gaps larger than expected interval)."""
        expected_delta = _TIMEFRAME_DELTAS.get(self._timeframe)
        if expected_delta is None or len(df) < 2:
            return

        max_gap = expected_delta * self._max_gap_ratio
        timestamps = pd.to_datetime(df["timestamp"])
        diffs = timestamps.diff().dropna()
        gaps = diffs[diffs > max_gap]

        if len(gaps) > 0:
            first_idx = gaps.index[0]
            ts = df.loc[first_idx, "timestamp"]
            gap_size = gaps.iloc[0]
            issues.append(DataIssue(
                "WARNING", "gaps",
                f"{len(gaps)} gaps detected (first: {gap_size} at row {first_idx})",
                row_index=int(first_idx),
                timestamp=ts if isinstance(ts, datetime) else ts.to_pydatetime(),
            ))

    def _check_timezone(self, df: pd.DataFrame, issues: List[DataIssue]) -> None:
        """Check for timezone issues."""
        timestamps = df["timestamp"]
        if hasattr(timestamps.dtype, "tz"):
            return  # Uniform tz-aware, fine

        # Check if any individual values have tz info
        sample = timestamps.iloc[0]
        if isinstance(sample, datetime) and sample.tzinfo is not None:
            issues.append(DataIssue(
                "INFO", "timezone",
                "Timestamps have timezone info but Series dtype is tz-naive. "
                "Consider using tz-aware dtype for consistency.",
            ))

    def report(self, issues: List[DataIssue]) -> str:
        """Format issues as a human-readable report.

        Args:
            issues: List from validate().

        Returns:
            Formatted string report.
        """
        if not issues:
            return "Data validation: CLEAN (no issues found)"

        severity_icons = {"ERROR": "\u2757", "WARNING": "\u26a0\ufe0f", "INFO": "\u2139\ufe0f"}
        errors = sum(1 for i in issues if i.severity == "ERROR")
        warnings = sum(1 for i in issues if i.severity == "WARNING")

        lines = [
            f"Data validation: {len(issues)} issues ({errors} errors, {warnings} warnings)",
            "",
        ]

        for issue in issues:
            icon = severity_icons.get(issue.severity, "?")
            loc = ""
            if issue.row_index is not None:
                loc = f" [row {issue.row_index}]"
            if issue.timestamp is not None:
                loc += f" @ {issue.timestamp}"
            lines.append(f"  {icon} {issue.severity} ({issue.check}){loc}: {issue.message}")

        return "\n".join(lines)


class ValidatedProvider(DataProvider):
    """DataProvider wrapper that validates data on first iteration.

    Logs any issues found. If strict=True, raises ValueError
    when ERROR-level issues are detected.

    Args:
        inner: The DataProvider to wrap.
        strict: If True, raise on ERROR issues.
        timeframe: Override timeframe for validation (defaults to inner.timeframe()).
    """

    def __init__(
        self,
        inner: DataProvider,
        strict: bool = False,
        timeframe: Optional[str] = None,
    ):
        self._inner = inner
        self._strict = strict
        self._timeframe = timeframe
        self._validated = False

    def _validate_once(self) -> None:
        """Run validation on first access."""
        if self._validated:
            return
        self._validated = True

        # Materialize bars to validate
        if hasattr(self._inner, "to_dataframe"):
            df = self._inner.to_dataframe()
        else:
            bars = list(self._inner)
            self._inner.reset()
            if not bars:
                return
            df = pd.DataFrame([
                {
                    "timestamp": b.timestamp,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ])

        tf = self._timeframe or self._inner.timeframe()
        validator = DataValidator(timeframe=tf)
        issues = validator.validate(df)

        if issues:
            report = validator.report(issues)
            logger.warning("Data validation issues:\n%s", report)

            if self._strict:
                errors = [i for i in issues if i.severity == "ERROR"]
                if errors:
                    raise ValueError(
                        f"Data validation failed with {len(errors)} errors. "
                        f"First: {errors[0].message}"
                    )

    def __iter__(self) -> Iterator[Bar]:
        self._validate_once()
        return iter(self._inner)

    def symbol(self) -> str:
        return self._inner.symbol()

    def timeframe(self) -> str:
        return self._inner.timeframe()

    def reset(self) -> None:
        self._inner.reset()
        self._validated = False

    def to_dataframe(self) -> pd.DataFrame:
        """Return inner dataframe if available."""
        self._validate_once()
        if hasattr(self._inner, "to_dataframe"):
            return self._inner.to_dataframe()
        raise AttributeError("Inner provider does not support to_dataframe()")

    def __len__(self) -> int:
        if hasattr(self._inner, "__len__"):
            return len(self._inner)
        raise TypeError("Inner provider does not support len()")


def validate_dataframe(
    df: pd.DataFrame,
    timeframe: str = "1m",
    max_gap_ratio: float = 2.0,
) -> List[DataIssue]:
    """Validate an OHLCV DataFrame for data quality issues.

    Args:
        df: DataFrame with columns: timestamp, open, high, low, close, volume.
        timeframe: Expected bar interval.
        max_gap_ratio: Gap threshold multiplier.

    Returns:
        List of DataIssue objects.
    """
    return DataValidator(timeframe, max_gap_ratio).validate(df)


def validate_provider(provider: DataProvider) -> List[DataIssue]:
    """Validate data from a DataProvider.

    Materializes all bars, validates, and resets the provider.

    Args:
        provider: Any DataProvider instance.

    Returns:
        List of DataIssue objects.
    """
    if hasattr(provider, "to_dataframe"):
        df = provider.to_dataframe()
    else:
        bars = list(provider)
        provider.reset()
        df = pd.DataFrame([
            {
                "timestamp": b.timestamp,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ])

    return DataValidator(timeframe=provider.timeframe()).validate(df)
