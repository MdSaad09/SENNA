"""The 32-dim ego observation (5.5.1). Every dimension is scale-bounded to
[-1, 1], the one-hot groups are exclusive, and the named formulas hold against
the info dict the same step reports.
"""

import numpy as np
import pytest

from tests.env.conftest import SEED

# 0-indexed slices of the 1-indexed 5.5.1 table
COMPOUND_ONE_HOT = slice(3, 8)  # #4-8
STATUS_ONE_HOT = slice(23, 26)  # #24-26 green / VSC / SC
WEATHER_ONE_HOT = slice(27, 30)  # #28-30 dry / damp / wet
SOC_FRAC = 14  # #15
LAP_PROGRESS = 0  # #1
OVERRIDE_AVAILABLE = 22  # #23
USABLE_SOC_MJ = 4.0


def _walk(env, laps=6):
    """Reset then take a few balanced stay-out laps, yielding (obs, info) each."""
    obs, info = env.reset(seed=SEED)
    yield obs, info
    for _ in range(laps):
        obs, reward, terminated, truncated, info = env.step(np.array([0, 1]))
        yield obs, info
        if terminated:
            return


def test_the_observation_matches_the_declared_box(env):
    obs, info = env.reset(seed=SEED)

    assert obs.shape == (32,)
    assert obs.dtype == np.float32
    assert env.observation_space.contains(obs)
    assert np.all(obs >= -1.0)
    assert np.all(obs <= 1.0)


def test_the_one_hot_groups_each_select_exactly_one_state(env):
    # E-03: green / VSC / SC are separate track states, never collapsed into one flag
    for obs, _ in _walk(env):
        assert obs[COMPOUND_ONE_HOT].sum() == pytest.approx(1.0)
        assert obs[STATUS_ONE_HOT].sum() == pytest.approx(1.0)
        assert obs[WEATHER_ONE_HOT].sum() == pytest.approx(1.0)


def test_soc_frac_reports_the_energy_store_as_a_fraction_of_four_megajoules(env):
    for obs, info in _walk(env):
        assert obs[SOC_FRAC] == pytest.approx(
            info["energy"]["soc_mj"] / USABLE_SOC_MJ, abs=1e-6
        )


def test_lap_progress_tracks_the_race_phase(env):
    for obs, info in _walk(env):
        assert obs[LAP_PROGRESS] == pytest.approx(info["lap"] / env.total_laps, abs=1e-6)


def test_override_available_flips_at_a_one_second_gap_ahead(env):
    # F-05: the 2026 overtaking aid needs a car ahead within 1.0 s
    for obs, info in _walk(env, laps=12):
        if info["position"] == 1:
            continue  # a leader has no car ahead to attack
        assert (obs[OVERRIDE_AVAILABLE] > 0.5) == (info["gap_ahead_s"] <= 1.0)
