"""Grid market making module for replaybt.

Provides a complete grid MM backtest engine with virtual order management,
inventory tracking, and configurable grid shapes.
"""

from .engine import GridBacktestEngine
from .inventory import InventoryTracker, InventoryState
from .manager import GridManager, GridLevel
from .shapes import ShapeConfig, compute_grid
from .types import GridConfig, GridFill, GridOrder, GridResults, OrderSide, OrderStatus

__all__ = [
    "GridBacktestEngine",
    "GridConfig",
    "GridFill",
    "GridLevel",
    "GridManager",
    "GridOrder",
    "GridResults",
    "InventoryState",
    "InventoryTracker",
    "OrderSide",
    "OrderStatus",
    "ShapeConfig",
    "compute_grid",
]
