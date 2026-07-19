"""The engineer-heuristic baseline (A-07): a readable pit wall that finishes a legal
two-compound race, grabs the cheap stop under a safety car, and switches to wets when
the track crosses over (E-08). Its wetness thresholds come from env.yaml
compound_validity — the same source the action mask reads — never from its own config,
so the mask and the baseline can never disagree.

The behaviour tests run on the deterministic twin so the safety car and the rain appear
exactly where the test injects them. Bahrain 2026 MEDIUM degrades past the heuristic's
1.2 s trigger at about age 16, so a stop earlier than that is the injected event talking,
not the deg model.
"""

import pytest

from senna import config
from senna.env import events
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.rollout import run_episode
from tests.strategy.conftest import SEED


def _heuristic(scenario):
    return EngineerHeuristic(scenario, config.load("baselines")["heuristic"])


def test_the_engineer_heuristic_finishes_with_a_legal_two_compound_strategy(
    make_env, green_trace
):
    env = make_env(twin=green_trace)
    result = run_episode(env, _heuristic(env.scenario), seed=SEED)

    assert result.dnf is False
    assert len(result.pit_laps) >= 1
    # MEDIUM is the fixed start; the finish must have run at least one other compound (F-20)
    compounds_run = {"MEDIUM"} | set(result.compounds)
    assert len(compounds_run) >= 2


@pytest.mark.slow
def test_the_heuristic_takes_the_cheap_stop_inside_a_safety_car_window(
    make_env, green_trace
):
    sc_start = 10  # old enough to clear both the min-stint and SC age gates, before deg
    green_trace.status[sc_start - 1 : sc_start + 2] = events.SC  # a 3-lap neutralisation

    env = make_env(twin=green_trace)
    result = run_episode(env, _heuristic(env.scenario), seed=SEED)

    assert any(sc_start <= lap <= sc_start + 4 for lap in result.pit_laps)


def test_the_heuristic_fits_intermediates_when_the_track_wets(make_env, green_trace):
    wet_from = 12  # wetness climbs into the inter band [0.25, 0.75] and stays there
    green_trace.wetness[wet_from - 1 :] = 0.5
    green_trace.weather[wet_from - 1 :] = events.DAMP

    env = make_env(twin=green_trace)
    result = run_episode(env, _heuristic(env.scenario), seed=SEED)

    assert "INTERMEDIATE" in result.compounds


def test_every_heuristic_threshold_reads_from_baselines_yaml(scenario):
    cfg = config.load("baselines")["heuristic"]
    without_deg_trigger = {k: v for k, v in cfg.items() if k != "deg_pit_threshold_s"}
    # the deg trigger is a config value, not an inline constant: dropping it must be fatal
    with pytest.raises(KeyError):
        EngineerHeuristic(scenario, without_deg_trigger)


def test_the_heuristic_shops_only_from_the_circuit_s_fitted_compounds(make_env):
    # Suzuka's 2026 fit carries no SOFT: the compound wheel must not target it, and
    # the deg trigger must not index a curve that does not exist (the F07 Stage B
    # recording crash — every earlier test ran Bahrain, which fits all three slicks)
    env = make_env(circuit="japanese_grand_prix")
    assert "SOFT" not in env.scenario.available_compounds

    result = run_episode(env, _heuristic(env.scenario), seed=SEED)
    assert not result.dnf
    assert set(result.compounds) <= set(env.scenario.available_compounds)
