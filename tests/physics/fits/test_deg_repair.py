"""The F24 repair ladder, pinned before the implementation exists (E-10, T5).

A bound-clip is a statement that the data could not measure wear, not a
measurement of zero wear. These tests hold the fitter to that: a clipped
amplitude is stored unidentified, the pooled refit recovers wear the
per-circuit fit starved on, and every substituted curve carries its source.
"""

import numpy as np
import pandas as pd
import pytest

from senna.physics.fits import degradation
from senna.physics.fits.degradation import fit_degradation

T0_S = 90.0
CURVE_BOUNDS = ([0.0, 0.3], [5.0, 3.0])  # fits.yaml degradation.curve_bounds (stylised)
MINIMUMS = {
    "min_laps": 30,  # fits.yaml deg_min_laps
    "min_stints": 3,  # fits.yaml deg_min_stints
    "min_drivers": 2,  # fits.yaml deg_min_drivers
    "min_max_age": 12,  # fits.yaml deg_min_max_age
    "p0": [0.05, 1.2],  # fits.yaml degradation.curve_p0 (stylised solver seed)
    "maxfev": 10_000,  # fits.yaml degradation.curve_maxfev
}

# 0.5 x a 0.3 s clean-lap sigma — the fits.yaml signal-floor rule, applied by the
# caller in absolute seconds; the pooled fitter takes the same floor over t0.
SIGNAL_FLOOR_S = 0.15
SIGNAL_FLOOR_FRAC = SIGNAL_FLOOR_S / T0_S

STINTS = [("VER", 1), ("VER", 2), ("HAM", 1), ("HAM", 2), ("NOR", 1)]


def _stint_rows(driver, stint, ages, residuals_s):
    return [
        {
            "driver": driver,
            "stint": stint,
            "compound": "SOFT",
            "tyre_life": float(age),
            "pace_residual_s": float(residual_s),
            "is_accurate": True,
            "pit_in_time_s": None,
            "pit_out_time_s": None,
        }
        for age, residual_s in zip(ages, residuals_s, strict=True)
    ]


def test_bound_clipped_fit_is_stored_unidentified():
    # zero-mean noise over ages 1..25: the a >= 0 bound pins the optimum at the
    # boundary. E-10 says that clip may never be serialised as a measurement.
    rng = np.random.default_rng(7)
    ages = range(1, 26)
    rows = []
    for driver, stint in STINTS:
        rows += _stint_rows(driver, stint, ages, rng.normal(0.0, 0.05, 25))
    laps = pd.DataFrame(rows)

    fits = fit_degradation(
        laps, T0_S, bounds=CURVE_BOUNDS, signal_floor_s=SIGNAL_FLOOR_S, **MINIMUMS
    )

    assert fits["SOFT"].identified is False


def test_fit_above_signal_floor_is_identified():
    rng = np.random.default_rng(5)
    ages = range(1, 21)
    rows = []
    for driver, stint in STINTS:
        residuals_s = [0.03 * age**1.2 + rng.normal(0.0, 0.05) for age in ages]
        rows += _stint_rows(driver, stint, ages, residuals_s)
    laps = pd.DataFrame(rows)

    fits = fit_degradation(
        laps, T0_S, bounds=CURVE_BOUNDS, signal_floor_s=SIGNAL_FLOOR_S, **MINIMUMS
    )
    soft = fits["SOFT"]

    # ~1.1 s of delta at age 20 clears the 0.15 s floor with room to spare
    assert soft.identified is True
    assert soft.a > 0.0


def test_pooled_refit_recovers_planted_wear():
    planted_a = 0.001  # fractional: grip(age) = 1 - a * age^b
    planted_b = 1.2
    rng = np.random.default_rng(11)
    rows = []
    # three circuits with different base laps pool honestly only in fractional
    # units — residual_s / t0_s — which is what the pooled fitter takes
    for t0_s in (80.0, 90.0, 105.0):
        for _ in range(3):
            for age in range(1, 31):
                residual_s = planted_a * t0_s * age**planted_b + rng.normal(0.0, 0.05)
                rows.append(
                    {
                        "compound": "SOFT",
                        "tyre_life": float(age),
                        "frac_residual": residual_s / t0_s,
                    }
                )
    frac_residuals = pd.DataFrame(rows)

    pooled = degradation.fit_pooled_degradation(
        frac_residuals,
        bounds=CURVE_BOUNDS,
        p0=[0.05, 1.2],
        maxfev=10_000,
        signal_floor_frac=SIGNAL_FLOOR_FRAC,
    )
    soft = pooled["SOFT"]

    assert soft.a == pytest.approx(planted_a, rel=0.2)
    assert soft.b == pytest.approx(planted_b, abs=0.2)
    assert soft.identified is True


def _fit(a, b, *, identified):
    return degradation.DegradationFit(
        a=a, b=b, n_laps=180, max_age_seen=30, low_confidence=False, identified=identified
    )


def test_unidentified_circuit_fit_takes_the_pooled_curve():
    deg = {
        ("monaco_grand_prix", "2026"): {
            "SOFT": _fit(0.0, 0.3, identified=False),
            "MEDIUM": _fit(0.0007, 1.1, identified=True),
        }
    }
    pooled_by_era = {
        "2026": {"SOFT": _fit(0.0009, 1.2, identified=True)},
        "2024": {"SOFT": _fit(0.0011, 1.0, identified=True)},
    }

    repaired, sources = degradation.repair_degradation(deg, pooled_by_era)
    soft = repaired[("monaco_grand_prix", "2026")]["SOFT"]

    assert (soft.a, soft.b) == (0.0009, 1.2)
    assert sources == {("monaco_grand_prix", "2026", "SOFT"): "pooled"}
    # the identified neighbour is untouched, and no source is invented for it
    assert repaired[("monaco_grand_prix", "2026")]["MEDIUM"] == deg[
        ("monaco_grand_prix", "2026")
    ]["MEDIUM"]


def test_pooled_unidentified_falls_through_to_cross_era_prior():
    deg = {
        ("monaco_grand_prix", "2026"): {"SOFT": _fit(0.0, 0.3, identified=False)}
    }
    pooled_by_era = {
        "2026": {"SOFT": _fit(0.0, 0.3, identified=False)},
        "2024": {"SOFT": _fit(0.0011, 1.0, identified=True)},
    }

    repaired, sources = degradation.repair_degradation(deg, pooled_by_era)
    soft = repaired[("monaco_grand_prix", "2026")]["SOFT"]

    assert (soft.a, soft.b) == (0.0011, 1.0)
    assert sources == {("monaco_grand_prix", "2026", "SOFT"): "prior_cross_era"}


def test_nothing_identified_leaves_the_fit_unrepaired():
    original = _fit(0.0, 0.3, identified=False)
    deg = {("monaco_grand_prix", "2026"): {"SOFT": original}}
    pooled_by_era = {
        "2026": {"SOFT": _fit(0.0, 0.3, identified=False)},
        "2024": {"SOFT": _fit(0.0, 0.3, identified=False)},
    }

    repaired, sources = degradation.repair_degradation(deg, pooled_by_era)

    # no rung of the ladder held: the fit stays as-is and stays unidentified,
    # for the scenario backstop to refuse — never silently promoted to a curve
    assert repaired[("monaco_grand_prix", "2026")]["SOFT"] == original
    assert sources == {}
