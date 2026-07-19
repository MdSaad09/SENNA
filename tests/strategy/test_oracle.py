"""The full-information DP oracle (A-05, M3) and its parts. Stage 1 costs every stint on
a deterministic trace with exact per-compound tables and enumerates the 1..max_stops
plans; stage 2 re-scores the best of those plus any injected baseline plans by full twin
rolls and returns the winner. The greedy energy rule it leans on is validated against the
env's own dynamics, so the oracle never drifts from the physics it optimises.

The exact-cell check runs on a green solo trace: one car means no traffic and no pit
FIFO, so a stint cost reduces to the joint lap-time model summed lap by lap.
"""

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from senna import config
from senna.env import dynamics
from senna.env.events import DRY
from senna.env.masks import build_mask
from senna.env.scenario import compound_code
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.oracle import enumerate_plans, solo_reference, solve_oracle, stint_cost_table
from senna.strategy.plans import PitPlan, greedy_mode
from senna.strategy.random_legal import RandomLegal
from senna.strategy.replay import RealStrategyReplay
from senna.strategy.rollout import run_episode
from tests.strategy.conftest import SEED


def _small_oracle_cfg(max_stops=2, top_k=3):
    cfg = dict(config.load("baselines")["oracle"])
    cfg["max_stops"] = max_stops
    cfg["top_k_rolls"] = top_k
    return cfg


def _mode_price_s(mode, soc_mj, track_status, scenario):
    """Pace plus derate that mode buys this lap, straight from the env dynamics."""
    modes = np.array([mode])
    harvest = np.array([dynamics.per_lap_harvest_mj(scenario, track_status)])
    request = dynamics.deploy_request_mj(modes, scenario)
    delivered, derate, _ = dynamics.resolve_energy(
        np.array([soc_mj]), harvest, request, scenario
    )
    pace = dynamics.mode_pace_s(modes, delivered, request, scenario)
    return float(pace[0] + derate[0])


def test_the_stint_table_matches_an_independent_hand_computation(make_env):
    env = make_env()
    scenario = env.scenario
    n = env.total_laps
    from senna.env.twin import EventTrace

    trace = EventTrace.green(
        env.circuit, env.era, n, 1, grid=np.array([1]), driver_s=np.zeros(1)
    )
    table = stint_cost_table(scenario, trace, compound_code("MEDIUM"))
    assert table.shape == (n + 1, n + 1)

    base_burn_kg = scenario.race_fuel_kg / n
    offset_s = scenario.compound_offset_s["MEDIUM"]
    a, b = scenario.deg_a["MEDIUM"], scenario.deg_b["MEDIUM"]

    def fuel_kg_at(lap):
        return scenario.race_fuel_kg - (lap - 1) * base_burn_kg

    # a fresh single lap: age 0 (no deg), balanced pace (0), no traffic/wet/noise/driver
    expected_lap1_s = scenario.t0_s + offset_s + scenario.k_m_s_per_kg * fuel_kg_at(1)
    assert table[1, 1] == pytest.approx(expected_lap1_s, rel=1e-6)

    # extending the stint by one lap adds lap 2 at tyre age 1 and one lap of burnt fuel
    deg_age1_s = a * scenario.t0_s * 1.0**b
    expected_lap2_s = (
        scenario.t0_s + offset_s + deg_age1_s + scenario.k_m_s_per_kg * fuel_kg_at(2)
    )
    assert table[1, 2] - table[1, 1] == pytest.approx(expected_lap2_s, rel=1e-6)

    # a longer stint always costs more than a shorter one from the same start
    for l2 in range(2, 12):
        assert table[1, l2] > table[1, l2 - 1]


@pytest.mark.slow
def test_the_oracle_beats_or_ties_every_baseline_on_a_deterministic_toy_race(
    make_env, scenario, green_trace
):
    baselines = {
        "heuristic": EngineerHeuristic(scenario, config.load("baselines")["heuristic"]),
        "random": RandomLegal(),
        "replay": RealStrategyReplay(
            PitPlan(stops=((28, "HARD"),)), scenario, config.load("baselines")["replay"]
        ),
    }

    realised = {}
    for name, policy in baselines.items():
        realised[name] = run_episode(make_env(twin=green_trace), policy, seed=SEED)

    realised_plans = tuple(
        PitPlan(stops=tuple(zip(r.pit_laps, r.compounds, strict=True)))
        for r in realised.values()
    )
    oracle = solve_oracle(
        scenario, green_trace, cfg=_small_oracle_cfg(), baselines=realised_plans
    )

    for name, result in realised.items():
        assert oracle.race_time_s <= result.race_time_s + 1e-6, f"oracle lost to {name}"


