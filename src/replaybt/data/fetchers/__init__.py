"""Exchange data fetchers with caching convenience functions."""

from .base import ExchangeFetcher


def BinanceProvider(
    symbol: str,
    timeframe: str = "1m",
    start=None,
    end=None,
    **kwargs,
):
    """Create a CachedProvider backed by Binance public API.

    Args:
        symbol: Binance trading pair (e.g. 'ETHUSDT').
        timeframe: Candle interval (default '1m').
        start: Start date (str or datetime).
        end: End date (str or datetime).
        **kwargs: Passed to CachedProvider (cache_dir, symbol_name, etc).

    Returns:
        CachedProvider instance ready for BacktestEngine.
    """
    from .binance import BinanceFetcher
    from ..cache import CachedProvider

    return CachedProvider(BinanceFetcher(), symbol, timeframe, start, end, **kwargs)


def BybitProvider(
    symbol: str,
    timeframe: str = "1m",
    start=None,
    end=None,
    **kwargs,
):
    """Create a CachedProvider backed by Bybit public API.

    Args:
        symbol: Bybit trading pair (e.g. 'ETHUSDT').
        timeframe: Candle interval (default '1m').
        start: Start date (str or datetime).
        end: End date (str or datetime).
        **kwargs: Passed to CachedProvider (cache_dir, symbol_name, etc).

    Returns:
        CachedProvider instance ready for BacktestEngine.
    """
    from .bybit import BybitFetcher
    from ..cache import CachedProvider

    return CachedProvider(BybitFetcher(), symbol, timeframe, start, end, **kwargs)


__all__ = [
    "ExchangeFetcher",
    "BinanceProvider",
    "BybitProvider",
]
