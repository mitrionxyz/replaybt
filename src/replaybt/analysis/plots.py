"""Visualization functions for backtest results.

All functions return a ``matplotlib.figure.Figure`` — call ``fig.savefig()``
to save, or ``plt.show()`` to display interactively.

matplotlib is an optional dependency. Install with::

    pip install replaybt[plots]

Import directly::

    from replaybt.analysis.plots import plot_equity
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    import matplotlib.figure

    from ..optimize.results import SweepResults
    from ..reporting.metrics import BacktestResults
    from ..reporting.multi import MultiAssetResults


def _import_matplotlib():
    """Lazy import with helpful error message."""
    try:
        import matplotlib
        import matplotlib.pyplot as plt

        return matplotlib, plt
    except ImportError:
        raise ImportError(
            "matplotlib is required for plotting. Install with:\n"
            "  pip install replaybt[plots]"
        ) from None


def plot_equity(
    results: "BacktestResults",
    show_drawdown: bool = True,
    figsize: Tuple[int, int] = (12, 6),
) -> "matplotlib.figure.Figure":
    """Plot equity curve with optional drawdown shading.

    Args:
        results: BacktestResults with equity_curve data.
        show_drawdown: If True, shade drawdown regions in red.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    _, plt = _import_matplotlib()
    import numpy as np

    fig, ax = plt.subplots(figsize=figsize)

    if not results.equity_curve:
        ax.text(
            0.5, 0.5, "No equity data", ha="center", va="center",
            transform=ax.transAxes, fontsize=14,
        )
        ax.set_title(f"Equity Curve — {results.symbol or 'N/A'}")
        plt.close(fig)
        return fig

    timestamps, equities = zip(*results.equity_curve)
    eq_array = np.array(equities)

    ax.plot(timestamps, eq_array, color="steelblue", linewidth=1.2, label="Equity")

    if show_drawdown:
        peak = np.maximum.accumulate(eq_array)
        dd_pct = (peak - eq_array) / np.where(peak > 0, peak, 1.0) * 100

        ax2 = ax.twinx()
        ax2.fill_between(
            timestamps, 0, -dd_pct, color="red", alpha=0.15, label="Drawdown",
        )
        ax2.set_ylabel("Drawdown %")
        ax2.set_ylim(bottom=-max(dd_pct.max() * 1.5, 1), top=0)
        ax2.legend(loc="lower right")

    ax.set_title(f"Equity Curve — {results.symbol or 'N/A'}")
    ax.set_xlabel("Time")
    ax.set_ylabel("Equity ($)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def plot_drawdown(
    results: "BacktestResults",
    figsize: Tuple[int, int] = (12, 4),
) -> "matplotlib.figure.Figure":
    """Plot drawdown as negative percentage filled area.

    Args:
        results: BacktestResults with equity_curve data.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    _, plt = _import_matplotlib()
    import numpy as np

    fig, ax = plt.subplots(figsize=figsize)

    if not results.equity_curve:
        ax.text(
            0.5, 0.5, "No equity data", ha="center", va="center",
            transform=ax.transAxes, fontsize=14,
        )
        plt.close(fig)
        return fig

    timestamps, equities = zip(*results.equity_curve)
    eq_array = np.array(equities)
    peak = np.maximum.accumulate(eq_array)
    dd_pct = -(peak - eq_array) / np.where(peak > 0, peak, 1.0) * 100

    ax.fill_between(timestamps, 0, dd_pct, color="red", alpha=0.4)
    ax.plot(timestamps, dd_pct, color="darkred", linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.5)

    ax.set_title(f"Drawdown — {results.symbol or 'N/A'}")
    ax.set_xlabel("Time")
    ax.set_ylabel("Drawdown %")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def plot_trades(
    results: "BacktestResults",
    prices: Optional[List[float]] = None,
    figsize: Tuple[int, int] = (14, 6),
) -> "matplotlib.figure.Figure":
    """Plot entry/exit markers, optionally on a price chart.

    Args:
        results: BacktestResults with trades.
        prices: Optional list of (timestamp, price) tuples for the price line.
            If None, only entry/exit markers are plotted.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    _, plt = _import_matplotlib()

    fig, ax = plt.subplots(figsize=figsize)

    if prices:
        ts, px = zip(*prices)
        ax.plot(ts, px, color="gray", linewidth=0.5, alpha=0.7, label="Price")

    for trade in results.trades:
        color = "green" if trade.pnl_usd > 0 else "red"
        marker_entry = "^" if trade.side.value == "LONG" else "v"
        ax.scatter(
            trade.entry_time, trade.entry_price,
            marker=marker_entry, color=color, s=30, zorder=5,
        )
        ax.scatter(
            trade.exit_time, trade.exit_price,
            marker="x", color=color, s=30, zorder=5,
        )

    ax.set_title(f"Trades — {results.symbol or 'N/A'} ({results.total_trades} trades)")
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def plot_monthly_heatmap(
    results: "BacktestResults",
    figsize: Tuple[int, int] = (10, 5),
) -> "matplotlib.figure.Figure":
    """Plot monthly PnL as a Year x Month heatmap.

    Args:
        results: BacktestResults with monthly data.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    _, plt = _import_matplotlib()
    import numpy as np

    fig, ax = plt.subplots(figsize=figsize)

    if not results.monthly:
        ax.text(
            0.5, 0.5, "No monthly data", ha="center", va="center",
            transform=ax.transAxes, fontsize=14,
        )
        plt.close(fig)
        return fig

    # Build year x month grid
    monthly_data: dict = defaultdict(dict)
    for m in results.monthly:
        monthly_data[m.year][m.month] = m.net_pnl

    years = sorted(monthly_data.keys())
    months = list(range(1, 13))

    grid = np.full((len(years), 12), np.nan)
    for yi, year in enumerate(years):
        for mi, month in enumerate(months):
            if month in monthly_data[year]:
                grid[yi, mi] = monthly_data[year][month]

    # Plot
    vmax = max(abs(np.nanmin(grid)) if not np.all(np.isnan(grid)) else 1,
               abs(np.nanmax(grid)) if not np.all(np.isnan(grid)) else 1)
    im = ax.imshow(
        grid, cmap="RdYlGn", aspect="auto",
        vmin=-vmax, vmax=vmax,
    )

    # Labels
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels(years)

    # Annotate cells
    for yi in range(len(years)):
        for mi in range(12):
            val = grid[yi, mi]
            if not np.isnan(val):
                color = "white" if abs(val) > vmax * 0.6 else "black"
                ax.text(
                    mi, yi, f"${val:,.0f}",
                    ha="center", va="center", fontsize=8, color=color,
                )

    ax.set_title(f"Monthly PnL — {results.symbol or 'N/A'}")
    fig.colorbar(im, ax=ax, label="PnL ($)")
    fig.tight_layout()
    plt.close(fig)
    return fig


def plot_exit_breakdown(
    results: "BacktestResults",
    kind: str = "bar",
    figsize: Tuple[int, int] = (8, 5),
) -> "matplotlib.figure.Figure":
    """Plot exit reason breakdown as bar or pie chart.

    Args:
        results: BacktestResults with exit_breakdown data.
        kind: ``"bar"`` or ``"pie"``.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    _, plt = _import_matplotlib()

    fig, ax = plt.subplots(figsize=figsize)

    if not results.exit_breakdown:
        ax.text(
            0.5, 0.5, "No exit data", ha="center", va="center",
            transform=ax.transAxes, fontsize=14,
        )
        plt.close(fig)
        return fig

    reasons = sorted(results.exit_breakdown.keys())
    counts = [results.exit_breakdown[r] for r in reasons]

    if kind == "pie":
        ax.pie(counts, labels=reasons, autopct="%1.1f%%", startangle=90)
    else:
        bars = ax.bar(reasons, counts, color="steelblue")
        ax.set_ylabel("Count")
        for bar, count in zip(bars, counts):
            ax.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                str(count), ha="center", va="bottom", fontsize=9,
            )

    ax.set_title(f"Exit Breakdown — {results.symbol or 'N/A'}")
    fig.tight_layout()
    plt.close(fig)
    return fig


