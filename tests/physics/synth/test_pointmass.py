import math

import numpy as np
import pandas as pd
import pytest

from senna.physics.synth.pointmass import fit_effective_car, run_straight, taper_kw

# 2026 MGU-K facts (physics_2026.yaml): 350 kW held to 290 km/h, zero at 355 — never 400
TAPER_2026 = {"mgu_k_max_kw": 350.0, "full_power_to_kmh": 290.0, "zero_power_at_kmh": 355.0}
# taper thresholds lifted above any speed the closed-form run reaches, so P_K stays flat
TAPER_ABOVE_RUN = {"mgu_k_max_kw": 350.0, "full_power_to_kmh": 450.0, "zero_power_at_kmh": 500.0}

P_BASE_KW = 400.0  # the ICE side of the 2026 unit
CAR_PLUS_HALF_TANK_KG = 768.0 + 35.0  # minimum car mass plus half the 70 kg allowance (AR-10)
CLOSED_FORM_RTOL = 1e-3  # the integrator's step-error budget against the analytic solution

# injected effective-car truth for the recovery tests; beta ~ 0.5*rho*CdA in N s^2/m^2
P_TRUE_KW = 575.0
BETA_TRUE = 0.90
MU_TRUE = 1.6
KAPPA_TRUE = 0.002
MASS_KG = 850.0
DRIVE_RTOL = 0.02  # plan: P_eff within 2 percent
DRAG_RTOL = 0.05  # plan: beta_eff within 5 percent
BRAKE_RTOL = 0.10  # the brake tail is short (10 samples), so a looser bar
# losing the two clean samples at the gap edges moves an exact-data least squares by far
# less than this; differencing across the 5 s hole moves it by whole percents
GAP_MATCH_RTOL = 1e-3

FIT_KWARGS = {
    "mass_kg": MASS_KG,
    "throttle_full_pct": 99.0,  # synth.yaml threshold arrives as an argument, never inline
    "accel_smooth_window_s": 0.5,
    "profile_tolerance_frac": 0.05,
}

TELEMETRY_KWARGS = {
    "p_kw": P_TRUE_KW,
    "beta": BETA_TRUE,
    "mass_kg": MASS_KG,
    "v0_kmh": 100.0,
    "n_samples": 120,
    "brake_samples": 10,
    "mu_brake": MU_TRUE,
    "kappa_brake": KAPPA_TRUE,
}


def test_flat_out_closed_form():
    # Spec-mandated (5.4 T1). With beta = 0 and both power terms flat, total drive
    # power P is constant, so m*v*dv/dt = P gives d(v^2)/dt = 2P/m:
    #   v(t) = sqrt(v0^2 + 2*P*t/m)          (P in W, v in m/s)
    #   x(t) = integral of v dt = (m/(3P)) * (v(t)^3 - v0^3)
    # Pick t_true, derive the distance, and the integrator must give t_true back.
    p_total_w = 1000.0 * (P_BASE_KW + TAPER_ABOVE_RUN["mgu_k_max_kw"])
    mass_kg = CAR_PLUS_HALF_TANK_KG
    t_true_s = 3.0
    v0_ms = 200.0 / 3.6
    v_end_ms = math.sqrt(v0_ms**2 + 2.0 * p_total_w * t_true_s / mass_kg)
    dist_m = mass_kg / (3.0 * p_total_w) * (v_end_ms**3 - v0_ms**3)

    run = run_straight(
        200.0,
        dist_m,
        mass_kg=mass_kg,
        p_base_kw=P_BASE_KW,
        beta_drag=0.0,
        taper=TAPER_ABOVE_RUN,
    )

    assert run.time_s == pytest.approx(t_true_s, rel=CLOSED_FORM_RTOL)
    assert run.v_end_kmh == pytest.approx(v_end_ms * 3.6, rel=CLOSED_FORM_RTOL)
    # E_dep counts only the MGU-K term (F-02): 350 kW held for t_true = 0.350*t_true MJ
    assert run.e_dep_mj == pytest.approx(0.350 * t_true_s, rel=CLOSED_FORM_RTOL)


def test_taper_shape():
    below = taper_kw(np.array([0.0, 120.0, 250.0, 290.0]), **TAPER_2026)
    np.testing.assert_array_equal(below, 350.0)  # full electric power to 290 km/h exactly

    above = taper_kw(np.array([355.0, 380.0, 500.0]), **TAPER_2026)
    np.testing.assert_array_equal(above, 0.0)  # nothing left at or beyond 355 km/h

    ramp = taper_kw(np.linspace(290.0, 355.0, 27), **TAPER_2026)
    assert np.all(np.diff(ramp) < 0.0)  # strictly decreasing across the taper band

    midpoint = taper_kw(np.array([(290.0 + 355.0) / 2.0]), **TAPER_2026)
    assert midpoint[0] == pytest.approx(175.0)  # linear taper: half power at half band


def test_recovers_effective_params(make_straight_telemetry):
    telemetry = make_straight_telemetry(**TELEMETRY_KWARGS)

    car = fit_effective_car(telemetry, **FIT_KWARGS)

    assert car.p_drive_kw == pytest.approx(P_TRUE_KW, rel=DRIVE_RTOL)
    assert car.beta_drag == pytest.approx(BETA_TRUE, rel=DRAG_RTOL)
    assert car.mu_brake == pytest.approx(MU_TRUE, rel=BRAKE_RTOL)
    assert car.kappa_brake == pytest.approx(KAPPA_TRUE, rel=BRAKE_RTOL)
    # the self-check gate: the fitted car reproduces its own observed phase times
    assert car.check_err_frac <= FIT_KWARGS["profile_tolerance_frac"]
    assert car.ok is True


def test_never_crosses_trace_gap(make_straight_telemetry):
    unbroken = make_straight_telemetry(**TELEMETRY_KWARGS)
    gapped = make_straight_telemetry(**TELEMETRY_KWARGS, trace_gap_at=60)

    baseline = fit_effective_car(unbroken, **FIT_KWARGS)
    split = fit_effective_car(gapped, **FIT_KWARGS)

    # a finite difference spanning the 5 s hole would read ~1/24th of the true
    # acceleration at full throttle — one poisoned sample that a boundary-respecting
    # fitter never produces (AR-16, the fits/energy.py convention)
    assert split.p_drive_kw == pytest.approx(baseline.p_drive_kw, rel=GAP_MATCH_RTOL)
    assert split.beta_drag == pytest.approx(baseline.beta_drag, rel=GAP_MATCH_RTOL)
    assert split.p_drive_kw == pytest.approx(P_TRUE_KW, rel=DRIVE_RTOL)
    assert split.beta_drag == pytest.approx(BETA_TRUE, rel=DRAG_RTOL)
    assert split.ok is True


def test_self_check_gate_flags_bad_fit(make_straight_telemetry):
    strong = make_straight_telemetry(**TELEMETRY_KWARGS)
    # a second run at roughly a quarter of the power: no single (P, beta) can
    # reproduce both observed full-throttle phase durations
    weak_kwargs = {**TELEMETRY_KWARGS, "p_kw": 150.0}
    weak = make_straight_telemetry(**weak_kwargs)
    offset = strong["Time"].iloc[-1] + pd.Timedelta(seconds=5)
    two_runs = pd.concat(
        [strong, weak.assign(Time=weak["Time"] + offset, trace_id=1)],
        ignore_index=True,
    )

    car = fit_effective_car(two_runs, **FIT_KWARGS)

    assert car.ok is False
    assert car.check_err_frac > FIT_KWARGS["profile_tolerance_frac"]
