"""Shared fixtures for the F1RaceEnv suite (F05, master spec 5.5).

Seeded, no network, no database: the env is pure numpy plus config, so every
fixture builds from a real circuit in the default configs. The module seed is
distinct from the physics suites (99 in fits, 271 in synth) so a cross-suite
coincidence cannot hide a bug (5.5.5).
"""

import numpy as np
import pytest

from senna.env import F1RaceEnv

SEED = 512
CIRCUIT = "bahrain_grand_prix"  # a raced 2026 event with real fitted params in configs


@pytest.fixture
def rng():
    return np.random.default_rng(SEED)


@pytest.fixture
def make_env():
    """Build an F1RaceEnv from the default configs; override circuit/era per test."""

    def build(circuit: str = CIRCUIT, era: str = "2026") -> F1RaceEnv:
        return F1RaceEnv(circuit, era)

    return build


@pytest.fixture
def env(make_env):
    return make_env()
