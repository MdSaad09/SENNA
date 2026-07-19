"""The F07 stage-env toggles (spec 5.7). Stage A trains on a solo, dry, hazard-free
circuit; Stage B keeps SC/VSC but bans the red flag (E-03/E-04); the defaults must
reproduce today's env bit for bit, with no RNG draw added or removed. The solo reward
divergence — pace priced on the full lap including pit time — is the approved F07
decision 1, pinned here so Stage A can never learn that stops are free.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from senna.env import F1RaceEnv
from senna.env.twin import EventTrace
from tests.env.conftest import CIRCUIT, SEED

ERA = "2026"
STALL = [0, 1]  # stay out, balanced — the do-nothing lap

# one env per toggle combo, reused across hypothesis examples: reset() reseeds every
# stream (5.5.5), and rebuilding per example would put 30 yaml parses in the fast suite
_ENV_CACHE = {}


def _toggled_env(**toggles):
    key = tuple(sorted(toggles.items()))
    if key not in _ENV_CACHE:
        _ENV_CACHE[key] = F1RaceEnv(CIRCUIT, ERA, **toggles)
    return _ENV_CACHE[key]


def _run_race(env, seed, max_steps=250):
    """Stall to the flag; returns the per-lap infos (reset info first) and summed reward."""
    _, info = env.reset(seed=seed)
    infos, total_reward = [info], 0.0
    for _ in range(max_steps):
        _, reward, terminated, _, info = env.step(np.array(STALL))
        infos.append(info)
        total_reward += float(reward)
        if terminated:
            break
    return infos, total_reward


def _first_forced_pit_lap(env, seed) -> int:
    infos, _ = _run_race(env, seed)
    return next(info["lap"] for info in infos if info["events"]["forced_pit"])


def test_default_env_is_unchanged_by_the_new_kwargs():
    default = F1RaceEnv(CIRCUIT, ERA)
    explicit = F1RaceEnv(CIRCUIT, ERA, solo=False, weather="markov", hazards="full")
    assert default.n_cars == 22
    assert explicit.n_cars == 22

    obs_default, _ = default.reset(seed=SEED)
    obs_explicit, _ = explicit.reset(seed=SEED)
    assert np.array_equal(obs_default, obs_explicit)
    for _ in range(default.total_laps):
        obs_default, _, done_default, _, _ = default.step(np.array(STALL))
        obs_explicit, _, done_explicit, _, _ = explicit.step(np.array(STALL))
        assert np.array_equal(obs_default, obs_explicit)
        assert done_default == done_explicit
        if done_default:
            break

    # and the default path still rolls weather and hazards — pins against silent drift
    weathers, statuses = set(), set()
    for seed in range(SEED, SEED + 10):
        infos, _ = _run_race(default, seed)
        weathers |= {info["events"]["weather"] for info in infos}
        statuses |= {info["track_status"] for info in infos}
    assert weathers != {"dry"}
    assert statuses != {"green"}


def test_solo_env_runs_one_car_to_the_flag():
    env = F1RaceEnv(CIRCUIT, ERA, solo=True)
    assert env.n_cars == 1

    obs, info = env.reset(seed=SEED)
    terminated = False
    for _ in range(env.total_laps + 5):
        assert np.all(np.isfinite(obs))
        assert np.all(np.abs(obs) <= 1.0)  # a field of one must not blow up the gap slots
        obs, _, terminated, _, info = env.step(np.array(STALL))
        if terminated:
            break

    assert terminated
    assert info["final_position"] == 1
    assert not info["dnf"]


@pytest.mark.property
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=30, deadline=None)
def test_dry_env_never_leaves_dry(seed):
    infos, _ = _run_race(_toggled_env(weather="dry"), seed)
    for info in infos:
        assert info["events"]["weather"] == "dry"
        assert info["events"]["wetness"] == 0.0


@pytest.mark.property
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=30, deadline=None)
def test_no_hazards_env_stays_green_all_race(seed):
    infos, _ = _run_race(_toggled_env(hazards="none"), seed)
    for info in infos:
        assert info["track_status"] == "green"
        assert not info["events"]["red_flag"]


def test_no_hazards_tyre_failure_is_a_hard_cap():
    capped = F1RaceEnv(CIRCUIT, ERA, solo=True, weather="dry", hazards="none")
    forced_lap = _first_forced_pit_lap(capped, SEED)
    for seed in (SEED + 1, SEED + 2):
        assert _first_forced_pit_lap(capped, seed) == forced_lap  # age cap, not a hazard roll

    # "none" swaps the hazard for the twin's deterministic ego rule, so the two agree
    trace = EventTrace.green(
        CIRCUIT, ERA, capped.total_laps, 1, grid=np.array([1]), driver_s=np.zeros(1)
    )
    twin = F1RaceEnv(CIRCUIT, ERA, solo=True, twin=trace)
    assert _first_forced_pit_lap(twin, SEED) == forced_lap

    cliff = capped.scenario.deg_max_age["MEDIUM"]
    margin = capped.scenario.env["tyre_failure"]["cliff_age_margin_laps"]
    assert forced_lap > cliff + margin  # the cap only engages past the fitted cliff


@pytest.mark.slow
def test_sc_vsc_hazards_never_raise_a_red_flag():
    # british carries a real fitted red-flag lambda, so silence over 40 races is signal
    env = F1RaceEnv("british_grand_prix", ERA, hazards="sc_vsc")
    statuses = set()
    for seed in range(SEED, SEED + 40):
        infos, _ = _run_race(env, seed)
        for info in infos:
            assert info["track_status"] != "red"
            assert not info["events"]["red_flag"]
        statuses |= {info["track_status"] for info in infos}
    assert {"sc", "vsc"} <= statuses  # the neutralisations still roll — only the red is off


def test_solo_reward_pace_term_prices_the_pit_stop():
    stop_env = F1RaceEnv(CIRCUIT, ERA, solo=True, weather="dry", hazards="none")
    stay_env = F1RaceEnv(CIRCUIT, ERA, solo=True, weather="dry", hazards="none")

    def summed_reward(env, actions):
        env.reset(seed=SEED)
        total = 0.0
        for action in actions:
            _, reward, _, _, _ = env.step(np.array(action))
            total += float(reward)
        return total

    # identical laps except the last, where one run boxes for HARD: the RNG streams only
    # diverge at the pit-service draw, so the return difference is exactly the priced stop
    laps_out = [STALL] * 10
    total_stop = summed_reward(stop_env, [*laps_out, [3, 1]])
    total_stay = summed_reward(stay_env, [*laps_out, STALL])

    scenario = stop_env.scenario
    w_p = scenario.env["reward"]["pace_weight_w_p"]
    priced = w_p * scenario.pit_loss_mean_s / scenario.s_ref_s
    # the realised service is a single N(mean, sigma) draw floored at min service: 4 sigma
    tolerance = w_p * 4.0 * scenario.pit_loss_sigma_s / scenario.s_ref_s
    assert total_stay - total_stop == pytest.approx(priced, abs=tolerance)


def test_a_mismatched_twin_is_refused():
    scenario = F1RaceEnv(CIRCUIT, ERA).scenario
    grid = np.arange(1, scenario.grid_size + 1)

    full_field = EventTrace.green(CIRCUIT, ERA, scenario.total_laps, scenario.grid_size, grid=grid)
    with pytest.raises(ValueError):
        F1RaceEnv(CIRCUIT, ERA, solo=True, twin=full_field)  # a 22-car trace, a 1-car env

    short = EventTrace.green(CIRCUIT, ERA, scenario.total_laps - 5, scenario.grid_size, grid=grid)
    with pytest.raises(ValueError):
        F1RaceEnv(CIRCUIT, ERA, twin=short)  # the lap count disagrees with the circuit
