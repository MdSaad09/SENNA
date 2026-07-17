# The plan's test_missing_circuit_entry_uses_default is deliberately absent: the
# 8.5 MJ baseline arrives through the config chain in run.py at make-synth time
# (E-02), not through these pure functions, so there is nothing to pin here.

import numpy as np
import pytest

from senna.config import NullConstantError
from senna.physics.synth.energy_budget import c_lc_s_per_mj, energy_budget

SUPER_CLIPPING_KW = 250.0  # AR-07: harvest headroom while the ICE runs flat out

MASS_KG = 800.0
P_BASE_KW = 400.0
LIFT_KW = 350.0  # AR-06: lift-and-coast harvests at full MGU-K power (Z-mode)
V_END_KMH = 320.0
SWEEP_POINTS = 6
# pinned sweep contract: lift speeds at these fractions of v_end, shallow to deep;
# the analytic expectation below is computed on exactly this grid
LIFT_FRACTIONS = np.linspace(0.85, 0.99, SWEEP_POINTS)
# taper thresholds above the 320 km/h run, so total drive power stays constant
TAPER_ABOVE_RUN = {"mgu_k_max_kw": 350.0, "full_power_to_kmh": 400.0, "zero_power_at_kmh": 500.0}
SLOPE_RTOL = 0.05


def test_supply_is_min_of_cap_and_mechanisms():
    capped = energy_budget(
        h_max_mj=8.5,
        e_dep_mj=9.5,
        braking_energy_mj=7.0,
        full_throttle_s=12.0,
        super_clipping_kw=SUPER_CLIPPING_KW,
    )

    assert capped.harvest_clipping_mj == pytest.approx(3.0)  # 250 kW * 12 s
    # the mechanisms offer 10.0 MJ but the per-event cap binds (E-02); the 1.0 MJ
    # shortfall against E_dep is the derate deficit
    assert capped.supply_mj == pytest.approx(8.5)
    assert capped.deficit_mj == pytest.approx(1.0)
    assert capped.h_max_mj == pytest.approx(8.5)

    open_cap = energy_budget(
        h_max_mj=8.5,
        e_dep_mj=4.0,
        braking_energy_mj=4.0,
        full_throttle_s=4.0,
        super_clipping_kw=SUPER_CLIPPING_KW,
    )

    assert open_cap.harvest_braking_mj == pytest.approx(4.0)
    assert open_cap.harvest_clipping_mj == pytest.approx(1.0)
    assert open_cap.supply_mj == pytest.approx(5.0)  # mechanisms bind, cap slack
    assert open_cap.deficit_mj == 0.0


def test_c_lc_matches_analytic_sweep():
    # With beta = 0 both legs have closed forms (P and Q in W, v in m/s):
    #   flat out  m*v*dv/dt =  P  ->  t = m*(v_end^2 - v_lift^2)/(2P),
    #                               dist = m*(v_end^3 - v_lift^3)/(3P)
    #   coast     m*v*dv/dt = -Q  ->  over the same dist, v_f^3 = v_lift^3 - 3*Q*dist/m,
    #                               t = m*(v_lift^2 - v_f^2)/(2Q)
    # Harvest per lift is Q * t_coast; the expected c_lc is the least-squares
    # slope through the origin of (delta_t, harvest) over the pinned grid.
    p_w = 1000.0 * (P_BASE_KW + TAPER_ABOVE_RUN["mgu_k_max_kw"])
    q_w = 1000.0 * LIFT_KW
    v_end_ms = V_END_KMH / 3.6
    delta_t_s = []
    harvest_mj = []
    for fraction in LIFT_FRACTIONS:
        v_lift_ms = fraction * v_end_ms
        t_flat_s = MASS_KG * (v_end_ms**2 - v_lift_ms**2) / (2.0 * p_w)
        dist_m = MASS_KG * (v_end_ms**3 - v_lift_ms**3) / (3.0 * p_w)
        v_final_ms = (v_lift_ms**3 - 3.0 * q_w * dist_m / MASS_KG) ** (1.0 / 3.0)
        t_coast_s = MASS_KG * (v_lift_ms**2 - v_final_ms**2) / (2.0 * q_w)
        delta_t_s.append(t_coast_s - t_flat_s)
        harvest_mj.append(q_w * t_coast_s / 1e6)
    deltas = np.array(delta_t_s)
    harvests = np.array(harvest_mj)
    expected_slope = float(np.sum(deltas * harvests) / np.sum(harvests * harvests))

    slope = c_lc_s_per_mj(
        V_END_KMH,
        mass_kg=MASS_KG,
        p_base_kw=P_BASE_KW,
        beta_drag=0.0,
        taper=TAPER_ABOVE_RUN,
        lift_kw=LIFT_KW,
        sweep_points=SWEEP_POINTS,
    )

    assert slope > 0.0  # lifting always costs time; a free MJ would be a physics bug
    assert slope == pytest.approx(expected_slope, rel=SLOPE_RTOL)


def test_null_h_max_raises():
    # E-02 through the anti-black-box contract: a missing per-event cap must
    # never silently become zero supply or an unbounded one
    with pytest.raises(NullConstantError):
        energy_budget(
            h_max_mj=None,
            e_dep_mj=8.0,
            braking_energy_mj=6.0,
            full_throttle_s=10.0,
            super_clipping_kw=SUPER_CLIPPING_KW,
        )
