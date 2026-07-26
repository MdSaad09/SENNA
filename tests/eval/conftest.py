"""Shared fixtures for the F14 evaluation suite: hand-built traces, scripted policies and
the tiny stores the report reads. Seed 1187 keeps this suite apart from fits (99), synth
(271), env (512), strategy (704) and train (846), so a cross-suite coincidence cannot mask
a bug (5.5.5).

Nothing here loads a checkpoint or opens a database. The metric arithmetic is separable
from the rollouts that feed it, and keeping it that way is what lets the M1 harness be
pinned on races whose answer is known by construction.
"""

import numpy as np
import pytest

from senna.env import F1RaceEnv

SEED = 1187
CIRCUIT = "bahrain_grand_prix"  # a raced 2026 event with real fitted params in configs


@pytest.fixture
def make_env():
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
    """An all-green, dry deterministic twin sized to the fixture circuit, grid 1..n."""
    from senna.env.twin import EventTrace

    n = env.scenario.grid_size
    return EventTrace.green(
        env.circuit, env.era, env.scenario.total_laps, n, grid=np.arange(1, n + 1)
    )


@pytest.fixture
def trace_with_sc(green_trace):
    """The green twin with one three-lap safety car, far enough into the race that a stop
    under it is a real strategic option rather than a start-phase artefact."""
    from senna.env import events

    trace = green_trace
    onset = trace.n_laps // 2
    trace.status[onset - 1 : onset + 2] = events.SC
    return trace


@pytest.fixture
def trace_with_vsc(green_trace):
    from senna.env import events

    trace = green_trace
    onset = trace.n_laps // 2
    trace.status[onset - 1 : onset + 1] = events.VSC
    return trace
