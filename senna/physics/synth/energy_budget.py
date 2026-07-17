"""T4 — the energy accounting layer: four numbers per circuit.

H_max (per-event cap, E-02), deployable energy E_dep (from T1), and the two
harvest mechanisms — braking recovery and super-clipping on throttle (AR-07) —
are the entire energy game (F-02/F-04). Supply is what the mechanisms deliver
capped by H_max; any shortfall against E_dep is the derate deficit. Lift-and-
coast (AR-06) buys extra harvest by spending lap time; c_lc is the price.
"""

from dataclasses import dataclass

import numpy as np

from senna.config import NullConstantError
from senna.physics.synth.pointmass import taper_kw
from senna.physics.synth.segments import KMH_TO_MS

LIFT_FRACTIONS_LO_HI = (0.85, 0.99)  # sweep grid: shallow to deep lift, as pinned by the tests
SWEEP_STEPS = 4000  # distance steps per leg; step error well below the 5% slope tolerance


@dataclass(frozen=True)
class EnergyBudget:
    h_max_mj: float
    e_dep_mj: float
    harvest_braking_mj: float
    harvest_clipping_mj: float
    supply_mj: float
    deficit_mj: float


def energy_budget(
    *,
    h_max_mj: float,
    e_dep_mj: float,
    braking_energy_mj: float,
    full_throttle_s: float,
    super_clipping_kw: float,
) -> EnergyBudget:
    if h_max_mj is None:
        raise NullConstantError(
            "h_max_mj is null — set the per-event cap in circuits.yaml before the "
            "energy budget can be computed (E-02)"
        )
    harvest_clipping_mj = super_clipping_kw * full_throttle_s / 1000.0
    supply_mj = min(h_max_mj, braking_energy_mj + harvest_clipping_mj)
    return EnergyBudget(
        h_max_mj=h_max_mj,
        e_dep_mj=e_dep_mj,
        harvest_braking_mj=braking_energy_mj,
        harvest_clipping_mj=harvest_clipping_mj,
        supply_mj=supply_mj,
        deficit_mj=max(0.0, e_dep_mj - supply_mj),
    )


def c_lc_s_per_mj(
    v_end_kmh: float,
    *,
    mass_kg: float,
    p_base_kw: float,
    beta_drag: float,
    taper: dict,
    lift_kw: float,
    sweep_points: int,
) -> float:
    """Lift-and-coast pace cost, fitted from the calibrated point-mass profile.

    For each lift depth: accelerate flat out from the lift speed to v_end over
    some distance, versus lift and coast under harvest power over that same
    distance. The extra time against the harvested megajoules is the cost, and
    the through-origin slope over the sweep is c_lc — a derived quantity from
    the profile, not a regression on noisy race laps.
    """
    v_end_ms = v_end_kmh * KMH_TO_MS
    lift_speeds_ms = np.linspace(*LIFT_FRACTIONS_LO_HI, sweep_points) * v_end_ms
    delta_t_s = []
    harvest_mj = []
    for v_lift_ms in lift_speeds_ms:
        t_flat_s, dist_m = _flat_out_to_speed(
            v_lift_ms, v_end_ms, mass_kg=mass_kg, p_base_kw=p_base_kw,
            beta_drag=beta_drag, taper=taper,
        )
        t_coast_s, harvest_j = _coast_over_distance(
            v_lift_ms, dist_m, mass_kg=mass_kg, beta_drag=beta_drag, lift_kw=lift_kw,
        )
        delta_t_s.append(t_coast_s - t_flat_s)
        harvest_mj.append(harvest_j / 1e6)
    deltas = np.array(delta_t_s)
    harvests = np.array(harvest_mj)
    return float(np.sum(deltas * harvests) / np.sum(harvests * harvests))


def _flat_out_to_speed(
    v0_ms: float, v_target_ms: float, *, mass_kg: float, p_base_kw: float,
    beta_drag: float, taper: dict,
) -> tuple[float, float]:
    """Time and distance accelerating flat out from v0 up to v_target."""
    v_ms, t_s, dist_m = v0_ms, 0.0, 0.0
    dv = (v_target_ms - v0_ms) / SWEEP_STEPS
    for _ in range(SWEEP_STEPS):
        power_w = 1000.0 * (p_base_kw + float(taper_kw(v_ms / KMH_TO_MS, **taper)))
        accel = (power_w / v_ms - beta_drag * v_ms * v_ms) / mass_kg
        dt = dv / accel
        t_s += dt
        dist_m += v_ms * dt
        v_ms += dv
    return t_s, dist_m


def _coast_over_distance(
    v0_ms: float, dist_m: float, *, mass_kg: float, beta_drag: float, lift_kw: float,
) -> tuple[float, float]:
    """Coast under constant harvest power over dist_m; time and MGU-K harvest."""
    step_m = dist_m / SWEEP_STEPS
    v_ms, t_s, harvest_j = v0_ms, 0.0, 0.0
    power_w = 1000.0 * lift_kw
    for _ in range(SWEEP_STEPS):
        accel = (-power_w / v_ms - beta_drag * v_ms * v_ms) / mass_kg
        dt = step_m / v_ms
        t_s += dt
        harvest_j += power_w * dt
        v_ms += accel * dt
    return t_s, harvest_j
