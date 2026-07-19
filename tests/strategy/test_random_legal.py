"""The random-legal baseline (A-07): it samples uniformly among the actions the mask
permits, so by construction it can never propose an illegal one. This is the same
compliance-by-construction property the env guarantees (F-16), read from the policy
side. The baseline doubles as the throughput-bench driver and an oracle baseline.
"""

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from senna.strategy.random_legal import RandomLegal
from senna.strategy.rollout import run_episode
from tests.strategy.conftest import SEED


def _drive_and_assert_legal(env, policy, max_laps):
    obs, info = env.reset(seed=SEED)
    policy.reset(obs, info, rng=np.random.default_rng(SEED))
    terminated = False
    laps = 0
    while not terminated and laps < max_laps:
        mask = env.action_masks()
        action = policy.act(obs, info, mask)
        # the mask read before stepping must permit both heads of the chosen action
        assert mask[:6][action[0]], "pit head chose a masked compound"
        assert mask[6:][action[1]], "mode head chose a masked energy mode"
        obs, reward, terminated, truncated, info = env.step(action)
        laps += 1


def test_the_random_legal_baseline_never_proposes_a_masked_action(make_env):
    env = make_env()
    _drive_and_assert_legal(env, RandomLegal(), env.total_laps)


@pytest.mark.property
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
# make_env builds a fresh env per example, so reusing the fixture across seeds is safe
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_the_random_legal_baseline_never_proposes_a_masked_action_over_many_seeds(
    make_env, seed
):
    env = make_env()
    obs, info = env.reset(seed=seed)
    policy = RandomLegal()
    policy.reset(obs, info, rng=np.random.default_rng(seed))
    for _ in range(8):  # a handful of laps per seed is enough to exercise the masks
        mask = env.action_masks()
        action = policy.act(obs, info, mask)
        assert mask[:6][action[0]]
        assert mask[6:][action[1]]
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated:
            break


def test_the_same_seed_reproduces_a_random_legal_episode(make_env):
    first = run_episode(make_env(), RandomLegal(), seed=SEED)
    second = run_episode(make_env(), RandomLegal(), seed=SEED)

    assert first.race_time_s == second.race_time_s
    assert np.array_equal(np.array(first.actions), np.array(second.actions))
