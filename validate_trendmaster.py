#!/usr/bin/env python3
"""
Validate replaybt engine against reference TrendMaster backtest.

Runs both the reference implementation (from backtest_combined_clean.py) and a
replaybt Strategy implementation on the same ETH data, then compares trade-by-trade.

PASS: All trade entry/exit times, prices, PnL match within $1 tolerance.
FAIL: Any mismatch → engine bug needs fixing.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Reference backtest
sys.path.insert(0, str(Path.home() / "trendtradingstrategyv1"))
from backtest_combined_clean import TrendMasterBacktest

# replaybt
from replaybt import (
    BacktestEngine, Bar, Side, Strategy, MarketOrder,
    DataProvider, BacktestResults,
)

DATA_DIR = Path.home() / "trendtradingstrategyv1" / "data"


# =============================================================================
# replaybt TrendMaster Strategy
# =============================================================================

class TrendMasterReplaybt(Strategy):
    """TrendMaster ported to replaybt Strategy interface.

    Pre-computes indicators with pandas (same as reference),
    then uses replaybt engine for execution.
    """

    def __init__(self, df_entry: pd.DataFrame, df_1h: pd.DataFrame, cfg: dict):
        self.df_entry = df_entry
        self.df_1h = df_1h
        self.cfg = cfg
        self.entry_tf = cfg['ENTRY_TF']
        self.entry_td = pd.Timedelta(self.entry_tf)
        self.prev_bullish = None
        self.last_entry_bar = None
        self.just_closed = False

    def on_bar(self, bar: Bar, indicators: dict, positions: list) -> Optional[MarketOrder]:
        current_time = pd.Timestamp(bar.timestamp)

        # Track just_closed from on_exit callback
        if self.just_closed:
            self.just_closed = False
            # Still update prev_bullish at bar boundary
            bar_entry = current_time.floor(self.entry_tf)
            if bar_entry != self.last_entry_bar:
                self.last_entry_bar = bar_entry
                completed_entry_time = bar_entry - self.entry_td
                if completed_entry_time in self.df_entry.index:
                    row_entry = self.df_entry.loc[completed_entry_time]
                    self.prev_bullish = row_entry['ema_fast'] > row_entry['ema_slow']
            return None

        bar_entry = current_time.floor(self.entry_tf)
        if bar_entry == self.last_entry_bar:
            return None

        self.last_entry_bar = bar_entry

        # Get COMPLETED entry bar
        completed_entry_time = bar_entry - self.entry_td

        # Get COMPLETED 1h bar
        bar_1h = current_time.floor('1h')
        completed_1h_time = bar_1h - timedelta(hours=1)

        if completed_entry_time not in self.df_entry.index:
            return None
        if completed_1h_time not in self.df_1h.index:
            return None

        row_entry = self.df_entry.loc[completed_entry_time]
        row_1h = self.df_1h.loc[completed_1h_time]

        ema_fast_entry = row_entry['ema_fast']
        ema_slow_entry = row_entry['ema_slow']
        ema_fast_1h = row_1h['ema_fast']
        ema_slow_1h = row_1h['ema_slow']
        close_entry = row_entry['close']
        chop_1h = row_1h['chop']

        trend_up = ema_fast_1h > ema_slow_1h
        trend_down = ema_fast_1h < ema_slow_1h
        curr_bullish = ema_fast_entry > ema_slow_entry

        if self.prev_bullish is not None:
            bullish_cross = curr_bullish and not self.prev_bullish
            bearish_cross = not curr_bullish and self.prev_bullish

            chop_ok = False if pd.isna(chop_1h) else chop_1h <= self.cfg['CHOP_THRESHOLD']

            if not positions and chop_ok:
                if trend_up and bullish_cross and close_entry > ema_fast_entry:
                    self.prev_bullish = curr_bullish
                    return MarketOrder(
                        side=Side.LONG,
                        take_profit_pct=self.cfg['TAKE_PROFIT_PCT'],
                        stop_loss_pct=self.cfg['STOP_LOSS_PCT'],
                        breakeven_trigger_pct=self.cfg['BREAKEVEN_TRIGGER'],
                        breakeven_lock_pct=self.cfg['BREAKEVEN_LOCK'],
                        scale_in_enabled=self.cfg.get('SCALE_IN_ENABLED', False),
                        scale_in_dip_pct=self.cfg.get('SCALE_IN_DIP', 0.002),
                        scale_in_size_pct=self.cfg.get('SCALE_IN_SIZE_PCT', 0.5),
                        scale_in_timeout=self.cfg.get('SCALE_IN_TIMEOUT', 48),
                    )
                elif trend_down and bearish_cross and close_entry < ema_fast_entry:
                    self.prev_bullish = curr_bullish
                    return MarketOrder(
                        side=Side.SHORT,
                        take_profit_pct=self.cfg['TAKE_PROFIT_PCT'],
                        stop_loss_pct=self.cfg['STOP_LOSS_PCT'],
                        breakeven_trigger_pct=self.cfg['BREAKEVEN_TRIGGER'],
                        breakeven_lock_pct=self.cfg['BREAKEVEN_LOCK'],
                        scale_in_enabled=self.cfg.get('SCALE_IN_ENABLED', False),
                        scale_in_dip_pct=self.cfg.get('SCALE_IN_DIP', 0.002),
                        scale_in_size_pct=self.cfg.get('SCALE_IN_SIZE_PCT', 0.5),
                        scale_in_timeout=self.cfg.get('SCALE_IN_TIMEOUT', 48),
                    )

        self.prev_bullish = curr_bullish
        return None

    def on_exit(self, fill, trade):
        self.just_closed = True


class ListProvider(DataProvider):
    """DataProvider from a list of Bar objects."""
    def __init__(self, bars: List[Bar], sym: str = "ETH", tf: str = "1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf


def load_and_prepare(symbol: str, start_date: str, end_date: str, cfg: dict):
    """Load data and pre-compute indicators (same as reference)."""
    from backtest_combined_clean import TRENDMASTER_CONFIG, TRENDMASTER_OVERRIDES

    # Merge config
    merged_cfg = {**TRENDMASTER_CONFIG, **TRENDMASTER_OVERRIDES.get(symbol, {})}

    # Find data file
    patterns = [
        f"{symbol}_binance_1m_full.csv",
        f"{symbol}_merged_1m.csv",
        f"{symbol}_1m.csv",
        f"{symbol}_hyperliquid_1m_full.csv",
    ]

    df_1m = None
    for pattern in patterns:
        filepath = DATA_DIR / pattern
        if filepath.exists():
            df_1m = pd.read_csv(filepath)
            break

    if df_1m is None:
        print(f"No data found for {symbol}")
        return None

    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_1m = df_1m.set_index('timestamp').sort_index()
    df_1m = df_1m[(df_1m.index >= start_date) & (df_1m.index <= end_date)]

    entry_tf = merged_cfg['ENTRY_TF']

    df_entry = df_1m.resample(entry_tf).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()

    df_1h = df_1m.resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()

    df_entry['ema_fast'] = df_entry['close'].ewm(span=merged_cfg['EMA_FAST'], adjust=False).mean()
    df_entry['ema_slow'] = df_entry['close'].ewm(span=merged_cfg['EMA_SLOW'], adjust=False).mean()
    df_1h['ema_fast'] = df_1h['close'].ewm(span=merged_cfg['EMA_FAST'], adjust=False).mean()
    df_1h['ema_slow'] = df_1h['close'].ewm(span=merged_cfg['EMA_SLOW'], adjust=False).mean()

    # CHOP
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['atr'] = df_1h['tr'].rolling(window=merged_cfg['ATR_PERIOD']).mean()
    df_1h['chop'] = (df_1h['atr'] / df_1h['close']) * 100

    # Convert 1m data to Bar objects
    bars = []
    for ts, row in df_1m.iterrows():
        bars.append(Bar(
            timestamp=ts.to_pydatetime(),
            open=row['open'], high=row['high'],
            low=row['low'], close=row['close'],
            volume=row['volume'], symbol=symbol,
        ))

    return {
        'bars': bars, 'df_entry': df_entry, 'df_1h': df_1h,
        'cfg': merged_cfg, 'df_1m': df_1m,
    }


def compare_trades(ref_trades, rbt_trades, tolerance=1.0):
    """Compare reference and replaybt trades."""
    print(f"\n{'='*80}")
    print(f"TRADE-BY-TRADE COMPARISON")
    print(f"{'='*80}")
    print(f"Reference trades: {len(ref_trades)}")
    print(f"Replaybt trades:  {len(rbt_trades)}")

    if len(ref_trades) != len(rbt_trades):
        print(f"\nFAIL: Trade count mismatch!")

        # Find where they diverge
        min_len = min(len(ref_trades), len(rbt_trades))
        for i in range(min_len):
            rt = ref_trades[i]
            bt = rbt_trades[i]
            if rt.entry_time != bt.entry_time or rt.exit_time != bt.exit_time:
                print(f"\n  First divergence at trade {i+1}:")
                print(f"    REF: entry={rt.entry_time}, exit={rt.exit_time}, "
                      f"side={rt.side}, pnl=${rt.pnl_usd:.2f}, reason={rt.reason}")
                print(f"    RBT: entry={bt.entry_time}, exit={bt.exit_time}, "
                      f"side={bt.side}, pnl=${bt.pnl_usd:.2f}, reason={bt.reason}")
                break

        # Show extra trades
        if len(ref_trades) > len(rbt_trades):
            extra = ref_trades[min_len]
            print(f"\n  REF has extra trade {min_len+1}: entry={extra.entry_time}, "
                  f"side={extra.side}, reason={extra.reason}")
        else:
            extra = rbt_trades[min_len]
            print(f"\n  RBT has extra trade {min_len+1}: entry={extra.entry_time}, "
                  f"side={extra.side}, reason={extra.reason}")

        return False

    mismatches = 0
    max_pnl_diff = 0.0

    for i, (rt, bt) in enumerate(zip(ref_trades, rbt_trades)):
        # Convert replaybt side to string
        bt_side = bt.side.value if hasattr(bt.side, 'value') else bt.side
        bt_entry_time = bt.entry_time
        bt_exit_time = bt.exit_time

        pnl_diff = abs(rt.pnl_usd - bt.pnl_usd)
        max_pnl_diff = max(max_pnl_diff, pnl_diff)

        entry_match = rt.entry_time == bt_entry_time
        exit_match = rt.exit_time == bt_exit_time
        side_match = rt.side == bt_side
        pnl_match = pnl_diff <= tolerance

        if not (entry_match and exit_match and side_match and pnl_match):
            mismatches += 1
            if mismatches <= 10:  # Show first 10 mismatches
                print(f"\n  Trade {i+1} MISMATCH:")
                if not entry_match:
                    print(f"    Entry: REF={rt.entry_time} vs RBT={bt_entry_time}")
                if not exit_match:
                    print(f"    Exit:  REF={rt.exit_time} vs RBT={bt_exit_time}")
                if not side_match:
                    print(f"    Side:  REF={rt.side} vs RBT={bt_side}")
                if not pnl_match:
                    print(f"    PnL:   REF=${rt.pnl_usd:.2f} vs RBT=${bt.pnl_usd:.2f} (diff=${pnl_diff:.2f})")
                print(f"    REF reason={rt.reason}, RBT reason={bt.reason}")

    print(f"\n  Max PnL diff:  ${max_pnl_diff:.4f}")
    print(f"  Mismatches:    {mismatches}/{len(ref_trades)}")

    if mismatches == 0:
        print(f"\n  PASS: All {len(ref_trades)} trades match within ${tolerance:.2f} tolerance!")
        return True
    else:
        print(f"\n  FAIL: {mismatches} trade(s) don't match!")
        return False


def validate_symbol(symbol: str, start_date: str, end_date: str):
    """Run validation for a single symbol."""
    print(f"\n{'='*80}")
    print(f"VALIDATING: TrendMaster {symbol}")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}")

    # 1. Run reference backtest
    print("\n[1/3] Running reference backtest...")
    ref = TrendMasterBacktest(symbol)
    ref_trades = ref.run(start_date, end_date)
    ref_pnl = ref.equity - 10000
    ref_dd = ref.max_drawdown * 100
    print(f"  Reference: {len(ref_trades)} trades, PnL=${ref_pnl:,.2f}, DD={ref_dd:.1f}%")

    # 2. Run replaybt backtest
    print("\n[2/3] Running replaybt backtest...")
    data = load_and_prepare(symbol, start_date, end_date, {})
    if not data:
        print("  FAIL: Could not load data")
        return False

    strategy = TrendMasterReplaybt(data['df_entry'], data['df_1h'], data['cfg'])
    provider = ListProvider(data['bars'], sym=symbol)

    engine = BacktestEngine(
        strategy=strategy,
        data=provider,
        config={
            'initial_equity': 10000,
            'default_size_usd': 10000,
            'slippage': 0.0002,
            'taker_fee': 0.00015,
            'maker_fee': 0.0,
        },
    )
    results = engine.run()
    print(f"  Replaybt: {results.total_trades} trades, PnL=${results.net_pnl:,.2f}, DD={results.max_drawdown_pct:.1f}%")

    # 3. Compare
    print("\n[3/3] Comparing trades...")
    return compare_trades(ref_trades, results.trades)


def main():
    start_date = '2024-01-01'
    end_date = '2026-02-08'

    symbols = ['ETH', 'SOL', 'SUI', 'AXS']
    results = {}

    for symbol in symbols:
        results[symbol] = validate_symbol(symbol, start_date, end_date)

    # Summary
    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")
    for symbol, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  TrendMaster {symbol}: {status}")

    all_passed = all(results.values())
    print(f"\n  {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
