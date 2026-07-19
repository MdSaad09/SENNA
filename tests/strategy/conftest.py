"""Shared fixtures for the F06 strategy suite: the scripted baselines, the DP oracle
and their rollouts. Seed 704 keeps this suite apart from env (512), fits (99) and synth
(271), so a cross-suite coincidence cannot mask a bug (5.5.5). No network, no database —
every rollout runs on the pure-numpy env and its deterministic twin.
"""

import numpy as np
import pytest

from senna.env import F1RaceEnv

SEED = 704
CIRCUIT = "bahrain_grand_prix"  # a raced 2026 event with real fitted params in configs


@pytest.fixture
def make_env():
    """Build an F1RaceEnv; forwards rival_band/record/twin so a test can pin a twin."""

    def build(circuit: str = CIRCUIT, era: str = "2026", **kwargs) -> F1RaceEnv:
        return F1RaceEnv(circuit, era, **kwargs)

    return build


@pytest.fixture
def env(make_env):
    return make_env()


@pytest.fixture
def scenario(env):
    return env.scenario


@pytest.fixture
def green_trace(env):
    """An all-green, dry deterministic twin sized to the fixture circuit, grid 1..n.

    EventTrace is part of F06's twin module; importing it inside the fixture rather than
    at module load keeps the rest of the suite collectable independently of it.
    """
    from senna.env.twin import EventTrace

    n = env.scenario.grid_size
    grid = np.arange(1, n + 1)
    return EventTrace.green(env.circuit, env.era, env.scenario.total_laps, n, grid=grid)
