#!/usr/bin/env python3
"""
Validate replaybt engine against reference HYPE/LIT Scalper backtest.

The scalper is significantly more complex than TrendMaster:
- Multi-position (max 2)
- Volatility regime (wide/tight TP/SL)
- Weekend TP override
- RSI crossover scale-in (HYPE) / DCA limit scale-in (LIT)
- Post-TP flip (HYPE only)
- HTF RSI early exit (LIT only)
- No breakeven

Matching the reference requires:
- on_fill: returns LimitOrder for DCA setup (fills on same bar via Phase 1b)
- on_exit: returns MarketOrder for post-TP flip (fills at next bar)
- just_closed skip: matches reference Phase 3 skip on close bars
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Reference backtest
sys.path.insert(0, str(Path.home() / "trendtradingstrategyv1"))
from backtest_combined_clean import HypeScalperBacktest, SCALPER_CONFIGS, SLIPPAGE, FEE

# replaybt
from replaybt import (
    BacktestEngine, Bar, Side, Strategy, MarketOrder, LimitOrder,
    CancelPendingLimitsOrder, DataProvider, BacktestResults,
)

DATA_DIR = Path.home() / "trendtradingstrategyv1" / "data"


class ScalperReplaybt(Strategy):
    """HYPE/LIT Scalper ported to replaybt Strategy interface.

    Pre-computes RSI with pandas (same as reference).
    Uses timestamp-based lookups to stay aligned with the reference
    despite engine skipping on_bar on close bars.

    Key integration:
    - on_fill: returns LimitOrder for DCA (LIT), processed in Phase 1b
    - on_exit: returns MarketOrder for post-TP flip (HYPE), processed in Phase 1
    - _clear_pending_limits: engine clears pending limits on TP exit (DCA cancel)
    """

    def __init__(self, symbol: str, df_1m: pd.DataFrame, cfg: dict):
        self.symbol = symbol
        self.df = df_1m
        self.cfg = cfg
        self.is_dca = cfg.get('SCALE_IN_MODE') == 'DCA'

        # Pre-compute RSI
        delta = df_1m['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/cfg['RSI_LEN'], min_periods=cfg['RSI_LEN'], adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/cfg['RSI_LEN'], min_periods=cfg['RSI_LEN'], adjust=False).mean()
        rs = avg_gain / avg_loss
        self.df = df_1m.copy()
        self.df['rsi'] = 100 - (100 / (1 + rs))

        # Pre-compute HTF RSI for early exit (LIT only)
        self.df_htf_rsi = None
        htf_exit_tf = cfg.get('HTF_RSI_EXIT_TF')
        if htf_exit_tf:
            df_30m = df_1m['close'].resample(htf_exit_tf).last().dropna()
            delta_h = df_30m.diff()
            gain_h = delta_h.where(delta_h > 0, 0)
            loss_h = -delta_h.where(delta_h < 0, 0)
            avg_gain_h = gain_h.ewm(alpha=1/cfg['RSI_LEN'], min_periods=cfg['RSI_LEN'], adjust=False).mean()
            avg_loss_h = loss_h.ewm(alpha=1/cfg['RSI_LEN'], min_periods=cfg['RSI_LEN'], adjust=False).mean()
            rs_h = avg_gain_h / avg_loss_h
            self.df_htf_rsi = 100 - (100 / (1 + rs_h))

        # Build timestamp-to-index map for fast lookups
        self._ts_to_idx = {ts: i for i, ts in enumerate(self.df.index)}

        # Volatility tracking
        self.last_vol_update = None
        self.current_volatility = 20.0
        self.base_tp_pct = 0.0
        self.base_sl_pct = 0.0
        self.vol_update_interval = timedelta(hours=4)

        # Position tracking for DCA guard
        self._position_count = 0

    def _calc_daily_volatility(self, current_time: pd.Timestamp) -> float:
        lookback = self.cfg['VOL_LOOKBACK']
        end_date = current_time - timedelta(days=1)
        start_date = end_date - timedelta(days=lookback + 5)
        df_period = self.df[(self.df.index >= start_date) & (self.df.index <= end_date)]
        if df_period.empty:
            return 20.0
        daily = df_period.resample('1D').agg({
            'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna()
        if len(daily) < 3:
            return 20.0
        daily['range_pct'] = (daily['high'] - daily['low']) / daily['low'] * 100
        return daily['range_pct'].tail(lookback).mean()

    def _get_tp_sl(self, volatility: float, is_weekend: bool = False) -> Tuple[float, float]:
        if volatility > self.cfg['VOL_THRESHOLD']:
            tp, sl = self.cfg['WIDE_TP_PCT'], self.cfg['WIDE_SL_PCT']
        else:
            tp, sl = self.cfg['TIGHT_TP_PCT'], self.cfg['TIGHT_SL_PCT']
        if is_weekend and 'WEEKEND_TP_PCT' in self.cfg:
            tp = self.cfg['WEEKEND_TP_PCT']
        return tp, sl

    def _current_tp_sl(self, current_time, for_fill=False):
        """Get current TP/SL based on volatility and weekend.

        Args:
            for_fill: If True, check weekend at fill time (T+1) since
                MarketOrders fill at next bar. Matches reference which
                computes TP/SL at fill bar, not signal bar.
        """
        check_time = current_time + timedelta(minutes=1) if for_fill else current_time
        is_weekend = check_time.weekday() in [5, 6]
        tp_pct = self._get_tp_sl(self.current_volatility, is_weekend=is_weekend)[0] if is_weekend else self.base_tp_pct
        sl_pct = self.base_sl_pct
        return tp_pct, sl_pct

    def check_exits(self, bar, positions):
        """Called every bar (Phase 3.5), even on just_closed bars.

        Updates vol regime (must stay synced with reference which updates
        at top of every bar), then checks HTF RSI exits (LIT only).
        """
        current_time = pd.Timestamp(bar.timestamp)

        # ALWAYS update volatility regime — reference does this at top of
        # every loop iteration, before exits and signals. Must run even
        # on just_closed bars to keep 4-hour boundaries in sync.
        if self.last_vol_update is None or current_time >= self.last_vol_update + self.vol_update_interval:
            self.last_vol_update = current_time
            self.current_volatility = self._calc_daily_volatility(current_time)
            self.base_tp_pct, self.base_sl_pct = self._get_tp_sl(self.current_volatility)

        if self.df_htf_rsi is None or not positions:
            return []

        cfg = self.cfg
        htf_lookup = current_time - timedelta(minutes=30)
        htf_idx = self.df_htf_rsi.index.asof(htf_lookup)
        if pd.isna(htf_idx):
            return []
        rsi_30m = self.df_htf_rsi.loc[htf_idx]
        if pd.isna(rsi_30m):
            return []

        htf_high = cfg['HTF_RSI_EXIT_HIGH']
        htf_low = cfg['HTF_RSI_EXIT_LOW']
        min_pnl = cfg['HTF_RSI_EXIT_MIN_PNL_PCT']
        exits = []
        for idx, pos in enumerate(positions):
            if pos.side == Side.LONG:
                pnl_pct = (bar.close - pos.entry_price) / pos.entry_price * 100
                if rsi_30m > htf_high and pnl_pct >= min_pnl:
                    exits.append((idx, bar.close, 'HTF_RSI_EXIT'))
            else:
                pnl_pct = (pos.entry_price - bar.close) / pos.entry_price * 100
                if rsi_30m < htf_low and pnl_pct >= min_pnl:
                    exits.append((idx, bar.close, 'HTF_RSI_EXIT'))
        return exits

    def on_bar(self, bar: Bar, indicators: dict, positions: list) -> Optional[MarketOrder]:
        current_time = pd.Timestamp(bar.timestamp)
        cfg = self.cfg

        # Get bar index via timestamp
        i = self._ts_to_idx.get(current_time)
        if i is None:
            return None

        # Update volatility regime every 4h
        if self.last_vol_update is None or current_time >= self.last_vol_update + self.vol_update_interval:
            self.last_vol_update = current_time
            self.current_volatility = self._calc_daily_volatility(current_time)
            self.base_tp_pct, self.base_sl_pct = self._get_tp_sl(self.current_volatility)

        tp_pct, sl_pct = self._current_tp_sl(current_time, for_fill=True)

        # Regular signal generation
        if len(positions) < cfg['MAX_POSITIONS']:
            if i > 1:
                prev_rsi = self.df.iloc[i-2]['rsi']
                curr_rsi = self.df.iloc[i-1]['rsi']

                if pd.notna(prev_rsi) and pd.notna(curr_rsi):
                    if self.is_dca:
                        # DCA mode (LIT): only signal Position 1 when no positions
                        if len(positions) == 0:
                            side = None
                            if curr_rsi < cfg['RSI_LOW'] and prev_rsi >= cfg['RSI_LOW']:
                                side = Side.LONG
                            elif curr_rsi > cfg['RSI_HIGH'] and prev_rsi <= cfg['RSI_HIGH']:
                                side = Side.SHORT
                            if side:
                                return MarketOrder(
                                    side=side,
                                    take_profit_pct=tp_pct,
                                    stop_loss_pct=sl_pct,
                                    size_usd=cfg['POSITION_SIZE_USD'],
                                )
                    else:
                        # RSI_CROSS mode (HYPE)
                        if len(positions) == 0:
                            if curr_rsi < cfg['RSI_LOW'] and prev_rsi >= cfg['RSI_LOW']:
                                return MarketOrder(
                                    side=Side.LONG,
                                    take_profit_pct=tp_pct,
                                    stop_loss_pct=sl_pct,
                                    size_usd=cfg['POSITION_SIZE_USD'],
                                )
                            elif curr_rsi > cfg['RSI_HIGH'] and prev_rsi <= cfg['RSI_HIGH']:
                                return MarketOrder(
                                    side=Side.SHORT,
                                    take_profit_pct=tp_pct,
                                    stop_loss_pct=sl_pct,
                                    size_usd=cfg['POSITION_SIZE_USD'],
                                )
                        else:
                            pos1_side = positions[0].side
                            if pos1_side == Side.LONG and curr_rsi < cfg['RSI_LOW'] and prev_rsi >= cfg['RSI_LOW']:
                                return MarketOrder(
                                    side=Side.LONG,
                                    take_profit_pct=tp_pct,
                                    stop_loss_pct=sl_pct,
                                    size_usd=cfg['POSITION_SIZE_USD'],
                                )
                            elif pos1_side == Side.SHORT and curr_rsi > cfg['RSI_HIGH'] and prev_rsi <= cfg['RSI_HIGH']:
                                return MarketOrder(
                                    side=Side.SHORT,
                                    take_profit_pct=tp_pct,
                                    stop_loss_pct=sl_pct,
                                    size_usd=cfg['POSITION_SIZE_USD'],
                                )

        return None

    def on_fill(self, fill):
        """Handle fills — set up DCA limit order for LIT."""
        if fill.is_entry:
            self._position_count += 1

        if not fill.is_entry:
            return None

        # DCA setup: only for LIT, only for Position 1 (first entry)
        if self.is_dca and self._position_count == 1:
            cfg = self.cfg
            dip = cfg['SCALE_IN_DIP']
            if fill.side == Side.LONG:
                limit_price = fill.price * (1 - dip)
            else:
                limit_price = fill.price * (1 + dip)

            tp_pct, sl_pct = self._current_tp_sl(pd.Timestamp(fill.timestamp))

            return LimitOrder(
                side=fill.side,
                limit_price=limit_price,
                timeout_bars=cfg['SCALE_IN_TIMEOUT'],
                take_profit_pct=tp_pct,
                stop_loss_pct=sl_pct,
                size_usd=cfg['POSITION_SIZE_USD'],
                use_maker_fee=False,  # DCA uses taker fee like reference
                min_positions=1,  # Only fill when Position 1 exists
                cancel_pending_limits=True,  # Clear old DCA before adding new
            )

        return None

    def on_exit(self, fill, trade):
        """Handle exits — post-TP flip (HYPE) and DCA cancel (LIT)."""
        self._position_count -= 1

        # DCA cancel: clear pending limits on TP exit when all positions closed
        if self.is_dca and self._position_count == 0:
            if 'TAKE_PROFIT' in trade.reason:
                return CancelPendingLimitsOrder()

        # Post-TP flip (HYPE only): return MarketOrder for immediate flip
        if not self.is_dca and 'TAKE_PROFIT' in trade.reason and self._position_count == 0:
            exit_ts = pd.Timestamp(trade.exit_time)
            idx = self._ts_to_idx.get(exit_ts)
            if idx and idx > 0:
                curr_rsi = self.df.iloc[idx - 1]['rsi']
                if pd.notna(curr_rsi):
                    cfg = self.cfg
                    tp_pct, sl_pct = self._current_tp_sl(exit_ts, for_fill=True)
                    if trade.side == Side.SHORT and curr_rsi < cfg['RSI_LOW']:
                        return MarketOrder(
                            side=Side.LONG,
                            take_profit_pct=tp_pct,
                            stop_loss_pct=sl_pct,
                            size_usd=cfg['POSITION_SIZE_USD'],
                        )
                    elif trade.side == Side.LONG and curr_rsi > cfg['RSI_HIGH']:
                        return MarketOrder(
                            side=Side.SHORT,
                            take_profit_pct=tp_pct,
                            stop_loss_pct=sl_pct,
                            size_usd=cfg['POSITION_SIZE_USD'],
                        )

        return None


class ListProvider(DataProvider):
    def __init__(self, bars, sym="HYPE", tf="1m"):
        self._bars = bars
        self._sym = sym
        self._tf = tf

    def __iter__(self):
        return iter(self._bars)

    def symbol(self):
        return self._sym

    def timeframe(self):
        return self._tf


def load_1m_data(symbol: str, start_date: str, end_date: str):
    """Load 1m data for symbol."""
    patterns = [
        f"{symbol}_merged_1m.csv",
        f"{symbol}_1m.csv",
        f"{symbol}_hyperliquid_1m_full.csv",
        f"{symbol}_bybit_1m_full.csv",
    ]

    for pattern in patterns:
        filepath = DATA_DIR / pattern
        if filepath.exists():
            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp').sort_index()
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            return df

    return None


def compare_trades(ref_trades, rbt_trades, tolerance=1.0):
    """Compare reference and replaybt trades."""
    print(f"\n  Reference trades: {len(ref_trades)}")
    print(f"  Replaybt trades:  {len(rbt_trades)}")

    if len(ref_trades) != len(rbt_trades):
        print(f"\n  Trade count mismatch ({len(ref_trades)} vs {len(rbt_trades)})")
        min_len = min(len(ref_trades), len(rbt_trades))

        # Find first divergence
        for i in range(min_len):
            rt = ref_trades[i]
            bt = rbt_trades[i]
            bt_entry = bt.entry_time
            bt_exit = bt.exit_time
            bt_side = bt.side.value if hasattr(bt.side, 'value') else bt.side
            if rt.entry_time != bt_entry or rt.exit_time != bt_exit or rt.side != bt_side:
                print(f"\n  First divergence at trade {i+1}:")
                print(f"    REF: entry={rt.entry_time}, exit={rt.exit_time}, "
                      f"side={rt.side}, pnl=${rt.pnl_usd:.2f}, reason={rt.reason}")
                print(f"    RBT: entry={bt_entry}, exit={bt_exit}, "
                      f"side={bt_side}, pnl=${bt.pnl_usd:.2f}, reason={bt.reason}")
                break
        else:
            if len(ref_trades) > len(rbt_trades):
                extra = ref_trades[min_len]
                print(f"\n  REF extra trade {min_len+1}: entry={extra.entry_time}, "
                      f"side={extra.side}, reason={extra.reason}")
            else:
                extra = rbt_trades[min_len]
                bt_side = extra.side.value if hasattr(extra.side, 'value') else extra.side
                print(f"\n  RBT extra trade {min_len+1}: entry={extra.entry_time}, "
                      f"side={bt_side}, reason={extra.reason}")

        ref_pnl = sum(t.pnl_usd for t in ref_trades)
        rbt_pnl = sum(t.pnl_usd for t in rbt_trades)
        print(f"\n  PnL:  REF=${ref_pnl:,.2f}  RBT=${rbt_pnl:,.2f}  diff=${abs(ref_pnl-rbt_pnl):,.2f}")
        return False

    mismatches = 0
    max_pnl_diff = 0.0

    for i, (rt, bt) in enumerate(zip(ref_trades, rbt_trades)):
        bt_side = bt.side.value if hasattr(bt.side, 'value') else bt.side
        pnl_diff = abs(rt.pnl_usd - bt.pnl_usd)
        max_pnl_diff = max(max_pnl_diff, pnl_diff)

        entry_match = rt.entry_time == bt.entry_time
        exit_match = rt.exit_time == bt.exit_time
        side_match = rt.side == bt_side
        pnl_match = pnl_diff <= tolerance

        if not (entry_match and exit_match and side_match and pnl_match):
            mismatches += 1
            if mismatches <= 5:
                print(f"\n  Trade {i+1} MISMATCH:")
                if not entry_match:
                    print(f"    Entry: REF={rt.entry_time} vs RBT={bt.entry_time}")
                if not exit_match:
                    print(f"    Exit:  REF={rt.exit_time} vs RBT={bt.exit_time}")
                if not side_match:
                    print(f"    Side:  REF={rt.side} vs RBT={bt_side}")
                if not pnl_match:
                    print(f"    PnL:   REF=${rt.pnl_usd:.2f} vs RBT=${bt.pnl_usd:.2f} (diff=${pnl_diff:.2f})")
                print(f"    REF reason={rt.reason}, RBT reason={bt.reason}")

    print(f"\n  Max PnL diff:  ${max_pnl_diff:.4f}")
    print(f"  Mismatches:    {mismatches}/{len(ref_trades)}")

    if mismatches == 0:
        print(f"\n  PASS: All {len(ref_trades)} trades match within ${tolerance:.2f}!")
        return True
    else:
        print(f"\n  FAIL: {mismatches} trade(s) don't match!")
        return False


def validate_symbol(symbol: str, start_date: str, end_date: str):
    """Run validation for a scalper symbol."""
    print(f"\n{'='*80}")
    print(f"VALIDATING: {symbol} Scalper")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}")

    cfg = SCALPER_CONFIGS[symbol]

    # 1. Reference
    print("\n[1/3] Running reference backtest...")
    ref = HypeScalperBacktest(symbol)
    ref_trades = ref.run(start_date, end_date)
    ref_pnl = ref.equity - 10000
    ref_dd = ref.max_drawdown * 100
    print(f"  Reference: {len(ref_trades)} trades, PnL=${ref_pnl:,.2f}, DD={ref_dd:.1f}%")

    # 2. replaybt
    print("\n[2/3] Running replaybt backtest...")
    df_1m = load_1m_data(symbol, start_date, end_date)
    if df_1m is None:
        print(f"  FAIL: Could not load data for {symbol}")
        return False

    # Convert to bars
    bars = []
    for ts, row in df_1m.iterrows():
        bars.append(Bar(
            timestamp=ts.to_pydatetime(),
            open=row['open'], high=row['high'],
            low=row['low'], close=row['close'],
            volume=row['volume'], symbol=symbol,
        ))

    strategy = ScalperReplaybt(symbol, df_1m, cfg)
    provider = ListProvider(bars, sym=symbol)

    engine = BacktestEngine(
        strategy=strategy,
        data=provider,
        config={
            'initial_equity': 10000,
            'default_size_usd': cfg['POSITION_SIZE_USD'],
            'max_positions': cfg['MAX_POSITIONS'],
            'slippage': SLIPPAGE,
            'taker_fee': FEE,
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

    results = {}

    # HYPE
    results['HYPE'] = validate_symbol('HYPE', start_date, end_date)

    # LIT
    results['LIT'] = validate_symbol('LIT', start_date, end_date)

    # Summary
    print(f"\n{'='*80}")
    print("SCALPER VALIDATION SUMMARY")
    print(f"{'='*80}")
    for symbol, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {symbol} Scalper: {status}")

    all_passed = all(results.values())
    print(f"\n  {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
