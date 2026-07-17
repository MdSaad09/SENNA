"""Transition-dynamics helpers (5.5.3): the tyre and energy terms in closed
form, and the SOC clip that keeps the store inside [0, 4] MJ (E-01).
"""

import numpy as np
import pytest

from senna.env.dynamics import derate_penalty_s, grip_est, tyre_deg_s
from tests.env.conftest import SEED

USABLE_SOC_MJ = 4.0


def test_tyre_degradation_follows_the_power_law():
    # deg = a * t0 * age**b (T5)
    assert tyre_deg_s(90.0, 0.01, 1.3, 5.0) == pytest.approx(0.01 * 90.0 * 5.0**1.3)

    ages = np.array([1.0, 4.0, 9.0])
    expected = 0.012 * 88.0 * ages**1.217
    assert tyre_deg_s(88.0, 0.012, 1.217, ages) == pytest.approx(expected)


def test_grip_estimate_stays_inside_the_unit_interval():
    assert grip_est(0.01, 1.3, 5.0) == pytest.approx(np.clip(1 - 0.01 * 5.0**1.3, 0, 1))
    assert grip_est(0.01, 1.3, 0.0) == pytest.approx(1.0)  # a fresh tyre has full grip
    assert grip_est(1.0, 1.0, 100.0) == 0.0  # a worn tyre floors at zero, never negative


def test_the_derate_penalty_prices_only_the_deployment_shortfall():
    # p_der * max(0, requested - delivered); zero whenever supply meets the request
    assert derate_penalty_s(5.0, 3.0, 0.8368) == pytest.approx(0.8368 * 2.0)
    assert derate_penalty_s(3.0, 5.0, 0.8368) == 0.0
    assert derate_penalty_s(3.0, 3.0, 0.8368) == 0.0

    requests = np.array([5.0, 2.0, 4.0])
    delivered = np.array([3.0, 2.0, 1.0])
    expected = 0.8 * np.array([2.0, 0.0, 3.0])
    assert derate_penalty_s(requests, delivered, 0.8) == pytest.approx(expected)


def test_sustained_attack_never_pushes_soc_out_of_bounds(env):
    # E-01: deploying hard drains the store, but the clip holds it in [0, 4]
    obs, info = env.reset(seed=SEED)
    soc_before = info["energy"]["soc_mj"]

    for _ in range(env.total_laps):
        obs, reward, terminated, truncated, info = env.step(np.array([0, 2]))  # attack
        energy = info["energy"]
        soc_after = energy["soc_mj"]
        assert -1e-9 <= soc_after <= USABLE_SOC_MJ + 1e-9

        # away from the clip edges the store obeys SOC' = SOC + harvest - deploy
        if 1e-6 < soc_after < USABLE_SOC_MJ - 1e-6:
            assert soc_after - soc_before == pytest.approx(
                energy["harvest_mj"] - energy["deploy_mj"], abs=1e-9
            )
        soc_before = soc_after
        if terminated:
            break
