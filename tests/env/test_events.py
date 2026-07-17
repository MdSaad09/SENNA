"""Event helpers and their env behaviour: the seeded weather chain (5.5.5), the
tyre-failure cliff (5.5.3), and the red-flag-as-event rule (E-04). Every
stochastic stream is fed an explicit rng — no module globals.
"""

import numpy as np
import pytest

from senna.config import get, load
from senna.env.events import advance_track_status, advance_weather, tyre_failure
from tests.env.conftest import SEED

MARKOV = get(load("env"), "weather.markov")
N_SECTORS = get(load("env"), "weather.n_sectors")
DRY, DAMP, WET = 0, 1, 2


def test_the_weather_step_is_reproducible_from_a_seed():
    # 5.5.5: the same rng state yields the same transition, for SubprocVecEnv statelessness
    first = advance_weather(DRY, 0.0, MARKOV, N_SECTORS, np.random.default_rng(SEED))
    second = advance_weather(DRY, 0.0, MARKOV, N_SECTORS, np.random.default_rng(SEED))

    assert first == second
    weather, wetness = first
    assert weather in (DRY, DAMP, WET)
    assert 0.0 <= wetness <= 1.0


def test_weather_holds_dry_when_the_chain_cannot_leave_dry():
    pinned = {"dry": [1.0, 0.0, 0.0], "damp": [0.0, 1.0, 0.0], "wet": [0.0, 0.0, 1.0]}
    for offset in range(20):
        weather, _ = advance_weather(
            DRY, 0.0, pinned, N_SECTORS, np.random.default_rng(SEED + offset)
        )
        assert weather == DRY


def test_a_tyre_never_fails_at_or_before_the_cliff():
    # always False while age <= max_age + cliff_margin, even at the maximum hazard
    for offset in range(50):
        rng = np.random.default_rng(SEED + offset)
        assert tyre_failure(10, 20, 3, 1.0, rng) is False
        assert tyre_failure(23, 20, 3, 1.0, rng) is False  # the boundary lap still holds


def test_a_tyre_can_fail_only_beyond_the_cliff():
    assert tyre_failure(24, 20, 3, 1.0, np.random.default_rng(SEED)) is True
    # a zero hazard never fires, cliff or not
    assert tyre_failure(24, 20, 3, 0.0, np.random.default_rng(SEED)) is False


def test_track_status_holds_green_when_no_hazard_fires():
    calm = {"sc": 0.0, "vsc": 0.0, "red": 0.0}
    assert advance_track_status(0, calm, np.random.default_rng(SEED)) == 0


def test_a_red_flag_is_an_event_and_never_a_termination(make_env):
    # E-04: a red flag neutralises the field and grants a free tyre change; the race
    # resumes, so it must appear as an event flag and never terminate the episode
    for seed in range(SEED, SEED + 8):
        env = make_env()
        obs, info = env.reset(seed=seed)
        terminated = False
        while not terminated:
            assert isinstance(info["events"]["red_flag"], bool)
            if info["events"]["red_flag"]:
                assert terminated is False
                assert any(info["mask"]["pit"][1:])  # a compound choice is offered
            obs, reward, terminated, truncated, info = env.step(np.array([0, 1]))
