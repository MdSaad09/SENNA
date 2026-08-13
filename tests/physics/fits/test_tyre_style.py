"""Per-driver tyre style: a multiplier on the pooled degradation amplitude (F17, T5).

The estimator is the least-squares slope of a driver's partial residual on the
degradation the pooled curve predicts for that lap, so it pools correctly across circuits
and compounds whose `a` and `b` differ. Three things about it are easy to get quietly
wrong, and each has a test here whose only job is to catch that:

- the multipliers are normalised to a lap-weighted mean of 1.0, or naming a lineup would
  shift tyre life for the whole field;
- the standard error is clustered by stint, because a set that runs hot is slow for its
  whole life and a lap-level error bar understates that by three to four times;
- a driver the design cannot pin down is published as 1.0 and unidentified, never as a
  noisy fitted value wearing a `fitted` tag (E-10, one layer down).

Frames are hand-built here rather than run through the joint fit: what is under test is
the estimator, and a synthetic residual cloud with a known style injected into it says
more about the estimator than a chain of three fits does.
"""

import numpy as np
import pandas as pd
import pytest

from senna.env.dynamics import tyre_deg_s
from senna.physics.fits.degradation import DegradationFit
from senna.physics.fits.tyre_style import deg_prediction_s, fit_deg_multipliers

SEED = 99  # tests/physics/fits/conftest.py's module seed, so this sits in the same stream
T0_S = 92.0

# the shape of Bahrain's committed 2024 curves (configs/physics_params.yaml), rounded:
# amplitude near a thousandth of t0, exponent near linear
CURVES = {
    "MEDIUM": DegradationFit(a=0.00145, b=0.96, n_laps=1596, max_age_seen=30,
                             low_confidence=False),
    "HARD": DegradationFit(a=0.0011, b=1.03, n_laps=1596, max_age_seen=30,
                           low_confidence=False),
}

LAP_NOISE_S = 0.25   # lap-to-lap scatter left in a partial residual after the joint fit
STINT_NOISE_S = 0.15  # a set that runs hot is slow for its whole life — the within-stint
                      # correlation the clustered standard error exists to price

# injected styles chosen to have a lap-weighted mean of exactly 1.0 over equal samples,
# so normalisation is a no-op on this frame and the published values are comparable to
# the injected ones directly. Without that, only ratios between drivers are recoverable.
STYLES = {"D00": 1.25, "D01": 0.80, "D02": 1.00, "D03": 0.95}

SESSIONS = ("2024-01-R", "2024-02-R")
STINTS_PER_SESSION = 6
STINT_LAPS = 18

# a driver with the era-2024 median sample lands near 0.05, so 0.10 refuses the thin
# cells without gutting coverage — configs/fits.yaml driver_identity.max_rel_se_for_deg_mult
MAX_REL_SE = 0.10
MIN_STINTS = 6


def _style_frame(styles, *, stints_per_session=None, stint_laps=None, stint_noise_s=STINT_NOISE_S,
                 lap_noise_s=LAP_NOISE_S) -> pd.DataFrame:
    """Partial residuals for a field of drivers, each wearing its tyres at a known
    multiple of the pooled curve. Stint numbers restart in every session, which is the
    trap: clustering or counting on `stint` alone silently merges a driver's Bahrain
    second stint with their Monaco second stint."""
    rng = np.random.default_rng(SEED)
    stints_per_session = stints_per_session or dict.fromkeys(styles, STINTS_PER_SESSION)
    stint_laps = stint_laps or dict.fromkeys(styles, STINT_LAPS)

    rows = []
    for driver in styles:
        for session in SESSIONS:
            for stint in range(1, stints_per_session[driver] + 1):
                offset_s = rng.normal(0.0, stint_noise_s)
                for age in range(1, stint_laps[driver] + 1):
                    rows.append({
                        "driver": driver,
                        "session_id": session,
                        "stint": stint,
                        "compound": "MEDIUM" if stint % 2 else "HARD",
                        "tyre_life": float(age),
                        "stint_offset_s": offset_s,
                    })

    frame = pd.DataFrame(rows)
    frame["predicted_deg_s"] = deg_prediction_s(frame, CURVES, T0_S)
    frame["pace_residual_s"] = (
        frame["driver"].map(styles) * frame["predicted_deg_s"]
        + frame["stint_offset_s"]
        + rng.normal(0.0, lap_noise_s, len(frame))
    )
    return frame


def _lap_weighted_mean(fits) -> float:
    laps = sum(fit.n_laps for fit in fits.values())
    return sum(fit.n_laps * fit.mult for fit in fits.values()) / laps


def test_the_predicted_degradation_is_the_simulators_own_curve():
    frame = _style_frame(STYLES)

    # the fitter must predict what dynamics.tyre_deg_s computes, or the multiplier is a
    # slope against a curve the simulator does not run (T5)
    row = frame.iloc[0]
    curve = CURVES[row["compound"]]
    assert row["predicted_deg_s"] == pytest.approx(
        tyre_deg_s(T0_S, curve.a, curve.b, row["tyre_life"])
    )


