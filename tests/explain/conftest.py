"""Shared fixtures for the F09 explainability suite. Suite seed 933 keeps it apart
from fits (99), synth (271), env (512), strategy (704) and train (846), so a
cross-suite coincidence cannot mask a bug (5.5.5). SB3 and xgboost load inside the
fixtures and test modules that need them, never here.
"""

import os

# arm64 landmine (F09 plan): torch and xgboost each bundle libomp, and two OpenMP
# runtimes in one process segfault — single-threaded OpenMP, set before either loads
os.environ.setdefault("OMP_NUM_THREADS", "1")

import pytest  # noqa: E402

from senna.env import F1RaceEnv  # noqa: E402

SEED = 933
CIRCUIT = "bahrain_grand_prix"  # a raced 2026 event with real fitted params in configs


def _make_env():
    return F1RaceEnv(CIRCUIT, "2026")


@pytest.fixture(scope="module")
def tiny_agent():
    """A near-untrained MaskablePPO with frozen VecNormalize statistics — enough to
    emit real per-head distributions; nothing about its play quality matters."""
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

    venv = VecNormalize(DummyVecEnv([_make_env]), norm_obs=True, norm_reward=False)
    model = MaskablePPO(
        "MlpPolicy", venv, n_steps=8, batch_size=8, n_epochs=1,
        policy_kwargs={"net_arch": {"pi": [16], "vf": [16]}}, seed=SEED, device="cpu",
    )
    model.learn(total_timesteps=8)  # one tiny rollout, so obs_rms moves off its init
    venv.training = False
    return model, venv
