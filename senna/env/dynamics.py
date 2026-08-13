"""Per-lap transition physics (spec 5.5.3), all 22 cars at once in numpy. The agent
requests a pace mode; physics disposes. Deployment is clipped to what the store and
the circuit's deployable-energy integral allow, and any shortfall is priced as a
lap-time derate — together with the action masks this is what makes legality hold by
construction (F-16), never a reward penalty.

Fitted and stylised constants arrive through the scenario; nothing here is inline.
"""

from dataclasses import dataclass

import numpy as np

from senna.env.scenario import COMPOUNDS

CONSERVE, BALANCED, ATTACK, DEFEND = 0, 1, 2, 3
GREEN, VSC, SC, RED = 0, 1, 2, 3
_INTERMEDIATE = COMPOUNDS.index("INTERMEDIATE")
_WET = COMPOUNDS.index("WET")


def tyre_deg_s(t0_s, a, b, age):
    """Grip loss expressed as lap-time delta: a * t0 * age**b (T5). `a` is the fractional
    loss per age**b that the F02 fitter stored, so multiplying by t0 recovers seconds."""
    return a * t0_s * age**b


def grip_est(a, b, age):
    """The simulator's own grip state, 1 - a*age**b, clipped to [0, 1] — the analogue of
    an engineer's deg model that the observation exposes (#10)."""
    return np.clip(1.0 - a * age**b, 0.0, 1.0)


def derate_penalty_s(request_mj, deploy_mj, p_der):
    """p_der * max(0, requested - delivered): the straight-line time lost when the store
    cannot supply the deployment the mode asked for (E-01)."""
    return p_der * np.maximum(0.0, request_mj - deploy_mj)


@dataclass(frozen=True)
class LapOutcome:
    """What a lap did to every car. Racing and pit time are reported apart as well as
    summed: the pace term is scored on the racing lap alone, so a stop is not read as
    a slow lap (5.5.4)."""

    lap_time_s: np.ndarray
    racing_time_s: np.ndarray
    pit_time_s: np.ndarray
    harvest_mj: np.ndarray
    deploy_mj: np.ndarray
    soc_next_mj: np.ndarray
    derate_penalty_s: np.ndarray
    failed: np.ndarray  # tyre let go this lap: a forced stop, not a retirement (5.5.5)
    red_flag: bool


def per_lap_harvest_mj(scenario, track_status: int) -> float:
    """Recovery is flow-limited (5.5.3): braking plus super-clipping harvest, capped at the
    FIA per-lap recoverable-energy limit. In 2026 the cap almost always binds, so the 4 MJ
    store buffers the difference against deployment — the banking lever is how much a mode
    deploys, not how much it harvests. Under a neutralisation the field brakes less and
    harvests less, so the cap stops binding and obs #16 moves (E-03)."""
    harvest = min(scenario.h_max_mj, scenario.harvest_braking_mj + scenario.harvest_clipping_mj)
    if track_status in (SC, VSC):
        harvest *= scenario.env["harvest"]["neutralized_scale"]
    return harvest


def deploy_request_mj(modes: np.ndarray, scenario) -> np.ndarray:
    """Each mode asks for a share of the circuit's deployable-energy integral E_dep."""
    frac = scenario.env["deploy"]["mode_request_frac"]
    share = np.array([frac["conserve"], frac["balanced"], frac["attack"], frac["defend"]])
    return share[modes] * scenario.e_dep_mj


def resolve_energy(soc_mj, harvest_mj, request_mj, scenario):
    """Clip deployment to E_dep and to what the store plus this lap's usable harvest can
    supply, then update SOC with a hard clip to [0, 4]. Returns (delivered, derate, soc')."""
    intra = scenario.env["harvest"]["intra_lap_share"]
    available = soc_mj + intra * harvest_mj
    delivered = np.minimum(request_mj, np.minimum(scenario.e_dep_mj, available))
    derate = derate_penalty_s(request_mj, delivered, scenario.derate_penalty_s_per_mj)
    soc_next = np.clip(soc_mj + harvest_mj - delivered, 0.0, scenario.usable_soc_mj)
    return delivered, derate, soc_next


