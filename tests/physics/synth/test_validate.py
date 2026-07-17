import numpy as np
import pytest
from scipy import stats

from senna.physics.synth.validate import (
    ks_distance,
    pit_delta_within,
    rate_within_band,
    stint_emd_laps,
)

SEED = 271
KS_TARGET = 0.15  # 5.4.1: sim-vs-real lap distributions must sit under this
SCIPY_MATCH_RTOL = 1e-9  # same statistic, independent implementation — agreement is exact


def test_ks_and_emd_match_scipy_reference():
    rng = np.random.default_rng(SEED)
    sim_s = rng.normal(90.0, 1.2, size=400)
    real_s = rng.normal(90.3, 1.0, size=300)

    assert ks_distance(sim_s, real_s) == pytest.approx(
        stats.ks_2samp(sim_s, real_s).statistic, rel=SCIPY_MATCH_RTOL
    )

    sim_lengths = rng.integers(12, 26, size=80).astype(float)
    real_lengths = rng.integers(14, 28, size=60).astype(float)

    assert stint_emd_laps(sim_lengths, real_lengths) == pytest.approx(
        stats.wasserstein_distance(sim_lengths, real_lengths), rel=SCIPY_MATCH_RTOL
    )


def test_ks_detects_half_second_shift():
    rng = np.random.default_rng(SEED)
    laps_s = rng.normal(90.0, 0.8, size=500)

    # a half-second bias — the size of miss 5.4.1 exists to catch — lands the
    # statistic well above the target; identical samples land exactly on zero
    assert ks_distance(laps_s, laps_s + 0.5) > KS_TARGET
    assert ks_distance(laps_s, laps_s) == 0.0


def test_band_and_pit_tolerance_checks():
    assert pit_delta_within(21.3, 21.9, tolerance_s=1.0) is True
    assert pit_delta_within(23.5, 21.9, tolerance_s=1.0) is False
    # 5.4.1 says "within 1.0 s": the boundary itself passes
    assert pit_delta_within(22.9, 21.9, tolerance_s=1.0) is True

    assert rate_within_band(0.30, 0.10, 0.50) is True
    assert rate_within_band(0.05, 0.10, 0.50) is False
    assert rate_within_band(0.60, 0.10, 0.50) is False
    # band edges are inclusive, matching the fitted hazard bands they came from
    assert rate_within_band(0.50, 0.10, 0.50) is True
