"""The 32-dimension ego observation (spec 5.5.1). Every dimension is named, bounded to
[-1, 1] and justified in the table; the raw encodings are already scale-bounded so the
served model degrades gracefully if VecNormalize statistics drift. Rival context is the
actual neighbours' continuous tyre state, not v2's binary archetype flags.
"""

import numpy as np

from senna.env.dynamics import grip_est
from senna.env.events import GREEN, RED, SC, VSC
from senna.env.scenario import COMPOUNDS

OBS_DIM = 32
_N_COMPOUNDS = len(COMPOUNDS)
_MAX_HARDNESS = _N_COMPOUNDS - 1
_NO_DEG_A, _NO_DEG_B = 0.0, 1.0  # a compound with no fit reads as full grip (identity)
# red is an event, not a state the policy acts in (5.5.1), so it shares the green slot
_STATUS_SLOT = {GREEN: 0, VSC: 1, SC: 2, RED: 0}


def encode(state, scenario, *, gap_ahead_s: float, gap_behind_s: float,
           ahead: int | None, behind: int | None, pit_open: bool) -> np.ndarray:
    """Build the ego's view. Gaps and neighbour indices are computed once by the env from
    the shared classification and passed in, so this stays a pure assembly of scalars."""
    ego = state.ego
    obs_cfg = scenario.env["obs"]
    age_norm = obs_cfg["tyre_age_norm_laps"]
    gap_cap = obs_cfg["gap_norm_cap_s"]

    position = int(state.positions()[ego])
    compound = int(state.compound[ego])
    age = float(state.tyre_age[ego])

    obs = np.zeros(OBS_DIM, dtype=np.float32)
    obs[0] = state.lap / scenario.total_laps
    obs[1] = (position - 1) / (state.n_cars - 1)
    obs[2] = _unit((state.grid_position[ego] - position) / (state.n_cars - 1))
    obs[3 + compound] = 1.0
    obs[8] = min(age / age_norm, 1.0)
    obs[9] = grip_est(scenario.deg_a.get(COMPOUNDS[compound], _NO_DEG_A),
                      scenario.deg_b.get(COMPOUNDS[compound], _NO_DEG_B), age)
    cliff_age = scenario.deg_max_age.get(COMPOUNDS[compound], age_norm)
    obs[10] = _tyre_temp_state(age, cliff_age, obs_cfg["tyre_cold_age_laps"])
    obs[11] = min(state.pit_count[ego] / obs_cfg["max_stops_norm"], 1.0)
    obs[12] = float(state.second_compound_used[ego])
    obs[13] = state.fuel_kg[ego] / scenario.race_fuel_kg
    obs[14] = state.soc_mj[ego] / scenario.usable_soc_mj
    obs[15] = min(state.last_harvest_mj[ego] / scenario.h_max_mj, 1.0)
    obs[16] = min(state.last_deploy_mj[ego] / scenario.e_dep_mj, 1.0)

    has_ahead = ahead is not None
    obs[17] = min((gap_ahead_s if has_ahead else gap_cap), gap_cap) / gap_cap
    obs[18] = min((gap_behind_s if behind is not None else gap_cap), gap_cap) / gap_cap
    if has_ahead:
        obs[19] = _unit((state.tyre_age[ahead] - age) / age_norm)
        obs[20] = _unit((int(state.compound[ahead]) - compound) / _MAX_HARDNESS)
    if behind is not None:
        obs[21] = _unit((state.tyre_age[behind] - age) / age_norm)
    obs[22] = 1.0 if (has_ahead and gap_ahead_s <= scenario.override_gap_s) else 0.0

    obs[23 + _STATUS_SLOT[state.track_status]] = 1.0
    obs[26] = 1.0 if pit_open else 0.0
    obs[27 + state.weather] = 1.0
    obs[30] = state.wetness
    obs[31] = _track_temp_norm(state.wetness, scenario)
    return obs


def _unit(value: float) -> float:
    return float(np.clip(value, -1.0, 1.0))


def _tyre_temp_state(age: float, cliff_age: float, cold_age: float) -> float:
    """Cliff-risk signal (#11): a fresh out-lap runs cold, a set past its cliff runs hot,
    everything between is optimal. The 0 / 0.5 / 1 values are the 5.5.1 encoding; the
    cold-age boundary is the stylised knob."""
    if age <= cold_age:
        return 0.0
    if age >= cliff_age:
        return 1.0
    return 0.5


def _track_temp_norm(wetness: float, scenario) -> float:
    weather = scenario.env["weather"]
    temp_c = weather["track_temp_dry_c"] - wetness * weather["track_temp_wet_drop_c"]
    obs_cfg = scenario.env["obs"]
    norm = (temp_c - obs_cfg["track_temp_min_c"]) / obs_cfg["track_temp_span_c"]
    return float(np.clip(norm, 0.0, 1.0))
