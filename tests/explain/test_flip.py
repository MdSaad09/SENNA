"""Counterfactual flip probes (5.8.2): sweep one feature across its physical range
against the true policy and report the first value where the choice changes. The
mask is recomputed at every sweep point — sweeping wetness or SOC crosses mask
thresholds, and a flip onto an action the mask forbids there would be a lie.
"""

import numpy as np
import pytest

from senna.explain.features import SWEEPABLE
from senna.explain.flip import find_flip

TYRE_AGE_DIM = 8
WETNESS_DIM = 30
STAY, SLICK_PIT, WET_PIT = 0, 1, 5  # pit-head action codes


def _grid(dim, points=101):
    lo, hi = SWEEPABLE[dim]
    return np.linspace(lo, hi, points)


def _lane_always_open(obs):
    return np.ones(6, dtype=bool)


def test_flip_probe_finds_known_threshold():
    def pits_past_a_worn_set(obs, mask):
        return SLICK_PIT if obs[TYRE_AGE_DIM] > 0.42 else STAY

    obs = np.zeros(32, dtype=np.float32)
    obs[TYRE_AGE_DIM] = 0.1  # recorded action: stay out

    flip_at = find_flip(pits_past_a_worn_set, obs, TYRE_AGE_DIM, _grid(TYRE_AGE_DIM),
                        _lane_always_open)

    assert flip_at == pytest.approx(0.43)  # first grid point past the built-in threshold


def test_flip_reports_the_nearest_crossing():
    # the recorded set is already worn past the threshold, so the honest counterfactual
    # is the fresher tyre just below it — a sweep scanning from the bottom of the range
    # would report 0.00 ("about 0 laps"), which is a false line on a card
    def pits_past_a_worn_set(obs, mask):
        return SLICK_PIT if obs[TYRE_AGE_DIM] > 0.42 else STAY

    obs = np.zeros(32, dtype=np.float32)
    obs[TYRE_AGE_DIM] = 0.8  # recorded action: pit

    flip_at = find_flip(pits_past_a_worn_set, obs, TYRE_AGE_DIM, _grid(TYRE_AGE_DIM),
                        _lane_always_open)

    assert flip_at == pytest.approx(0.42)


def test_sweep_recomputes_mask():
    # an over-eager policy wants the full wet from 0.5 wetness, but the tyre only
    # becomes legal at 0.7 — like MaskablePPO, the policy can never pick a masked action
    def wants_the_wet_early(obs, mask):
        if obs[WETNESS_DIM] > 0.5 and mask[WET_PIT]:
            return WET_PIT
        return STAY

    def wet_legal_from(obs):
        mask = np.ones(6, dtype=bool)
        mask[WET_PIT] = obs[WETNESS_DIM] >= 0.7
        return mask

    obs = np.zeros(32, dtype=np.float32)
    obs[WETNESS_DIM] = 0.2  # bone dry at the recorded decision; mask forbids the wet

    flip_at = find_flip(wants_the_wet_early, obs, WETNESS_DIM, _grid(WETNESS_DIM),
                        wet_legal_from)

    # the honest flip sits where the action first becomes legal AND preferred (0.70),
    # never at the eagerness point (0.51) where the mask still forbids it; a sweep
    # holding the recorded mask fixed would report no flip at all
    assert flip_at == pytest.approx(0.70)
    assert wet_legal_from(_swept(obs, flip_at))[WET_PIT]


def _swept(obs, value):
    swept = obs.copy()
    swept[WETNESS_DIM] = value
    return swept
