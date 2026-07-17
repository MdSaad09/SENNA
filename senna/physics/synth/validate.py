"""5.4.1 validation metrics — the numbers Chapter 6 reports per held-out circuit.

This module and heldout.py are the only ones allowed to read rounds 7+; every
other synth module refuses them (E-14). The metrics themselves are distribution
distances between the generator's Monte Carlo output and the real held-out
races: lap-time KS, stint-length EMD, pit delta, and event-rate band checks.
"""

import numpy as np
from scipy import stats


def ks_distance(sim_s: np.ndarray, real_s: np.ndarray) -> float:
    """Two-sample Kolmogorov-Smirnov statistic — max CDF gap (5.4.1, target < 0.15)."""
    sim_sorted = np.sort(np.asarray(sim_s, dtype=float))
    real_sorted = np.sort(np.asarray(real_s, dtype=float))
    grid = np.concatenate([sim_sorted, real_sorted])
    cdf_sim = np.searchsorted(sim_sorted, grid, side="right") / sim_sorted.size
    cdf_real = np.searchsorted(real_sorted, grid, side="right") / real_sorted.size
    return float(np.max(np.abs(cdf_sim - cdf_real)))


def stint_emd_laps(sim_lengths: np.ndarray, real_lengths: np.ndarray) -> float:
    """Earth-mover distance between stint-length histograms, in laps (5.4.1)."""
    return float(stats.wasserstein_distance(sim_lengths, real_lengths))


def pit_delta_within(sim_mean_s: float, real_mean_s: float, *, tolerance_s: float) -> bool:
    """Simulated pit delta within tolerance of the OpenF1 mean; boundary passes (5.4.1)."""
    return abs(sim_mean_s - real_mean_s) <= tolerance_s


def rate_within_band(rate: float, band_low: float, band_high: float) -> bool:
    """Event rate inside the fitted Wilson band; edges inclusive (E-03)."""
    return band_low <= rate <= band_high
