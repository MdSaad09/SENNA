"""Shared fixtures for the F10 serving-logic suite (senna/serve). Suite seed 1250 keeps
it apart from fits (99), synth (271), env (512), strategy (704), train (846), explain
(933) and api (1105), so a cross-suite coincidence cannot mask a bug (5.5.5).
"""

import os

# arm64 landmine (F09 plan): torch and xgboost each bundle libomp, and two OpenMP
# runtimes in one process segfault — single-threaded OpenMP, set before either loads
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from senna.env import F1RaceEnv  # noqa: E402

SEED = 1250
CIRCUIT = "bahrain_grand_prix"  # a raced 2026 event with real fitted params in configs


def sample_legal_action(flat_mask: np.ndarray, rng) -> np.ndarray:
    """Uniform over what the mask permits, per head — the random-legal pattern (A-07)."""
    return np.array([
        int(rng.choice(np.flatnonzero(flat_mask[:6]))),
        int(rng.choice(np.flatnonzero(flat_mask[6:]))),
    ])


@pytest.fixture
def make_env():
    def build(circuit: str = CIRCUIT, era: str = "2026", **kwargs) -> F1RaceEnv:
        return F1RaceEnv(circuit, era, **kwargs)

    return build


@pytest.fixture
def env(make_env):
    return make_env()
