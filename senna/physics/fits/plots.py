"""Figure helpers the calibration notebooks share.

Figures land in docs/fits/<module>/ as PNGs so the residual-plot deliverable
survives without committing rendered notebook outputs.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from senna import config

FIGURE_ROOT = config.REPO_ROOT / "docs" / "fits"


def save_figure(fig: plt.Figure, module: str, name: str) -> Path:
    path = FIGURE_ROOT / module / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return path


def residual_panel(residuals_s: pd.Series, against: dict[str, pd.Series], title: str) -> plt.Figure:
    """Residuals scattered against each named regressor — flat clouds are the pass."""
    fig, axes = plt.subplots(1, len(against), figsize=(4.5 * len(against), 3.5), sharey=True)
    for ax, (name, values) in zip(np.atleast_1d(axes), against.items(), strict=True):
        ax.scatter(values, residuals_s, s=4, alpha=0.3)
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_xlabel(name)
    np.atleast_1d(axes)[0].set_ylabel("residual (s)")
    fig.suptitle(title)
    return fig


def degradation_curve(
    ages: pd.Series, residuals_s: pd.Series, a: float, b: float, t0_s: float, title: str
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(ages, residuals_s, s=6, alpha=0.35, label="partial residuals")
    grid = np.linspace(max(ages.min(), 1.0), ages.max(), 100)
    ax.plot(grid, a * t0_s * grid**b, color="crimson", label=f"fit: {a:.2e} * t0 * age^{b:.2f}")
    ax.set_xlabel("tyre age (laps)")
    ax.set_ylabel("pace delta (s)")
    ax.set_title(title)
    ax.legend()
    return fig


def hazard_band_chart(hazards: pd.DataFrame, kind: str) -> plt.Figure:
    """Per-circuit rate with its Wilson band; wide bands are the honest answer."""
    ordered = hazards.sort_values("p_per_race")
    fig, ax = plt.subplots(figsize=(7, 0.3 * len(ordered) + 1.5))
    y = np.arange(len(ordered))
    below = ordered["p_per_race"] - ordered["band_low"]
    above = ordered["band_high"] - ordered["p_per_race"]
    ax.errorbar(ordered["p_per_race"], y, xerr=[below, above], fmt="o", markersize=4, capsize=2)
    ax.set_yticks(y, ordered.index)
    ax.set_xlabel(f"P({kind.upper()} per race), Wilson 95%")
    ax.set_xlim(0, 1)
    return fig
