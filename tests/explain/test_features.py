"""The names <-> indices contract: FEATURE_NAMES mirrors observation.encode dimension
for dimension, and the sweepable-dims table only ever names dims a single-feature
sweep makes sense for (F09 plan, flip probes). SHAP output is meaningless if this
mapping drifts, so it gets its own guard.
"""

import numpy as np

from senna.env import F1RaceEnv
from senna.env.observation import OBS_DIM, encode
from senna.env.state import RaceState
from senna.explain.features import FEATURE_NAMES, SWEEPABLE
from tests.explain.conftest import CIRCUIT

# dims that are one-hot slots or booleans in observation.encode: compound (3-7),
# second-compound flag (12), override window (22), track status (23-25), pit lane
# open (26), weather (27-29) — a physical sweep across any of these is nonsense
ONE_HOT_AND_BINARY_DIMS = frozenset({3, 4, 5, 6, 7, 12, 22, 23, 24, 25, 26, 27, 28, 29})
TYRE_TEMP_DIM = 10  # tri-state cold/optimal/hot — sweeps its three encoded values


def test_feature_names_match_obs_dim():
    assert len(FEATURE_NAMES) == OBS_DIM
    assert all(isinstance(name, str) and name for name in FEATURE_NAMES)
    assert len(set(FEATURE_NAMES)) == OBS_DIM  # a duplicate name would hide a dim

    # the flip-probe table names real dims and never a one-hot or binary slot
    assert set(SWEEPABLE) <= set(range(OBS_DIM))
    assert not set(SWEEPABLE) & ONE_HOT_AND_BINARY_DIMS
    for dim, grid_bounds in SWEEPABLE.items():
        if dim == TYRE_TEMP_DIM:
            continue
        lo, hi = grid_bounds
        assert lo < hi
    assert tuple(SWEEPABLE[TYRE_TEMP_DIM]) == (0.0, 0.5, 1.0)


def _two_car_state(*, soc_mj: float) -> RaceState:
    n = 2
    return RaceState(
        n_cars=n, lap=20,
        compound=np.array([1, 2]), tyre_age=np.array([8, 5]),
        soc_mj=np.array([soc_mj, 3.0]), fuel_kg=np.array([40.0, 40.0]),
        cumulative_time_s=np.array([1900.0, 1904.0]),
        grid_position=np.array([1, 2]), pit_count=np.array([1, 1]),
        second_compound_used=np.array([True, True]), first_compound=np.array([0, 1]),
        last_harvest_mj=np.array([4.0, 4.0]), last_deploy_mj=np.array([3.0, 3.0]),
        retired=np.array([False, False]), driver_s=np.zeros(n),
        track_status=0, status_laps_left=0, weather=0, wetness=0.0,
        red_flags_seen=0, red_flag_now=False, ego=0,
    )


def test_perturbation_maps_to_named_dim():
    # drift guard: bumping one physical quantity moves exactly the dim its name claims
    scenario = F1RaceEnv(CIRCUIT, "2026").scenario

    def obs_with(soc_mj):
        return encode(
            _two_car_state(soc_mj=soc_mj), scenario,
            gap_ahead_s=5.0, gap_behind_s=4.0, ahead=None, behind=1, pit_open=True,
        )

    changed = np.flatnonzero(obs_with(2.0) != obs_with(3.0))
    assert changed.size == 1
    assert "soc" in FEATURE_NAMES[changed[0]]