def mode_pace_s(modes: np.ndarray, delivered_mj, request_mj, scenario) -> np.ndarray:
    """The pace each mode buys or pays. Conserve lifts and coasts to bank energy, paying
    c_lc per banked MJ; attack spends toward E_dep for a straight-line gain, scaled by how
    much of the request the store could actually supply; balanced and defend are neutral."""
    frac = scenario.env["deploy"]["mode_request_frac"]
    banked_mj = max(0.0, frac["balanced"] - frac["conserve"]) * scenario.e_dep_mj
    pace = np.zeros_like(delivered_mj, dtype=float)
    pace[modes == CONSERVE] = scenario.conserve_pace_cost_s_per_mj * banked_mj
    attack = modes == ATTACK
    achieved = np.divide(
        delivered_mj, request_mj, out=np.zeros_like(delivered_mj, dtype=float), where=request_mj > 0
    )
    pace[attack] = -scenario.attack_pace_gain_s * achieved[attack]
    return pace


def wet_penalty_s(compound: np.ndarray, wetness: float, scenario) -> np.ndarray:
    """Pace cost for a compound that does not suit the wetness (E-08). Slicks suffer as the
    track wets; a full wet grains on a drying track. The crossover on this scalar is where
    the British GP counterfactual lives."""
    validity = scenario.env["compound_validity"]
    scale = scenario.env["weather"]["wet_mismatch_penalty_s"]
    is_slick = compound < _INTERMEDIATE
    is_wet = compound == _WET
    slick_over = np.maximum(0.0, wetness - validity["slick_max_wetness"])
    wet_under = np.maximum(0.0, validity["wet_min_wetness"] - wetness)
    penalty = np.where(is_slick, scale * slick_over, 0.0)
    penalty = np.where(is_wet, scale * wet_under, penalty)
    return penalty


def lap_time_s(*, compound, age, fuel_kg, modes, delivered_mj, request_mj, derate_s,
               gap_ahead_s, wetness, track_status, driver_s, noise_s, scenario) -> np.ndarray:
    """The joint lap-time model (5.5.3), assembled per car. Neutralisation multiplies the
    green lap time by the fitted SC/VSC factor — those constants are lap-time multipliers,
    not additive seconds, so the '+ status' in the spec pseudocode is a ×."""
    offset = _compound_lookup(compound, scenario.compound_offset_s, scenario)
    a = _compound_lookup(compound, scenario.deg_a, scenario)
    b = _compound_lookup(compound, scenario.deg_b, scenario)
    if scenario.lineup is not None:
        # per-driver tyre style (F17). T5's form is untouched — the multiplier scales the
        # fitted amplitude, so a fresh set still costs nothing whoever is driving it, and
        # the observation keeps reporting the pooled curve because that is the engineer's
        # model of the tyre rather than this driver's realised wear (F20 owns the obs).
        a = a * scenario.lineup.deg_mult[: a.size]

    deg = tyre_deg_s(scenario.t0_s, a, b, age)
    fuel_term = scenario.k_m_s_per_kg * fuel_kg
    pace = mode_pace_s(modes, delivered_mj, request_mj, scenario)
    close = gap_ahead_s < scenario.dirty_air_threshold_s
    dirty_air_s = scenario.env["traffic"]["dirty_air_penalty_s"] * scenario.aero_traffic_scale
    traffic = np.where(close, dirty_air_s, 0.0)
    wet = wet_penalty_s(compound, wetness, scenario)

    green = (
        scenario.t0_s + offset + deg + fuel_term + pace + derate_s + traffic + wet
        + driver_s + noise_s
    )
    mult = np.ones_like(green)
    mult[track_status == SC] = scenario.status_mult["sc"]
    mult[track_status == VSC] = scenario.status_mult["vsc"]
    return green * mult


def _compound_lookup(compound: np.ndarray, table: dict, scenario) -> np.ndarray:
    """Map each car's compound code to its per-compound scalar. A compound with no fit
    (e.g. a wet tyre where only slicks were fitted) falls back to the hardest slick, so a
    forced wet stop still runs rather than throwing in the hot loop."""
    out = np.empty(compound.shape, dtype=float)
    fallback = table.get("HARD") or next(iter(table.values()))
    for code, name in enumerate(COMPOUNDS):
        out[compound == code] = table.get(name, fallback)
    return out
