"""Seed discipline (5.5.5): reset(seed=k) plus an identical action stream
reproduces a byte-identical episode across events, rivals and noise; a different
seed diverges. This is the SubprocVecEnv statelessness contract kept from v2.
"""

import numpy as np

from tests.env.conftest import SEED

# a fixed policy: run balanced, take a single mid-race stop, run balanced to the flag
ACTIONS = [[0, 1]] * 15 + [[2, 1]] + [[0, 1]] * 80


def _run(env, seed):
    obs, info = env.reset(seed=seed)
    frames = [obs.copy()]
    rewards = []
    for action in ACTIONS:
        obs, reward, terminated, truncated, info = env.step(np.array(action))
        frames.append(obs.copy())
        rewards.append(reward)
        if terminated:
            break
    return np.array(frames), np.array(rewards)


def test_the_same_seed_and_actions_reproduce_the_episode(make_env):
    frames_a, rewards_a = _run(make_env(), SEED)
    frames_b, rewards_b = _run(make_env(), SEED)

    assert np.array_equal(frames_a, frames_b)
    assert np.array_equal(rewards_a, rewards_b)


def test_different_seeds_diverge(make_env):
    frames_a, rewards_a = _run(make_env(), SEED)
    frames_b, rewards_b = _run(make_env(), SEED + 1)

    diverged = not np.array_equal(rewards_a, rewards_b) or not np.array_equal(
        frames_a, frames_b
    )
    assert diverged