def test_deg_multipliers_are_normalised():
    styles = {**STYLES, "D04": 1.30}
    # D04 runs one stint per session, below the count gate, so the published vector mixes
    # fitted multipliers with the 1.0 an unidentified driver takes — which is exactly when
    # a normalisation over the wrong set stops summing to one
    stints = {**dict.fromkeys(styles, STINTS_PER_SESSION), "D04": 1}
    frame = _style_frame(styles, stints_per_session=stints)

    fits = fit_deg_multipliers(frame, min_stints=MIN_STINTS, max_rel_se=MAX_REL_SE)

    assert fits["D04"].identified is False
    # a named grid cannot change the field's overall tyre life: the pooled `a` was fitted
    # on all drivers, so an unnormalised vector would shift every stint length at once
    assert _lap_weighted_mean(fits) == pytest.approx(1.0)


def test_deg_multiplier_recovers_an_injected_style():
    frame = _style_frame(STYLES)

    fits = fit_deg_multipliers(frame, min_stints=MIN_STINTS, max_rel_se=MAX_REL_SE)

    assert all(fit.identified for fit in fits.values())
    # the ratio survives normalisation whatever the pooled level is, so it is the honest
    # statement of "this driver wears a set 1.25 times as fast as that one"
    assert fits["D00"].mult / fits["D01"].mult == pytest.approx(1.25 / 0.80, rel=0.05)
    # and because the injected styles already average to 1.0, the levels are comparable too
    for driver, injected in STYLES.items():
        assert fits[driver].mult == pytest.approx(injected, abs=0.05)


def test_deg_multiplier_falls_back_when_unidentified():
    # one driver on two-lap stints: plenty of stints, almost no tyre life, so the design
    # never sees the curve it is being asked to scale
    styles = {**STYLES, "D04": 1.30}
    imprecise = _style_frame(styles, stint_laps={**dict.fromkeys(styles, STINT_LAPS), "D04": 2})
    # and one driver with a single stint per session: the sample is precise but too thin
    # to separate a style from the two sets it was measured on
    thin = _style_frame(styles, stints_per_session={
        **dict.fromkeys(styles, STINTS_PER_SESSION), "D04": 1
    })

    # gates relaxed one at a time so each refusal has exactly one cause
    on_precision = fit_deg_multipliers(imprecise, min_stints=1, max_rel_se=MAX_REL_SE)
    on_count = fit_deg_multipliers(thin, min_stints=MIN_STINTS, max_rel_se=1.0)

    for fits in (on_precision, on_count):
        # 1.0 and unidentified, never a noisy coefficient wearing a `fitted` tag (E-10)
        assert fits["D04"].identified is False
        assert fits["D04"].mult == 1.0
        assert fits["D00"].identified is True  # the gate bites one driver, not the field
    assert on_precision["D04"].rel_se > MAX_REL_SE
    assert on_count["D04"].n_stints < MIN_STINTS


def test_the_deg_multiplier_se_is_clustered_by_stint():
    """Degradation residuals are correlated within a stint, so a lap-level standard error
    counts eighteen laps of one hot set as eighteen independent observations. It understates
    by three to four times on data with any per-stint component, which is enough to walk a
    driver through a precision gate that should have refused them."""
    frame = _style_frame({"D00": 1.00}, stint_noise_s=0.5, lap_noise_s=0.05)

    fits = fit_deg_multipliers(frame, min_stints=1, max_rel_se=1.0)

    predicted_s = frame["predicted_deg_s"].to_numpy(dtype=float)
    residual_s = frame["pace_residual_s"].to_numpy(dtype=float)
    bread = float(predicted_s @ predicted_s)
    error_s = residual_s - (residual_s @ predicted_s / bread) * predicted_s
    # the lap-level error bar this must not be: sigma_hat / sqrt(sum d_hat^2), which treats
    # every lap of a set as fresh evidence
    naive_se = float(np.sqrt(error_s @ error_s / (len(error_s) - 1)) / np.sqrt(bread))
    assert fits["D00"].se > 2.0 * naive_se


def test_a_driver_with_no_degradation_signal_is_not_identified():
    # a quarter of the committed degradation curves sit at exactly a = 0 (the fitter hits
    # its lower bound on flat-residual circuits), so a driver whose whole sample came from
    # those has no denominator at all — that must read as "unidentified", not as a NaN
    flat = {"MEDIUM": DegradationFit(a=0.0, b=1.0, n_laps=400, max_age_seen=30,
                                     low_confidence=True)}
    frame = _style_frame(STYLES)
    frame = frame.assign(compound="MEDIUM")
    frame["predicted_deg_s"] = deg_prediction_s(frame, flat, T0_S)

    fits = fit_deg_multipliers(frame, min_stints=MIN_STINTS, max_rel_se=MAX_REL_SE)

    for fit in fits.values():
        assert fit.identified is False
        assert fit.mult == 1.0
        assert np.isfinite(fit.mult)