def test_every_enumerated_plan_honours_the_two_compound_rule_and_the_stop_cap(
    scenario, green_trace
):
    max_stops = 2
    plans = enumerate_plans(scenario, green_trace, max_stops)
    assert plans

    cliff = scenario.env["tyre_failure"]["cliff_age_margin_laps"]
    age_fallback = scenario.env["obs"]["tyre_age_norm_laps"]
    for plan in plans:
        laps = [lap for lap, _ in plan.stops]
        assert laps == sorted(set(laps))  # stop laps strictly increasing
        assert len(plan.stops) <= max_stops  # the stop cap
        compounds_run = {"MEDIUM"} | {compound for _, compound in plan.stops}
        assert len(compounds_run) >= 2  # F-20: two distinct compounds, MEDIUM start included

        # no stint banks on a forced failure: every segment stays inside its compound's cliff
        boundaries = [1, *laps, scenario.total_laps + 1]
        segments = ["MEDIUM", *[compound for _, compound in plan.stops]]
        for start, end, name in zip(boundaries[:-1], boundaries[1:], segments, strict=True):
            max_age_in_stint = (end - start) - 1
            assert max_age_in_stint <= scenario.deg_max_age.get(name, age_fallback) + cliff


@pytest.mark.slow
def test_the_oracle_winner_honours_the_two_compound_rule_and_the_stop_cap(scenario, green_trace):
    cfg = _small_oracle_cfg()
    oracle = solve_oracle(scenario, green_trace, cfg=cfg)

    assert len(oracle.plan.stops) <= cfg["max_stops"]
    compounds_run = {"MEDIUM"} | {compound for _, compound in oracle.plan.stops}
    assert len(compounds_run) >= 2  # F-20: two distinct compounds, MEDIUM start included


@pytest.mark.property
@given(
    soc_mj=st.floats(min_value=0.0, max_value=4.0, allow_nan=False, allow_infinity=False),
    status_name=st.sampled_from(["green", "vsc", "sc"]),
)
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_the_greedy_energy_rule_never_picks_a_worse_priced_mode(
    scenario, soc_mj, status_name
):
    track_status = {"green": dynamics.GREEN, "vsc": dynamics.VSC, "sc": dynamics.SC}[
        status_name
    ]
    mask = build_mask(
        pit_open=True,
        weather=DRY,
        wetness=0.0,
        soc_mj=soc_mj,
        lap=10,
        total_laps=scenario.total_laps,
        second_compound_used=True,
        attack_soc_floor_mj=scenario.attack_soc_floor_mj,
        validity=scenario.env["compound_validity"],
    ).flat()

    chosen = greedy_mode(soc_mj, track_status, mask, scenario)
    legal_modes = [mode for mode in range(4) if mask[6 + mode]]

    assert chosen in legal_modes
    best_price_s = min(_mode_price_s(m, soc_mj, track_status, scenario) for m in legal_modes)
    assert _mode_price_s(chosen, soc_mj, track_status, scenario) <= best_price_s + 1e-9


def test_the_oracle_refuses_a_wet_trace(scenario, green_trace):
    # slick-only enumeration cannot price the rain; scoring it would be meaningless (M3),
    # so the oracle refuses rather than return a wrong ceiling (the wet extension is F14)
    green_trace.wetness[20:] = 0.9
    with pytest.raises(NotImplementedError):
        solve_oracle(scenario, green_trace, cfg=_small_oracle_cfg())


def test_the_solo_reference_is_deterministic_across_calls(scenario):
    cfg = _small_oracle_cfg(max_stops=1)
    plan_a, time_a = solo_reference(scenario, cfg=cfg)
    plan_b, time_b = solo_reference(scenario, cfg=cfg)

    assert plan_a == plan_b
    assert time_a == pytest.approx(time_b)
