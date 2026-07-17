"""The three-term reward (5.5.4): scale-free pace shaping, potential-based
position shaping that telescopes to zero (F-15), and terminal championship
points over 2.5. All three appear separately in the per-step decomposition.
"""

import numpy as np
import pytest

from senna.env.reward import (
    RewardTerms,
    pace_shaping,
    position_potential,
    shaping_step,
    terminal_points,
)
from tests.env.conftest import SEED

POINTS_2026 = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
DIVISOR = 2.5
COEF = 0.1


def test_pace_shaping_rewards_beating_the_reference_lap():
    # w_p * (t_ref - lap_time) / s_ref
    assert pace_shaping(90.0, 91.0, 2.0, 0.02) == pytest.approx(0.02 * 1.0 / 2.0)
    # a slower-than-reference lap costs pace
    assert pace_shaping(92.0, 91.0, 2.0, 0.02) < 0.0


def test_the_position_potential_is_minus_coefficient_times_place():
    assert position_potential(1, COEF) == pytest.approx(-0.1)
    assert position_potential(4, COEF) == pytest.approx(-0.4)


def test_position_shaping_nets_exactly_zero_over_a_closed_loop():
    # F-15: the oscillation exploit that broke v2 pays nothing back
    places = [3, 5, 2, 7, 4, 3]  # starts and ends on P3
    total = sum(
        shaping_step(prev, nxt, COEF, gamma=1.0)
        for prev, nxt in zip(places, places[1:])
    )
    assert total == pytest.approx(0.0, abs=1e-9)


def test_a_single_place_gained_is_worth_the_coefficient():
    # telescoping means one net place is +0.1 regardless of the path taken
    assert shaping_step(5, 4, COEF, gamma=1.0) == pytest.approx(0.1)
    assert shaping_step(4, 5, COEF, gamma=1.0) == pytest.approx(-0.1)


def test_the_terminal_points_table_maps_places_to_scaled_points():
    assert terminal_points(1, POINTS_2026, DIVISOR, dnf=False) == pytest.approx(10.0)
    assert terminal_points(10, POINTS_2026, DIVISOR, dnf=False) == pytest.approx(0.4)
    assert terminal_points(11, POINTS_2026, DIVISOR, dnf=False) == 0.0
    # DNF forfeits everything rather than paying a negative penalty (documented choice)
    assert terminal_points(1, POINTS_2026, DIVISOR, dnf=True) == 0.0


def test_the_reward_decomposition_carries_three_separate_terms(env):
    obs, info = env.reset(seed=SEED)
    obs, reward, terminated, truncated, info = env.step(np.array([0, 1]))

    terms = info["reward_terms"]
    assert set(terms) >= {"pace", "position", "terminal", "total"}
    assert terms["total"] == pytest.approx(
        terms["pace"] + terms["position"] + terms["terminal"], abs=1e-9
    )
    assert reward == pytest.approx(terms["total"], abs=1e-9)


def test_reward_terms_dataclass_exposes_the_named_terms():
    terms = RewardTerms(pace=0.01, position=0.1, terminal=0.0, total=0.11)
    assert terms.pace == 0.01
    assert terms.position == 0.1
    assert terms.terminal == 0.0
    assert terms.total == pytest.approx(0.11)
