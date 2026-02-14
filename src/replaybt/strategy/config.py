"""Strategy configuration with per-symbol overrides."""

from __future__ import annotations

from typing import Any, Dict, Optional


class StrategyConfig:
    """Configuration container with per-symbol parameter overrides.

    Mirrors the TRENDMASTER_OVERRIDES pattern from the live bot:
    default values for all symbols, with specific overrides per symbol.

    Usage:
        config = StrategyConfig(
            defaults={'ema_fast': 15, 'ema_slow': 35, 'tp': 0.08},
            overrides={'ETH': {'ema_fast': 10, 'ema_slow': 30, 'tp': 0.12}},
        )
        config.get('tp', symbol='ETH')  # 0.12
        config.get('tp', symbol='SOL')  # 0.08
    """

    def __init__(
        self,
        defaults: Optional[Dict[str, Any]] = None,
        overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self._defaults = defaults or {}
        self._overrides = overrides or {}

    def get(self, key: str, symbol: Optional[str] = None, default: Any = None) -> Any:
        """Get a config value, checking symbol overrides first.

        Args:
            key: Parameter name.
            symbol: Optional symbol for override lookup.
            default: Fallback if key not found anywhere.
        """
        if symbol and symbol in self._overrides:
            if key in self._overrides[symbol]:
                return self._overrides[symbol][key]
        return self._defaults.get(key, default)

    def for_symbol(self, symbol: str) -> Dict[str, Any]:
        """Return merged config for a specific symbol.

        Returns defaults with symbol overrides applied on top.
        """
        merged = dict(self._defaults)
        if symbol in self._overrides:
            merged.update(self._overrides[symbol])
        return merged

    def symbols(self) -> list:
        """Return list of symbols that have overrides."""
        return list(self._overrides.keys())

    def __getitem__(self, key: str) -> Any:
        return self._defaults[key]

    def __contains__(self, key: str) -> bool:
        return key in self._defaults

    def __repr__(self) -> str:
        return f"StrategyConfig(defaults={self._defaults}, overrides={list(self._overrides.keys())})"