def plot_multi_equity(
    results: "MultiAssetResults",
    show_combined: bool = True,
    figsize: Tuple[int, int] = (14, 7),
) -> "matplotlib.figure.Figure":
    """Plot per-symbol equity curves with optional combined overlay.

    Args:
        results: MultiAssetResults with per-symbol equity curves.
        show_combined: If True, plot the combined portfolio equity.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    _, plt = _import_matplotlib()

    fig, ax = plt.subplots(figsize=figsize)

    for sym in sorted(results.per_symbol.keys()):
        res = results.per_symbol[sym]
        if res.equity_curve:
            ts, eq = zip(*res.equity_curve)
            ax.plot(ts, eq, linewidth=0.8, alpha=0.7, label=sym)

    if show_combined and results.combined_equity_curve:
        ts, eq = zip(*results.combined_equity_curve)
        ax.plot(ts, eq, color="black", linewidth=1.5, label="Combined")

    ax.set_title("Multi-Asset Equity Curves")
    ax.set_xlabel("Time")
    ax.set_ylabel("Equity ($)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def plot_sweep_heatmap(
    results: "SweepResults",
    x_param: str,
    y_param: str,
    metric: str = "net_pnl",
    figsize: Tuple[int, int] = (10, 7),
) -> "matplotlib.figure.Figure":
    """Plot 2D parameter sweep as a heatmap.

    Args:
        results: SweepResults from a ParameterSweep.
        x_param: Parameter name for the x-axis.
        y_param: Parameter name for the y-axis.
        metric: Metric to display in cells.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    _, plt = _import_matplotlib()
    import numpy as np

    fig, ax = plt.subplots(figsize=figsize)

    if not results.combos:
        ax.text(
            0.5, 0.5, "No sweep data", ha="center", va="center",
            transform=ax.transAxes, fontsize=14,
        )
        plt.close(fig)
        return fig

    # Extract unique param values
    x_vals = sorted(set(c[x_param] for c in results.combos if x_param in c))
    y_vals = sorted(set(c[y_param] for c in results.combos if y_param in c))

    if not x_vals or not y_vals:
        ax.text(
            0.5, 0.5, f"Parameters '{x_param}'/'{y_param}' not found",
            ha="center", va="center", transform=ax.transAxes, fontsize=12,
        )
        plt.close(fig)
        return fig

    # Build lookup
    lookup = {}
    for c in results.combos:
        key = (c.get(x_param), c.get(y_param))
        lookup[key] = c.get(metric, 0)

    grid = np.full((len(y_vals), len(x_vals)), np.nan)
    for xi, xv in enumerate(x_vals):
        for yi, yv in enumerate(y_vals):
            if (xv, yv) in lookup:
                grid[yi, xi] = lookup[(xv, yv)]

    vmax = max(
        abs(np.nanmin(grid)) if not np.all(np.isnan(grid)) else 1,
        abs(np.nanmax(grid)) if not np.all(np.isnan(grid)) else 1,
    )
    im = ax.imshow(
        grid, cmap="RdYlGn", aspect="auto",
        vmin=-vmax, vmax=vmax,
    )

    ax.set_xticks(range(len(x_vals)))
    ax.set_xticklabels([str(v) for v in x_vals], rotation=45, ha="right")
    ax.set_yticks(range(len(y_vals)))
    ax.set_yticklabels([str(v) for v in y_vals])
    ax.set_xlabel(x_param)
    ax.set_ylabel(y_param)

    # Annotate cells
    for yi in range(len(y_vals)):
        for xi in range(len(x_vals)):
            val = grid[yi, xi]
            if not np.isnan(val):
                color = "white" if abs(val) > vmax * 0.6 else "black"
                fmt = f"${val:,.0f}" if metric.endswith("pnl") else f"{val:.1f}"
                ax.text(
                    xi, yi, fmt,
                    ha="center", va="center", fontsize=7, color=color,
                )

    ax.set_title(f"Sweep Heatmap: {metric} by {x_param} x {y_param}")
    fig.colorbar(im, ax=ax, label=metric)
    fig.tight_layout()
    plt.close(fig)
    return fig
