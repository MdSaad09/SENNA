"""The reconstructed v2 reward (5.6.3 row 3): pure per-term functions checked against
the master spec's "v2 says" quotes (F-15, F-16, F-17, F-07, R-02), coefficients from
configs/ablations.yaml. Reproducing v2's known pathology — the +0.2 oscillation
pump — is the proof this is v2's reward and not a strawman.
"""

import numpy as np
import pytest

from senna import config
from senna.env import F1RaceEnv
from senna.env.reward_v2 import (
    ers_efficiency,
    ers_violation,
    fastest_lap_bonus,
    grip_stint_end,
    position_change,
    sc_pit_bonus,
    tyre_failure,
)
from tests.env.conftest import CIRCUIT, SEED

V2_TERMS = {
    "pace", "position_gain", "position_loss", "terminal", "sc_pit", "ers_efficiency",
    "grip_stint_end", "undercut", "ers_violation", "fuel", "tyre_failure",
    "fastest_lap", "total",
}


def test_v2_reward_terms_match_the_quoted_formulas():
    coefs = config.load("ablations")["reward_v2"]

    assert coefs["position_gain"] == 1.0         # F-15 "v2 says"
    assert coefs["position_loss"] == -0.8        # F-15 "v2 says"
    assert coefs["sc_pit_bonus"] == 2.5          # F-17 "v2 says"
    assert coefs["ers_efficiency_coef"] == 0.1   # F-17 "v2 says"
    assert coefs["grip_stint_end_coef"] == 0.2   # F-17 "v2 says"
    assert coefs["undercut_bonus"] == 0.5        # F-17 "v2 says"
    assert coefs["ers_violation_penalty"] == -8.0  # F-16 "v2 says"
    assert coefs["tyre_failure_penalty"] == -12.0  # R-02
    assert coefs["fastest_lap_bonus"] == 1.0     # F-07 "v2 says"
    assert coefs["fuel_penalty"] == -5.0         # reconstructed — plan decision 1
    assert coefs["undercut_window_laps"] == 3    # reconstructed — plan decision 1

    gain, loss = coefs["position_gain"], coefs["position_loss"]
    assert position_change(6, 4, gain=gain, loss=loss) == (2.0, 0.0)
    assert position_change(4, 6, gain=gain, loss=loss) == (0.0, pytest.approx(-1.6))
    window = coefs["sc_pit_window_laps"]
    assert sc_pit_bonus(True, 2, bonus=2.5, window_laps=window) == 2.5
    assert sc_pit_bonus(True, 3, bonus=2.5, window_laps=window) == 0.0  # first two only
    assert sc_pit_bonus(False, 1, bonus=2.5, window_laps=window) == 0.0
    assert ers_efficiency(2.0, 4.0, coef=0.1) == pytest.approx(0.05)
    assert grip_stint_end(True, 0.8, coef=0.2) == pytest.approx(0.16)
    assert grip_stint_end(False, 0.8, coef=0.2) == 0.0
    assert ers_violation(0.5, penalty=-8.0) == -8.0  # fires whenever the lap derated
    assert ers_violation(0.0, penalty=-8.0) == 0.0
    assert tyre_failure(True, penalty=-12.0) == -12.0
    places = len(config.load("env")["reward"]["points_2026"])  # P1-P10, the real table
    assert fastest_lap_bonus(True, 3, bonus=1.0, points_places=places) == 1.0
    assert fastest_lap_bonus(True, 11, bonus=1.0, points_places=places) == 0.0


def test_v2_position_terms_pay_the_oscillation_pump():
    # F-15's exact pathology, reproduced on purpose: lose P4 and take it back, and v2
    # pays +0.2 for the round trip — the pump the potential-based v3 term telescopes away
    coefs = config.load("ablations")["reward_v2"]
    gain, loss = coefs["position_gain"], coefs["position_loss"]

    lost = position_change(4, 5, gain=gain, loss=loss)
    regained = position_change(5, 4, gain=gain, loss=loss)
    assert sum(lost) + sum(regained) == pytest.approx(0.2)


def test_v2_env_emits_the_twelve_terms():
    env = F1RaceEnv(CIRCUIT, "2026", reward_mode="v2")
    env.reset(seed=SEED)

    _, _, _, _, info = env.step(np.array([0, 1]))
    assert set(info["reward_terms"]) == V2_TERMS


def test_the_undercut_window_counts_full_laps_after_the_stop():
    # window 3 means judged once laps L+1..L+3 have run — the reading the yaml
    # provenance comment promises, so the off-by-one is pinned white-box
    window = config.load("ablations")["reward_v2"]["undercut_window_laps"]
    env = F1RaceEnv(CIRCUIT, "2026", reward_mode="v2")
    env.reset(seed=SEED)
    env._state.lap = 10
    env._undercut_check = None

    zeros = np.zeros(env.n_cars)
    facts = env._v2_lap_facts(2, np.zeros(env.n_cars, dtype=bool), zeros, zeros,
                              np.full(env.n_cars, 90.0), 3)
    assert facts["pitted"]
    assert env._undercut_check == (3, 10 + 1 + window)

    env._state.lap = 10 + window  # the last lap still inside the window
    assert env._undercut_resolved_ahead() is False
    assert env._undercut_check is not None

    env._state.lap = 10 + 1 + window  # the window closes: resolved and cleared
    rank = env._state.positions()
    assert env._undercut_resolved_ahead() == (int(rank[0]) < int(rank[3]))
    assert env._undercut_check is None
