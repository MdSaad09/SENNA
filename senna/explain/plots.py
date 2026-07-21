"""Figures for the surrogate notebook. Same split as the calibration modules: the
logic lives here, the narrative lives in notebooks/fit_surrogate.ipynb, and the PNGs
land in docs/explain/ so the deliverable survives without committing rendered
notebook outputs.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from senna import config

FIGURE_ROOT = config.REPO_ROOT / "docs" / "explain"


def save_figure(fig: plt.Figure, name: str) -> Path:
    path = FIGURE_ROOT / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return path


def fidelity_bars(heads: dict, threshold: float) -> plt.Figure:
    """The badge itself: per-head top-1 agreement against the bar it had to clear."""
    fig, ax = plt.subplots(figsize=(5, 3.5))
    names = list(heads)
    ax.bar(names, [heads[h]["top1"] for h in names], width=0.5, color="#4c72b0")
    ax.axhline(threshold, color="crimson", linestyle="--", linewidth=1.2,
               label=f"gate {threshold:.2f}")
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("top-1 agreement on held-out states")
    ax.set_title("Surrogate fidelity per action head")
    ax.legend()
    return fig


def kl_bars(heads: dict) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(5, 3.5))
    names = list(heads)
    ax.bar(names, [heads[h]["mean_kl"] for h in names], width=0.5, color="#55a868")
    ax.set_ylabel("mean KL(policy || surrogate), nats")
    ax.set_title("Where the surrogate disagrees in distribution")
    return fig


def rank_correlation_hist(rhos: np.ndarray) -> plt.Figure:
    """The A-04 integrity statistic across the sampled decisions. A tight positive
    mass means the tree surrogate and the true network rank the same drivers."""
    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    ax.hist(rhos, bins=30, color="#c44e52", alpha=0.85)
    ax.axvline(float(np.mean(rhos)), color="black", linewidth=1.2,
               label=f"mean {np.mean(rhos):.3f}")
    ax.set_xlabel("Spearman rho, |TreeSHAP| vs |GradientExplainer|")
    ax.set_ylabel("decisions")
    ax.set_title("Cross-check on the true network")
    ax.legend()
    return fig


def background_composition(composition: dict, top_n: int = 20) -> plt.Figure:
    """What the 1,024 background states actually are — attributions are marginal
    contributions against this set, so its shape is part of the explanation."""
    strata = composition["strata"]
    by_phase_status: dict[str, int] = {}
    for key, count in strata.items():
        _, phase, status = key.split("|")
        label = f"{phase} / {status}"
        by_phase_status[label] = by_phase_status.get(label, 0) + count

    ordered = sorted(by_phase_status.items(), key=lambda kv: -kv[1])[:top_n]
    fig, ax = plt.subplots(figsize=(6, 0.35 * len(ordered) + 1.5))
    ax.barh([k for k, _ in ordered][::-1], [v for _, v in ordered][::-1], color="#8172b2")
    ax.set_xlabel("states")
    ax.set_title(f"Background composition ({composition['size']} states, "
                 f"{len(strata)} non-empty strata)")
    return fig
