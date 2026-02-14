"""CSV and Parquet data provider."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional

import pandas as pd

from ..types import Bar
from .base import DataProvider


class CSVProvider(DataProvider):
    """Load OHLCV data from CSV or Parquet files.

    Expected columns: timestamp, open, high, low, close, volume
    Timestamp can be any pandas-parseable datetime format.

    Args:
        path: Path to CSV or Parquet file.
        symbol_name: Symbol name to tag bars with (e.g. 'ETH').
        timeframe: Bar timeframe (default '1m').
        start: Optional start date filter (inclusive).
        end: Optional end date filter (inclusive).
        timestamp_col: Name of the timestamp column.
    """

    def __init__(
        self,
        path: str | Path,
        symbol_name: str = "",
        timeframe: str = "1m",
        start: Optional[str] = None,
        end: Optional[str] = None,
        timestamp_col: str = "timestamp",
    ):
        self._path = Path(path)
        self._symbol = symbol_name or self._infer_symbol()
        self._timeframe = timeframe
        self._start = start
        self._end = end
        self._timestamp_col = timestamp_col
        self._df: Optional[pd.DataFrame] = None

    def _infer_symbol(self) -> str:
        """Try to extract symbol from filename like 'ETH_1m.csv'."""
        name = self._path.stem
        parts = name.split("_")
        return parts[0] if parts else name

    def _load(self) -> pd.DataFrame:
        """Load and cache the dataframe."""
        if self._df is not None:
            return self._df

        if self._path.suffix == ".parquet":
            df = pd.read_parquet(self._path)
        else:
            df = pd.read_csv(self._path)

        # Normalize timestamp
        if self._timestamp_col in df.columns:
            df["timestamp"] = pd.to_datetime(df[self._timestamp_col])
        elif "date" in df.columns:
            df["timestamp"] = pd.to_datetime(df["date"])
        else:
            # Assume first column is timestamp
            df["timestamp"] = pd.to_datetime(df.iloc[:, 0])

        df = df.sort_values("timestamp").reset_index(drop=True)

        # Filter date range
        if self._start:
            df = df[df["timestamp"] >= self._start]
        if self._end:
            df = df[df["timestamp"] <= self._end]

        # Ensure required columns
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        self._df = df
        return df

    def __iter__(self) -> Iterator[Bar]:
        df = self._load()
        sym = self._symbol
        tf = self._timeframe

        for row in df.itertuples(index=False):
            yield Bar(
                timestamp=row.timestamp.to_pydatetime(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                symbol=sym,
                timeframe=tf,
            )

    def symbol(self) -> str:
        return self._symbol

    def timeframe(self) -> str:
        return self._timeframe

    def reset(self) -> None:
        pass  # Stateless — re-iterates from cached df

    def to_dataframe(self) -> pd.DataFrame:
        """Return the underlying dataframe (useful for indicator pre-computation)."""
        return self._load().copy()

    def __len__(self) -> int:
        return len(self._load())
