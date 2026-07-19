"""The F08 env variants (spec 5.6.3, F-16). `constraints="penalty"` reproduces v2's
compliance architecture — illegal requests execute, are counted under the mask's
reason codes and fined, while SOC clipping and energy conservation never relax
(E-01) — and `reward_mode` swaps the objective for the ablation arms. The defaults
must reproduce the standing env bit for bit: the variants exist to be measured
against it.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from senna import config
from senna.env import F1RaceEnv
from senna.env.events import DAMP
from senna.env.reward import terminal_points
from tests.env.conftest import CIRCUIT, SEED

ERA = "2026"
STALL = [0, 1]  # stay out, balanced — the do-nothing lap
USABLE_SOC_MJ = 4.0

# one penalty env reused across hypothesis examples: reset() reseeds every stream
# (5.5.5), and a rebuild per example would put 20 yaml parses in the property run
_penalty_envs = []


def _penalty_env():
    if not _penalty_envs:
        _penalty_envs.append(F1RaceEnv(CIRCUIT, ERA, constraints="penalty"))
    return _penalty_envs[0]


def _legal_action(env, rng):
    flat = env.action_masks()
    return np.array([rng.choice(np.flatnonzero(flat[:6])),
                     rng.choice(np.flatnonzero(flat[6:]))])


def _stall_to_flag(env):
    """Step (0, 1) from a seeded reset to the flag; returns the terminal info."""
    _, info = env.reset(seed=SEED)
    for _ in range(env.total_laps + 5):
        _, _, terminated, _, info = env.step(np.array(STALL))
        if terminated:
            return info
    raise AssertionError("race never reached the flag")


def test_default_env_is_unchanged_by_the_variant_kwargs():
    default = F1RaceEnv(CIRCUIT, ERA)
    explicit = F1RaceEnv(CIRCUIT, ERA, constraints="mask", reward_mode="v3")

    obs_default, _ = default.reset(seed=SEED)
    obs_explicit, _ = explicit.reset(seed=SEED)
    assert np.array_equal(obs_default, obs_explicit)

    for _ in range(default.total_laps):
        obs_d, reward_d, done_d, _, info_d = default.step(np.array(STALL))
        obs_e, reward_e, done_e, _, info_e = explicit.step(np.array(STALL))
        assert np.array_equal(obs_d, obs_e)
        assert reward_d == reward_e
        assert info_d["position"] == info_e["position"]
        assert done_d == done_e
        if done_d:
            break


def test_variant_kwargs_are_validated():
    with pytest.raises(ValueError, match="mask"):
        F1RaceEnv(CIRCUIT, ERA, constraints="penalise")
    with pytest.raises(ValueError, match="v3"):
        F1RaceEnv(CIRCUIT, ERA, reward_mode="v1")


def test_penalty_env_reports_every_action_legal():
    env = F1RaceEnv(CIRCUIT, ERA, constraints="penalty")
    env.reset(seed=SEED)

    assert env.action_masks().shape == (10,)
    assert env.action_masks().all()
    for _ in range(3):
        env.step(np.array(STALL))
        assert env.action_masks().all()


def test_penalty_env_permits_and_fines_a_two_compound_breach():
    # a dry solo race that never stops breaches the two-compound rule on its last lap
    # deterministically — the "otherwise ablation 2 measures nothing" pin (5.6.3 row 2)
    penalty = F1RaceEnv(CIRCUIT, ERA, solo=True, weather="dry", hazards="none",
                        constraints="penalty")
    info = _stall_to_flag(penalty)

    assert info["violations"] == {"two_compound_rule": 1}
    assert info["reward_terms"]["violation_penalty"] == -8.0
    assert info["pit_laps"] == []  # the stay-out executed: the race finished in breach

    masked = F1RaceEnv(CIRCUIT, ERA, solo=True, weather="dry", hazards="none")
    info = _stall_to_flag(masked)
    assert info["pit_laps"]  # under masking the same drive is coerced into the stop


def test_penalty_env_counts_a_wet_rule_pit():
    env = F1RaceEnv(CIRCUIT, ERA, constraints="penalty")
    env.reset(seed=SEED)
    # white-box: a damp track where every slick is weather-masked, mask rebuilt to match
    env._state.wetness = 0.5
    env._state.weather = DAMP
    env._mask = env._ego_mask()

    _, _, _, _, info = env.step(np.array([1, 1]))  # box for Soft against the wet rule

    assert info["violations"]["slick_above_wet_threshold"] == 1
    assert info["reward_terms"]["violation_penalty"] == -8.0
    assert env._ego_pit_compounds == ["SOFT"]  # the stop executed, priced by the physics


def test_penalty_env_still_coerces_an_unfitted_compound():
    # Suzuka has no SOFT fit — a data limit, not a sporting rule v2 ever penalised, so
    # the coercion holds in every constraints mode and no violation is counted
    env = F1RaceEnv("japanese_grand_prix", ERA, constraints="penalty")
    env.reset(seed=SEED)

    _, _, _, _, info = env.step(np.array([1, 1]))  # ask for the unfitted Soft

    assert info["violations"] == {}
    assert "SOFT" not in env._ego_pit_compounds


def test_penalty_env_counts_an_attack_below_the_soc_floor():
    env = F1RaceEnv(CIRCUIT, ERA, constraints="penalty")
    env.reset(seed=SEED)
    env._state.soc_mj[0] = 0.0  # white-box: drain the ego's store below the floor
    env._mask = env._ego_mask()

    _, _, _, _, info = env.step(np.array([0, 2]))  # stay out, attack on an empty store

    assert info["violations"]["soc_below_attack_floor"] == 1
    assert info["reward_terms"]["violation_penalty"] == -8.0
    # the request executed, but the physics still derated it (E-01 untouched)
    assert info["energy"]["deploy_mj"] < env.scenario.e_dep_mj


@pytest.mark.property
@pytest.mark.slow
@given(base_seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=20, deadline=None)
def test_penalty_env_still_clips_soc_and_conserves_energy(base_seed):
    # E-01 under raw actions the mask never filtered: only discrete legality changed
    # architecture in penalty mode, never conservation
    env = _penalty_env()
    rng = np.random.default_rng(base_seed)

    _, info = env.reset(seed=int(rng.integers(0, 2**31)))
    terminated = False
    while not terminated:
        action = np.array([rng.integers(0, 6), rng.integers(0, 4)])
        soc_before = info["energy"]["soc_mj"]
        _, _, terminated, _, info = env.step(action)
        energy = info["energy"]
        soc_after = energy["soc_mj"]

        assert -1e-9 <= soc_after <= USABLE_SOC_MJ + 1e-9
        if 1e-6 < soc_after < USABLE_SOC_MJ - 1e-6:
            assert soc_after - soc_before == pytest.approx(
                energy["harvest_mj"] - energy["deploy_mj"], abs=1e-9
            )


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"reward_mode": "terminal_only"}, {"reward_mode": "v2"},
     {"constraints": "penalty"}],
    ids=["default", "terminal_only", "v2", "penalty"],
)
def test_reward_decomposition_sums_to_total_in_every_mode(kwargs):
    env = F1RaceEnv(CIRCUIT, ERA, **kwargs)
    env.reset(seed=SEED)
    rng = np.random.default_rng(SEED)

    for _ in range(10):
        _, reward, terminated, _, info = env.step(_legal_action(env, rng))
        terms = info["reward_terms"]
        assert sum(v for k, v in terms.items() if k != "total") == pytest.approx(terms["total"])
        assert float(reward) == terms["total"]
        if terminated:
            break


def test_terminal_only_reward_is_zero_until_the_flag():
    env = F1RaceEnv(CIRCUIT, ERA, solo=True, weather="dry", hazards="none",
                    reward_mode="terminal_only")
    env.reset(seed=SEED)

    rewards = []
    for _ in range(env.total_laps + 5):
        _, reward, terminated, _, info = env.step(np.array(STALL))
        rewards.append(float(reward))
        if terminated:
            break

    assert terminated
    assert rewards[:-1] == [0.0] * (len(rewards) - 1)
    # both shaping terms are reported, held at zero — the decomposition contract
    assert info["reward_terms"]["pace"] == 0.0
    assert info["reward_terms"]["position"] == 0.0

    # the terminal term is exactly v3's, from the same 2026 points table over 2.5
    reward_cfg = config.load("env")["reward"]
    assert rewards[-1] == terminal_points(
        info["final_position"], reward_cfg["points_2026"], reward_cfg["points_divisor"],
        dnf=info["dnf"],
    )
