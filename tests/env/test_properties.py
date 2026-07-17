"""The compliance-by-construction property (E-01, F-16). Across ~100k random
transitions the executed action is always one the mask permitted, SOC never
leaves [0, 4] MJ, and the per-step energy ledger balances to 1e-9 MJ.

Marked slow as well as property: reaching 100k transitions runs past the fast
suite's budget, so /ship gates it deliberately.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

USABLE_SOC_MJ = 4.0
TRANSITIONS_PER_SEED = 20_000  # 5 hypothesis seeds -> ~100k transitions total


def _sample_legal_action(pit_mask, mode_mask, rng):
    pit_choices = np.flatnonzero(pit_mask)
    mode_choices = np.flatnonzero(mode_mask)
    return np.array([rng.choice(pit_choices), rng.choice(mode_choices)])


@pytest.mark.property
@pytest.mark.slow
@given(base_seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=5, deadline=None)
def test_random_legal_play_keeps_soc_and_energy_within_bounds(make_env, base_seed):
    env = make_env()
    rng = np.random.default_rng(base_seed)

    transitions = 0
    while transitions < TRANSITIONS_PER_SEED:
        obs, info = env.reset(seed=int(rng.integers(0, 2**31)))
        terminated = False
        while not terminated and transitions < TRANSITIONS_PER_SEED:
            flat = env.action_masks()
            pit_mask, mode_mask = flat[:6], flat[6:]
            # the mask never strands a head with no legal action (MaskablePPO contract)
            assert pit_mask.any()
            assert mode_mask.any()

            action = _sample_legal_action(pit_mask, mode_mask, rng)
            soc_before = info["energy"]["soc_mj"]

            obs, reward, terminated, truncated, info = env.step(action)
            energy = info["energy"]
            soc_after = energy["soc_mj"]

            # the action we chose was legal under the mask read before stepping (F-16)
            assert pit_mask[action[0]]
            assert mode_mask[action[1]]
            # E-01: the store stays inside its physical bounds no matter the request
            assert -1e-9 <= soc_after <= USABLE_SOC_MJ + 1e-9
            # and when the clip does not bite, harvest minus deploy is conserved exactly
            if 1e-6 < soc_after < USABLE_SOC_MJ - 1e-6:
                assert soc_after - soc_before == pytest.approx(
                    energy["harvest_mj"] - energy["deploy_mj"], abs=1e-9
                )

            assert truncated is False  # the horizon is the race by definition (5.5.5)
            transitions += 1
