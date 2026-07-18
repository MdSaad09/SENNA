"""A full race end to end (5.5.5, A-10). A 22-car 2026 race runs from reset to
terminated in the scheduled distance, the 2024 era runs the same code path, the
info dict carries the mask and reward decomposition every step, and nothing
pandas-shaped is reachable from the hot loop.
"""

import subprocess
import sys

import numpy as np

from tests.env.conftest import SEED


# balanced most of the way, one mid-race stop to satisfy the two-compound rule (F-20)
def _policy(lap):
    return np.array([2, 1]) if lap == 15 else np.array([0, 1])


def _drive_to_flag(env):
    obs, info = env.reset(seed=SEED)
    steps = 0
    while True:
        assert env.observation_space.contains(obs)
        assert len(info["mask"]["pit"]) == 6
        assert len(info["mask"]["mode"]) == 4
        assert isinstance(info["mask"]["reasons"], dict)
        assert set(info["reward_terms"]) >= {"pace", "position", "terminal", "total"}

        obs, reward, terminated, truncated, info = env.step(_policy(info["lap"]))
        steps += 1
        assert truncated is False
        if terminated:
            return steps, info


def test_a_2026_race_runs_to_the_flag_and_reports_a_result(env):
    steps, info = _drive_to_flag(env)

    assert steps <= env.total_laps
    assert 1 <= info["final_position"] <= env.n_cars
    assert isinstance(info["dnf"], bool)
    assert "points" in info
    assert "pit_laps" in info and "compounds" in info
    assert "derate_count" in info
    assert "energy_totals" in info


def test_a_classified_finisher_of_a_green_race_scores_points(make_env):
    # regression: fuel burns to ~0 at the flag, so crossing the line must not read as a DNF.
    # Suzuka's 53-lap distance lands fuel on exactly zero — the case that mis-scored the winner.
    env = make_env(circuit="japanese_grand_prix")
    obs, info = env.reset(seed=SEED)
    terminated = False
    while not terminated:
        obs, reward, terminated, truncated, info = env.step(_policy(info["lap"]))

    assert info["dnf"] is False
    assert info["final_position"] <= env.n_cars
    if info["final_position"] <= len(env.scenario.env["reward"]["points_2026"]):
        assert info["points"] > 0.0


def test_a_2024_era_race_runs_on_the_same_code_path(make_env):
    # A-10: the era switch is one code path over two constant files
    env = make_env(era="2024")
    steps, info = _drive_to_flag(env)

    assert steps <= env.total_laps
    assert 1 <= info["final_position"] <= env.n_cars


def test_the_env_module_pulls_in_no_pandas():
    # the 5.6.2 throughput gate depends on nothing pandas-shaped in the hot loop;
    # a clean subprocess proves senna.env never imports it
    probe = (
        "import sys, senna.env; "
        "leaked = sorted(m for m in sys.modules if 'pandas' in m); "
        "assert not leaked, leaked"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
