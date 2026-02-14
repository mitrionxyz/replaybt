"""Resampler: 1m bars → higher timeframe bars.

This module provides batch resampling utilities using pandas.
For incremental (bar-by-bar) resampling, see _BarAccumulator in base.py.
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import numpy as np


class Resampler:
    """Resample 1m OHLCV dataframe to higher timeframes.

    This is the batch version used for pre-computing indicators
    on resampled data (the same pattern as backtest_combined_clean.py).
    """

    @staticmethod
    def resample(
        df_1m: pd.DataFrame,
        timeframe: str,
    ) -> pd.DataFrame:
        """Resample a 1m dataframe to a higher timeframe.

        Args:
            df_1m: DataFrame with DatetimeIndex and OHLCV columns.
            timeframe: Target timeframe ('5m', '15m', '30m', '1h', etc).

        Returns:
            Resampled DataFrame with OHLCV columns.
        """
        # Normalize timeframe strings
        tf_map = {
            "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1D",
        }
        pd_tf = tf_map.get(timeframe, timeframe)

        resampled = df_1m.resample(pd_tf).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

        return resampled

    @staticmethod
    def add_ema(
        df: pd.DataFrame,
        period: int,
        col: str = "close",
        name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Add EMA column to a dataframe.

        Args:
            df: DataFrame with the source column.
            period: EMA period.
            col: Source column name.
            name: Output column name (default: f'ema_{period}').

        Returns:
            DataFrame with new EMA column added.
        """
        out_name = name or f"ema_{period}"
        df[out_name] = df[col].ewm(span=period, adjust=False).mean()
        return df

    @staticmethod
    def add_rsi_wilder(
        df: pd.DataFrame,
        period: int = 14,
        col: str = "close",
        name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Add Wilder's RSI column to a dataframe.

        Args:
            df: DataFrame with the source column.
            period: RSI period.
            col: Source column name.
            name: Output column name (default: 'rsi').

        Returns:
            DataFrame with new RSI column added.
        """
        out_name = name or "rsi"
        delta = df[col].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss
        df[out_name] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def add_atr(
        df: pd.DataFrame,
        period: int = 14,
        name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Add ATR column to a dataframe.

        Args:
            df: DataFrame with high, low, close columns.
            period: ATR period.
            name: Output column name (default: 'atr').

        Returns:
            DataFrame with new ATR column added.
        """
        out_name = name or "atr"
        tr0 = abs(df["high"] - df["low"])
        tr1 = abs(df["high"] - df["close"].shift())
        tr2 = abs(df["low"] - df["close"].shift())
        tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)
        df[out_name] = tr.rolling(window=period).mean()
        return df

    @staticmethod
    def add_chop(
        df: pd.DataFrame,
        atr_period: int = 14,
        name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Add CHOP (ATR/Price * 100) column.

        Args:
            df: DataFrame with high, low, close columns.
            atr_period: ATR period.
            name: Output column name (default: 'chop').

        Returns:
            DataFrame with new CHOP column added.
        """
        out_name = name or "chop"
        if "atr" not in df.columns:
            Resampler.add_atr(df, atr_period)
        df[out_name] = (df["atr"] / df["close"]) * 100
        return df
