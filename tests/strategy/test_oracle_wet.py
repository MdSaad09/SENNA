"""The oracle's F14 wet extension (A-05, M3) and its status-aware stage-1 pit charge.

Three things are pinned. The dry path must not move: on a bone-dry trace the enumerator
and the Stage A solo reference return exactly what they return today, so wet legality
cannot leak into the number the F07 gate is measured against. On a wet trace the oracle
stops refusing, and every stop it enumerates carries a compound the mask would allow at
that stop's pit entry — the action for lap L is chosen against the mask built at the end
of lap L-1, so the wetness that decides legality is trace.wetness[L-2] (E-08). And stage 1
prices a stop taken under a neutralisation at the discounted pit loss (E-03) instead of
the flat pit_loss_mean_s it charges today, which quietly overstates every plan that boxes
under a safety car and so hands M3 a beatable ceiling.
"""

import numpy as np
import pytest

from senna import config
from senna.env import events
from senna.env.scenario import SLICKS, compound_code
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.oracle import (
    _plan_table_cost,
    enumerate_plans,
    solo_reference,
    solve_oracle,
    stint_cost_table,
)
from senna.strategy.plans import PitPlan, PlanPolicy
from senna.strategy.rollout import run_episode
from tests.strategy.conftest import SEED


def _oracle_cfg(max_stops, top_k):
    cfg = dict(config.load("baselines")["oracle"])
    cfg["max_stops"] = max_stops
    cfg["top_k_rolls"] = top_k
    return cfg


def _wet_ramp(trace):
    """Dry start, soaked middle, drying finish — the crossover race E-08 owns. Sized to the
    fixture circuit's 57 laps: rain arrives on lap 16, the track is fully wet from lap 18 to
    lap 40, and it is dry again from lap 43."""
    wetness = np.zeros(trace.n_laps)
    wetness[15:17] = (0.3, 0.6)
    wetness[17:40] = 0.9
    wetness[40:42] = (0.6, 0.3)
    trace.wetness[:] = wetness
    trace.weather[:] = np.where(
        wetness >= 0.7, events.WET, np.where(wetness > 0.3, events.DAMP, events.DRY)
    )
    return trace


def _compound_allowed(name, wetness, validity):
    """The same rule senna/env/masks.py applies, restated here so the test says what it
    checks instead of borrowing the code under test."""
    if name in SLICKS:
        return wetness <= validity["slick_max_wetness"]
    if name == "INTERMEDIATE":
        low, high = validity["inter_band"]
        return low <= wetness <= high
    return wetness >= validity["wet_min_wetness"]


def test_dry_enumeration_unchanged_by_the_wet_extension(scenario, green_trace):
    plans = enumerate_plans(scenario, green_trace, 1)

    # Bahrain runs 57 laps and every fitted slick carries a 43-lap cliff cap, which fixes
    # the one-stop window at both ends: box before lap 14 and the new tyre cannot reach the
    # flag, box after lap 45 and the grid MEDIUM cannot reach the stop. MEDIUM never appears
    # as the stop compound — refitting the start tyre leaves the race one compound short
    # (F-20).
    expected = {((lap, name),) for lap in range(14, 46) for name in ("HARD", "SOFT")}
    assert {plan.stops for plan in plans} == expected

    plan, cost_s = solo_reference(scenario, cfg=_oracle_cfg(max_stops=1, top_k=3))
    assert plan == PitPlan(stops=((14, "SOFT"),))
    # a physics-derived pin, not a physics claim: what this test is about is that the
    # wet extension leaves dry enumeration alone, and the tight tolerance catches a
    # silent change in the search. The number tracks configs/physics_params.yaml and is
    # expected to move on a refit — F18 moved it from 5555.697989252283 when the fits
    # went from two seasons to four, and F24 from 5585.666133009284 when the repair
    # gave the soft real wear.
    assert cost_s == pytest.approx(5667.5262072564865, rel=1e-9)


@pytest.mark.slow
def test_wet_enumeration_respects_pit_entry_legality(scenario, green_trace):
    trace = _wet_ramp(green_trace)
    validity = scenario.env["compound_validity"]

    oracle = solve_oracle(scenario, trace, cfg=_oracle_cfg(max_stops=2, top_k=3))
    assert oracle.plan is not None
    assert np.isfinite(oracle.race_time_s)

    plans = enumerate_plans(scenario, trace, 2)
    assert plans
    for plan in plans:
        for out_lap, name in plan.stops:
            entry_wetness = float(trace.wetness[out_lap - 2])
            assert _compound_allowed(name, entry_wetness, validity), (
                f"{name} taken on lap {out_lap} entered the pit lane at wetness "
                f"{entry_wetness}, where the mask would have refused it"
            )


def test_stage1_pit_charge_is_status_aware(scenario, green_trace):
    trace = green_trace
    trace.status[27:30] = events.SC  # laps 28-30 neutralised
    medium, hard = compound_code("MEDIUM"), compound_code("HARD")
    tables = {code: stint_cost_table(scenario, trace, code) for code in (medium, hard)}

    def charged_pit_loss_s(out_lap):
        """A one-stop plan's table cost less its two stint costs. The stints are the only
        other term, so what is left is exactly what stage 1 charges for the stop."""
        plan = PitPlan(stops=((out_lap, "HARD"),))
        stints_s = tables[medium][1, out_lap] + tables[hard][out_lap + 1, trace.n_laps]
        return _plan_table_cost(plan, tables, scenario, trace) - stints_s

    under_sc_s = charged_pit_loss_s(29)  # the out-lap runs under the safety car
    on_green_s = charged_pit_loss_s(34)

    assert on_green_s == pytest.approx(scenario.pit_loss_mean_s, rel=1e-9)
    assert under_sc_s == pytest.approx(
        scenario.pit_loss_mean_s * scenario.env["pit_loss_mult"]["sc"], rel=1e-9
    )
    assert under_sc_s < on_green_s


@pytest.mark.slow
def test_regret_is_zero_when_the_agent_plays_the_oracle_plan(make_env, scenario, green_trace):
    trace = _wet_ramp(green_trace)
    cfg = _oracle_cfg(max_stops=2, top_k=3)

    oracle = solve_oracle(scenario, trace, cfg=cfg)
    # seed 0 is the seed solve_oracle rolls its own contenders on; the twin is deterministic,
    # so replaying the winning plan has to land on the reported time exactly — that identity
    # is what makes M3 regret a gap and not an artefact of two different rolls
    replay = run_episode(
        make_env(twin=trace), PlanPolicy(oracle.plan, mode="greedy", scenario=scenario), seed=0
    )
    assert replay.race_time_s == pytest.approx(oracle.race_time_s, abs=1e-6)

    agent = run_episode(
        make_env(twin=trace),
        EngineerHeuristic(scenario, config.load("baselines")["heuristic"]),
        seed=SEED,
    )
    agent_plan = PitPlan(stops=tuple(zip(agent.pit_laps, agent.compounds, strict=True)))
    contested = solve_oracle(scenario, trace, cfg=cfg, baselines=(agent_plan,))

    # a baseline only ever adds a contender to stage 2, so the oracle's time can tie or
    # improve, never drift the other way
    assert contested.race_time_s <= oracle.race_time_s + 1e-9
