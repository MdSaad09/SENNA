"""Figure helpers for the F03 Chapter 6 validation plots.

Figures land in docs/synth/<module>/ as PNGs so the 5.4.1 deliverable survives
without committing rendered notebook outputs — the same convention as fits/.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from senna import config

FIGURE_ROOT = config.REPO_ROOT / "docs" / "synth"


def save_figure(fig: plt.Figure, module: str, name: str) -> Path:
    path = FIGURE_ROOT / module / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def lap_time_ecdf(sim_s: np.ndarray, real_s: np.ndarray, *, ks: float, title: str) -> plt.Figure:
    """Simulated vs real green-lap ECDFs; the KS gap is the headline (5.4.1)."""
    fig, ax = plt.subplots(figsize=(6, 4))
    for values, label in ((np.sort(sim_s), "simulated"), (np.sort(real_s), "real 2026")):
        ax.step(values, np.arange(1, len(values) + 1) / len(values), where="post", label=label)
    ax.set_xlabel("green lap time (s)")
    ax.set_ylabel("cumulative fraction")
    ax.set_title(f"{title} — KS {ks:.3f}")
    ax.legend()
    return fig


def corner_exponent_fit(
    downforce_ratio: float, exponent: float, v_2024: np.ndarray, v_2026: np.ndarray
) -> plt.Figure:
    """Matched apexes and the fitted downforce exponent (T2)."""
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(v_2024, v_2026, s=8, alpha=0.4, label="matched apexes")
    grid = np.linspace(float(v_2024.min()), float(v_2024.max()), 50)
    ax.plot(grid, grid * downforce_ratio**exponent, color="crimson",
            label=f"v26 = v24 * {downforce_ratio}^{exponent:.3f}")
    ax.set_xlabel("2024 apex (km/h)")
    ax.set_ylabel("2026 apex (km/h)")
    ax.legend()
    return fig
