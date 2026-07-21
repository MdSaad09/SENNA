"""The flip probe rebuilds the pit mask from a swept observation rather than reusing
the recorded one. That reconstruction is the load-bearing claim behind every "would
have stayed out" line on a card, so it is pinned against the env's own masks over a
real race — every argument recovered from the encoding, on every lap.
"""

import numpy as np

from senna.env import F1RaceEnv
from senna.explain.run import pit_mask_fn
from senna.strategy.random_legal import RandomLegal
from tests.explain.conftest import CIRCUIT, SEED


def test_reconstruction_matches_the_env_mask():
    # markov weather plus the full hazard set: random-legal play wanders through
    # compounds, SOC states and track statuses, so the rebuild is exercised well
    # past the dry green-flag path
    env = F1RaceEnv(CIRCUIT, "2026", rival_band="train", weather="markov",
                    hazards="full")
    from_obs = pit_mask_fn(env.scenario)

    obs, info = env.reset(seed=SEED)
    policy = RandomLegal()
    policy.reset(obs, info, rng=np.random.default_rng(SEED))

    terminated, laps = False, 0
    while not terminated:
        expected = env.action_masks()[:6]
        assert np.array_equal(from_obs(obs), expected), (
            f"lap {info['lap']}: rebuilt {from_obs(obs)} but the env says {expected}"
        )
        obs, _, terminated, _, info = env.step(policy.act(obs, info, env.action_masks()))
        laps += 1

    assert laps > 10  # a race that ended immediately would prove nothing
