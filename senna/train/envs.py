"""Stage vec-envs: deterministic circuit assignment across workers and one wrapper per
worker slot that owns the episode-seed stream. SB3 seeds only the first reset of each
worker; the wrapper derives every later episode's seed from that one anchor, so a whole
stage is reproducible from the stage seed alone (5.5.5, applied per episode).
"""

import numpy as np
from gymnasium import Env

from senna.env import F1RaceEnv


def assign_circuits(circuits: list, workers: int) -> list:
    """Worker i hosts circuits[i % n] when the list fits, else the slice circuits[i::w]
    — pure arithmetic on the yaml order, so the assignment reproduces from configs."""
    if len(circuits) <= workers:
        return [[circuits[i % len(circuits)]] for i in range(workers)]
    return [list(circuits[i::workers]) for i in range(workers)]


class CircuitCycler(Env):
    """One worker's slot: pre-built envs for its circuits, rotated on every reset (the
    env itself never changes circuit), and a per-worker episode-seed stream re-anchored
    by any seeded reset."""

    metadata = {"render_modes": []}

    def __init__(self, envs: list):
        self._envs = envs
        self._index = -1
        self._episode_rng = np.random.default_rng(None)  # re-anchored by venv.seed()
        self.action_space = envs[0].action_space
        self.observation_space = envs[0].observation_space

    def reset(self, *, seed=None, options=None):
        if seed is not None:
            self._episode_rng = np.random.default_rng(seed)
        self._index = (self._index + 1) % len(self._envs)
        episode_seed = int(self._episode_rng.integers(2**31 - 1))
        return self._envs[self._index].reset(seed=episode_seed, options=options)

    def step(self, action):
        return self._envs[self._index].step(action)

    def action_masks(self) -> np.ndarray:
        return self._envs[self._index].action_masks()

    def close(self):
        for env in self._envs:
            env.close()


def stage_venv(stage_cfg: dict, *, workers: int, stage_seed: int, vec: str,
               normalize: dict, stats_path=None, configs_dir=None):
    """The stage's VecNormalize-wrapped vec env. stats_path carries the previous
    stage's statistics in (5.7: continuity beats re-warming); fresh otherwise."""
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecNormalize

    assignment = assign_circuits(stage_cfg["circuits"], workers)
    env_kwargs = dict(stage_cfg["env"])
    band = stage_cfg["rival_band"]

    def worker(circuits):
        def make():
            envs = [
                F1RaceEnv(circuit, "2026", rival_band=band, configs_dir=configs_dir,
                          **env_kwargs)
                for circuit in circuits
            ]
            return Monitor(CircuitCycler(envs))

        return make

    vec_cls = SubprocVecEnv if vec == "subproc" else DummyVecEnv
    venv = vec_cls([worker(circuits) for circuits in assignment])
    if stats_path is not None:
        venv = VecNormalize.load(str(stats_path), venv)
        venv.training = True  # carried statistics keep adapting; frozen only at serving
        venv.norm_reward = False
    else:
        venv = VecNormalize(venv, norm_obs=normalize["obs"], norm_reward=normalize["reward"])
    venv.seed(stage_seed)
    return venv
