"""T1 — powertrain reprofile through an effective point-mass car.

Nothing physical is sourced here: p_drive_kw and beta_drag absorb engine power,
drivetrain efficiency, air density, CdA and rolling resistance in one pair of
effective constants fitted from what the 2024 car observably did. That keeps
the transform free of grade-C aero guesses — the only sourced numbers are the
2026 deltas applied afterwards (AR-01, AR-02, AR-08).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from senna.physics.synth.segments import KMH_TO_MS, lap_phases

GRAVITY_MS2 = 9.81
INTEGRATION_STEPS = 2000  # RK4 over distance; step error far below the 1e-3 closed-form bar


def taper_kw(
    speed_kmh, *, mgu_k_max_kw: float, full_power_to_kmh: float, zero_power_at_kmh: float
) -> np.ndarray:
    """MGU-K power vs speed: full to 290 km/h, linear to zero at 355 (AR-02)."""
    speed = np.asarray(speed_kmh, dtype=float)
    fraction = (zero_power_at_kmh - speed) / (zero_power_at_kmh - full_power_to_kmh)
    return mgu_k_max_kw * np.clip(fraction, 0.0, 1.0)


@dataclass(frozen=True)
class EffectiveCar:
    p_drive_kw: float
    beta_drag: float  # N/(m/s)^2 — absorbs rho*CdA/2 and rolling resistance
    mu_brake: float
    kappa_brake: float
    check_err_frac: float
    ok: bool


@dataclass(frozen=True)
class StraightRun:
    time_s: float
    v_end_kmh: float
    e_dep_mj: float


def run_straight(
    v0_kmh: float,
    dist_m: float,
    *,
    mass_kg: float,
    p_base_kw: float,
    beta_drag: float,
    taper: dict,
) -> StraightRun:
    """Integrate a full-throttle run over dist_m; e_dep counts only the MGU-K side (F-02)."""

    def total_power_w(v_ms: float) -> float:
        return 1000.0 * (p_base_kw + float(taper_kw(v_ms / KMH_TO_MS, **taper)))

    def harvest_side_w(v_ms: float) -> float:
        return 1000.0 * float(taper_kw(v_ms / KMH_TO_MS, **taper))

    # state over distance: (time, speed, deployed energy)
    def gradient(state: np.ndarray) -> np.ndarray:
        v_ms = state[1]
        accel = (total_power_w(v_ms) / v_ms - beta_drag * v_ms * v_ms) / mass_kg
        return np.array([1.0 / v_ms, accel / v_ms, harvest_side_w(v_ms) / v_ms])

    state = np.array([0.0, v0_kmh * KMH_TO_MS, 0.0])
    step_m = dist_m / INTEGRATION_STEPS
    for _ in range(INTEGRATION_STEPS):
        k1 = gradient(state)
        k2 = gradient(state + 0.5 * step_m * k1)
        k3 = gradient(state + 0.5 * step_m * k2)
        k4 = gradient(state + step_m * k3)
        state = state + step_m / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    return StraightRun(
        time_s=float(state[0]),
        v_end_kmh=float(state[1] / KMH_TO_MS),
        e_dep_mj=float(state[2] / 1e6),
    )


def fit_effective_car(
    car_data: pd.DataFrame,
    *,
    mass_kg: float,
    throttle_full_pct: float,
    accel_smooth_window_s: float,
    profile_tolerance_frac: float,
) -> EffectiveCar:
    """Least squares on phase-interior finite differences, then a self-check.

    Differences span accel_smooth_window_s of samples but never a phase edge or
    a trace_id boundary — the interval leaving the last full-throttle sample
    already brakes, and a pair across a dropout hole reads a fraction of the
    true acceleration (AR-16, the fits/energy.py convention).
    """
    drive_v_ms: list[float] = []
    drive_a: list[float] = []
    brake_v_ms: list[float] = []
    brake_a: list[float] = []
    for _, trace in car_data.groupby("trace_id"):
        time_s = trace["Time"].dt.total_seconds().to_numpy()
        v_ms = trace["Speed"].to_numpy(dtype=float) * KMH_TO_MS
        brake = trace["Brake"].to_numpy(dtype=bool)
        full = (trace["Throttle"].to_numpy(dtype=float) >= throttle_full_pct) & ~brake
        if len(time_s) < 2:
            continue
        span = max(1, round(accel_smooth_window_s / float(np.median(np.diff(time_s)))))
        for i in range(len(time_s) - span):
            j = i + span
            v_mid = 0.5 * (v_ms[i] + v_ms[j])
            accel = (v_ms[j] - v_ms[i]) / (time_s[j] - time_s[i])
            if full[i : j + 1].all():
                drive_v_ms.append(v_mid)
                drive_a.append(accel)
            elif brake[i : j + 1].all():
                brake_v_ms.append(v_mid)
                brake_a.append(accel)

    v_drive = np.array(drive_v_ms)
    # m*a = P/v - beta*v^2, linear in (P, beta)
    drive_design = np.column_stack([1.0 / v_drive, -v_drive**2])
    p_drive_w, beta_drag = np.linalg.lstsq(
        drive_design, mass_kg * np.array(drive_a), rcond=None
    )[0]

    mu_brake, kappa_brake = 0.0, 0.0
    if brake_v_ms:
        v_brake = np.array(brake_v_ms)
        # -a = mu*g + kappa*v^2
        brake_design = np.column_stack([np.full_like(v_brake, GRAVITY_MS2), v_brake**2])
        mu_brake, kappa_brake = np.linalg.lstsq(
            brake_design, -np.array(brake_a), rcond=None
        )[0]

    check_err_frac = _phase_time_error(
        car_data,
        mass_kg=mass_kg,
        p_drive_w=float(p_drive_w),
        beta_drag=float(beta_drag),
        throttle_full_pct=throttle_full_pct,
    )
    return EffectiveCar(
        p_drive_kw=float(p_drive_w) / 1000.0,
        beta_drag=float(beta_drag),
        mu_brake=float(mu_brake),
        kappa_brake=float(kappa_brake),
        check_err_frac=check_err_frac,
        ok=check_err_frac <= profile_tolerance_frac,
    )


def _phase_time_error(
    car_data: pd.DataFrame,
    *,
    mass_kg: float,
    p_drive_w: float,
    beta_drag: float,
    throttle_full_pct: float,
) -> float:
    """Median relative error reproducing each observed full-throttle phase time.

    One car model must explain every phase; a lap the model cannot reproduce
    flags itself out of the transform rather than silently distorting it.
    """
    errors = []
    for phase in lap_phases(car_data, throttle_full_pct=throttle_full_pct):
        if phase.kind != "throttle":
            continue
        observed_s = phase.t_end_s - phase.t_start_s
        if observed_s <= 0.0 or phase.dist_m <= 0.0:
            continue
        modelled = _time_over_distance(
            phase.v_start_kmh * KMH_TO_MS,
            phase.dist_m,
            mass_kg=mass_kg,
            power_w=p_drive_w,
            beta_drag=beta_drag,
        )
        errors.append(abs(modelled - observed_s) / observed_s)
    return float(np.median(errors)) if errors else np.inf


def _time_over_distance(
    v0_ms: float, dist_m: float, *, mass_kg: float, power_w: float, beta_drag: float
) -> float:
    step_m = dist_m / INTEGRATION_STEPS
    t_s, v_ms = 0.0, v0_ms
    for _ in range(INTEGRATION_STEPS):
        # midpoint step is plenty here: the self-check compares against ~1e-1
        # relative tolerances, not the closed form
        accel = (power_w / v_ms - beta_drag * v_ms * v_ms) / mass_kg
        v_half = v_ms + accel * (step_m / v_ms) / 2.0
        accel_half = (power_w / v_half - beta_drag * v_half * v_half) / mass_kg
        dt = step_m / v_half
        t_s += dt
        v_ms += accel_half * dt
    return t_s
