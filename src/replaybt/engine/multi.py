"""MultiAssetEngine: time-synchronized multi-symbol backtesting.

Runs multiple symbols through the same strategy in a single
time-synchronized loop. This captures correlated drawdowns that
running separate BacktestEngine instances would miss.

Key features:
  - Per-symbol Portfolio, IndicatorManager, and BarProcessor
  - Shared ExecutionModel and Strategy
  - Time-synchronized bar processing via min-heap merge
  - Optional portfolio-level exposure cap
  - Per-symbol config overrides
"""

from __future__ import annotations

import heapq
from typing import Callable, Dict, List, Optional

from ..data.types import Bar
from ..data.providers.base import DataProvider
from ..indicators.base import IndicatorManager
from ..strategy.base import Strategy
from ..reporting.multi import MultiAssetResults
from .execution import ExecutionModel
from .portfolio import Portfolio
from .processor import BarProcessor


class MultiAssetEngine:
    """Run a strategy against multiple assets in a time-synchronized loop.

    Args:
        strategy: Strategy instance (shared across all symbols).
        assets: {symbol: DataProvider} mapping.
        config: Engine configuration dict.

    Config keys:
        initial_equity: Starting equity per symbol (default 10000).
        default_size_usd: Default position size per symbol (default 10000).
        max_positions: Max concurrent positions per symbol (default 1).
        slippage: Per-side slippage (default 0.0002).
        taker_fee: Per-side taker fee (default 0.00015).
        maker_fee: Per-side maker fee (default 0.0).
        indicators: Default indicator configs for all symbols.
        skip_signal_on_close: Skip on_bar on bars where a position closed
            (default True).
        same_direction_only: Reject orders in opposite direction (default True).
        max_total_exposure_usd: Optional portfolio-level exposure cap.
        symbol_configs: Per-symbol config overrides.
            {symbol: {key: value, ...}} — overrides default config keys.

    Example config:
        {
            "initial_equity": 10_000,
            "indicators": {"ema_fast": {"type": "ema", "period": 15}},
            "symbol_configs": {
                "ETH": {"indicators": {"ema_fast": {"type": "ema", "period": 10}}},
            },
            "max_total_exposure_usd": 50_000,
        }
    """

    def __init__(
        self,
        strategy: Strategy,
        assets: Dict[str, DataProvider],
        config: Optional[Dict] = None,
    ):
        self.strategy = strategy
        self.assets = assets
        self.config = config or {}

        # Shared execution model
        self.execution = ExecutionModel(
            slippage=self.config.get("slippage", 0.0002),
            taker_fee=self.config.get("taker_fee", 0.00015),
            maker_fee=self.config.get("maker_fee", 0.0),
        )

        # Exposure cap
        self._max_total_exposure: Optional[float] = self.config.get(
            "max_total_exposure_usd"
        )

        # Per-symbol overrides
        symbol_configs = self.config.get("symbol_configs", {})

        # Build per-symbol state
        self._portfolios: Dict[str, Portfolio] = {}
        self._indicators: Dict[str, IndicatorManager] = {}
        self._processors: Dict[str, BarProcessor] = {}

        # Event callbacks
        self._callbacks: Dict[str, List[Callable]] = {
            "bar": [],
            "fill": [],
            "exit": [],
            "signal": [],
        }

        for sym in sorted(assets.keys()):
            sym_cfg = self._resolve_config(sym, symbol_configs)

            portfolio = Portfolio(
                initial_equity=sym_cfg.get("initial_equity", 10_000.0),
                default_size_usd=sym_cfg.get("default_size_usd", 10_000.0),
                execution=self.execution,
                max_positions=sym_cfg.get("max_positions", 1),
                sizer=sym_cfg.get("sizer"),
            )
            self._portfolios[sym] = portfolio

            indicators = IndicatorManager(sym_cfg.get("indicators", {}))
            self._indicators[sym] = indicators

            processor = BarProcessor(
                portfolio=portfolio,
                indicators=indicators,
                execution=self.execution,
                strategy=self.strategy,
                config=sym_cfg,
                callbacks=self._callbacks,
            )
            self._processors[sym] = processor

        # Track first/last bar per symbol
        self._first_bars: Dict[str, Optional[Bar]] = {sym: None for sym in assets}
        self._last_bars: Dict[str, Optional[Bar]] = {sym: None for sym in assets}

        # Configure strategy once
        self.strategy.configure(self.config)

    def _resolve_config(
        self, symbol: str, symbol_configs: Dict
    ) -> Dict:
        """Merge default config with per-symbol overrides."""
        base = {k: v for k, v in self.config.items() if k != "symbol_configs"}
        overrides = symbol_configs.get(symbol, {})
        merged = {**base, **overrides}
        return merged

    def on(self, event: str, callback: Callable) -> "MultiAssetEngine":
        """Register an event callback.

        Events: 'bar', 'fill', 'exit', 'signal'
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
        return self

    def run(self) -> MultiAssetResults:
        """Execute the multi-asset backtest.

        Bars from all symbols are merged in chronological order.
        When multiple symbols have bars at the same timestamp,
        they are processed in alphabetical order for determinism.

        Returns:
            MultiAssetResults with combined + per-symbol metrics.
        """
        # Reset all state
        for sym in self._portfolios:
            self._portfolios[sym].reset()
            self._indicators[sym].reset()
            self._processors[sym].reset()
            self._first_bars[sym] = None
            self._last_bars[sym] = None

        # Build iterators and seed the min-heap
        # Heap entries: (timestamp, symbol_name, bar, iterator)
        heap: list = []
        iterators: Dict[str, iter] = {}

        for sym in sorted(self.assets.keys()):
            self.assets[sym].reset()
            it = iter(self.assets[sym])
            iterators[sym] = it
            try:
                bar = next(it)
                heapq.heappush(heap, (bar.timestamp, sym, bar))
            except StopIteration:
                pass

        # Process bars in chronological order
        while heap:
            ts, sym, bar = heapq.heappop(heap)

            # Track first/last
            if self._first_bars[sym] is None:
                self._first_bars[sym] = bar
            self._last_bars[sym] = bar

            # Enforce exposure cap before processing
            self._enforce_exposure_cap(sym)

            # Process through the symbol's BarProcessor
            self._processors[sym].process_bar(bar)

            # Restore max_positions after processing
            self._restore_max_positions(sym)

            # Advance this symbol's iterator
            try:
                next_bar = next(iterators[sym])
                heapq.heappush(heap, (next_bar.timestamp, sym, next_bar))
            except StopIteration:
                pass

        return MultiAssetResults.from_portfolios(
            portfolios=self._portfolios,
            first_bars=self._first_bars,
            last_bars=self._last_bars,
            config=self.config,
        )

    def _enforce_exposure_cap(self, current_sym: str) -> None:
        """Temporarily limit position opens if exposure cap would be breached."""
        if self._max_total_exposure is None:
            return

        # Calculate current total exposure (sum of all open position sizes)
        total_exposure = 0.0
        for sym, portfolio in self._portfolios.items():
            for pos in portfolio.positions:
                total_exposure += pos.size_usd

        # If we're already at/above cap, prevent this symbol from opening new
        if total_exposure >= self._max_total_exposure:
            portfolio = self._portfolios[current_sym]
            # Save original max_positions for restore
            if not hasattr(portfolio, "_saved_max_positions"):
                portfolio._saved_max_positions = portfolio.max_positions
            portfolio.max_positions = portfolio.position_count

    def _restore_max_positions(self, sym: str) -> None:
        """Restore max_positions after exposure cap enforcement."""
        portfolio = self._portfolios[sym]
        if hasattr(portfolio, "_saved_max_positions"):
            portfolio.max_positions = portfolio._saved_max_positions
            del portfolio._saved_max_positions
