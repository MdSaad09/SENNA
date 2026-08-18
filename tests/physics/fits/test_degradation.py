import numpy as np
import pandas as pd
import pytest

from senna.physics.fits.degradation import (
    InaccurateLapError,
    InOutLapError,
    fit_degradation,
)

T0_S = 90.0
CURVE_BOUNDS = ([0.0, 0.3], [5.0, 3.0])  # fits.yaml deg_curve_bounds (stylised)
MINIMUMS = {
    "min_laps": 30,  # fits.yaml deg_min_laps
    "min_stints": 3,  # fits.yaml deg_min_stints
    "min_drivers": 2,  # fits.yaml deg_min_drivers
    "min_max_age": 12,  # fits.yaml deg_min_max_age
    "p0": [0.05, 1.2],  # fits.yaml degradation.curve_p0 (stylised solver seed)
    "maxfev": 10_000,  # fits.yaml degradation.curve_maxfev
    "signal_floor_s": 0.15,  # fits.yaml degradation.signal_floor_frac_of_s_ref x a 0.3 s sigma
}

DEG_A_S = 0.05  # A in the injected residual A*age^1.3; grip-law a = A/t0
DEG_EXPONENT = 1.3


def _stint_rows(driver, stint, ages, residuals_s):
    return [
        {
            "driver": driver,
            "stint": stint,
            "compound": "MEDIUM",
            "tyre_life": float(age),
            "pace_residual_s": residual_s,
            "is_accurate": True,
            "pit_in_time_s": None,
            "pit_out_time_s": None,
        }
        for age, residual_s in zip(ages, residuals_s, strict=True)
    ]


def _power_law_laps(rng, stints, max_age):
    ages = range(1, max_age + 1)
    rows = []
    for driver, stint in stints:
        residuals_s = [
            DEG_A_S * age**DEG_EXPONENT + rng.normal(0.0, 0.05) for age in ages
        ]
        rows += _stint_rows(driver, stint, ages, residuals_s)
    return pd.DataFrame(rows)


def test_recovers_power_law():
    rng = np.random.default_rng(7)
    stints = [("VER", 1), ("VER", 2), ("HAM", 1), ("HAM", 2), ("NOR", 1)]
    laps = _power_law_laps(rng, stints, max_age=18)

    fits = fit_degradation(laps, T0_S, bounds=CURVE_BOUNDS, **MINIMUMS)
    medium = fits["MEDIUM"]

    assert medium.a == pytest.approx(DEG_A_S / T0_S, rel=0.15)
    assert medium.b == pytest.approx(DEG_EXPONENT, abs=0.15)
    assert medium.low_confidence is False
    assert medium.n_laps == len(laps)
    assert medium.max_age_seen == 18


def test_refuses_in_out_laps():
    rng = np.random.default_rng(7)
    laps = _power_law_laps(rng, [("VER", 1), ("HAM", 1), ("NOR", 1)], max_age=15)
    laps.loc[3, "pit_in_time_s"] = 5400.0

    # E-09: an in-lap in a degradation dataset means the upstream filter
    # failed -- the fitter refuses rather than fitting through the poison
    with pytest.raises(InOutLapError):
        fit_degradation(laps, T0_S, bounds=CURVE_BOUNDS, **MINIMUMS)


def test_refuses_inaccurate_laps():
    rng = np.random.default_rng(7)
    laps = _power_law_laps(rng, [("VER", 1), ("HAM", 1), ("NOR", 1)], max_age=15)
    laps.loc[5, "is_accurate"] = False

    with pytest.raises(InaccurateLapError):
        fit_degradation(laps, T0_S, bounds=CURVE_BOUNDS, **MINIMUMS)


def test_low_confidence_below_minimums():
    rng = np.random.default_rng(7)
    # a truncated stint: one driver, one stint, eight laps, max age under 12
    laps = _power_law_laps(rng, [("VER", 1)], max_age=8)

    fits = fit_degradation(laps, T0_S, bounds=CURVE_BOUNDS, **MINIMUMS)
    medium = fits["MEDIUM"]

    # thin data still gets a fit -- T5 needs the coefficients for cluster
    # transfer -- but the flag must say the sample gates were not met
    assert medium.low_confidence is True
    assert np.isfinite(medium.a) and np.isfinite(medium.b)
    assert medium.n_laps == 8
    assert medium.max_age_seen == 8
