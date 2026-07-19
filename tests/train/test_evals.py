"""The gate evaluation loops (5.7): the Stage A reference proof, frozen-seed
aggregation, and the Stage B pairing that runs on EventTraces rather than raw seeds
(A-06, INDEX decision 19 Jul) — including the overflow path for a DNF'd recording.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from senna import config
from senna.env import F1RaceEnv
from senna.env.scenario import build_scenario
from senna.env.twin import EventTrace
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.plans import PitPlan, PlanPolicy
from senna.strategy.rollout import run_episode
from senna.train.evals import (
    RecordedRace,
    record_stage_b_traces,
    run_stage_a_eval,
    run_stage_b_eval,
    stage_a_reference,
)
from senna.train.gates import StageAEval, pair_outcome
from tests.train.conftest import CIRCUIT

SUB_BANK = (846_101, 846_102, 846_103, 846_104, 846_105)  # a 5-seed stand-in bank


@pytest.mark.property
@pytest.mark.slow
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=6, deadline=None)
def test_solo_reference_matches_a_twin_roll_of_its_own_plan(seed):
    plan, reference_time_s = stage_a_reference(CIRCUIT)

    scenario = build_scenario(CIRCUIT, "2026")
    trace = EventTrace.green(
        CIRCUIT, "2026", scenario.total_laps, 1, grid=np.array([1]), driver_s=np.zeros(1)
    )
    env = F1RaceEnv(CIRCUIT, "2026", solo=True, twin=trace)
    rolled = run_episode(env, PlanPolicy(plan, mode="greedy", scenario=scenario), seed=seed)

    # the twin zeroes noise and takes pit service at the mean, so any seed lands on the
    # table's cost — the exactness that makes the 1.5% Stage A time gate meaningful
    assert rolled.race_time_s == pytest.approx(reference_time_s, abs=0.5)


@pytest.mark.slow
def test_stage_a_eval_aggregates_over_seeds():
    one_stop = PlanPolicy(PitPlan(stops=((26, "HARD"),)), mode="balanced")

    first = run_stage_a_eval(one_stop, step=49_152, circuit=CIRCUIT, seeds=SUB_BANK)
    again = run_stage_a_eval(one_stop, step=49_152, circuit=CIRCUIT, seeds=SUB_BANK)

    assert isinstance(first, StageAEval)
    assert first.step == 49_152
    assert np.isfinite(first.mean_return)
    assert first.mean_race_time_s > 0.0
    assert first.dnf_count == 0  # solo DNFs are fuel-only, and a one-stop race covers it
    assert first == again  # frozen seeds make the eval a pure function of the policy


@pytest.mark.slow
def test_stage_b_pairing_self_pair_is_a_tie():
    scenario = build_scenario(CIRCUIT, "2026")
    heuristic = EngineerHeuristic(scenario, config.load("baselines")["heuristic"])

    recorded, replaced = record_stage_b_traces(
        banks={CIRCUIT: (846_201,)}, overflow=(846_298, 846_299)
    )
    assert replaced == []
    assert len(recorded) == 1
    assert recorded[0].circuit == CIRCUIT

    # the recorded baseline replayed against its own twin: like for like, so a dead tie
    (pair,) = run_stage_b_eval(heuristic, recorded)
    assert pair.seed == 846_201
    assert pair.agent_position == pair.baseline_position
    assert pair_outcome(
        pair.agent_position, pair.agent_dnf, pair.baseline_position, pair.baseline_dnf
    ) == (False, 0)


def test_stage_b_recording_replaces_a_dnf_seed_from_overflow():
    def recorder(circuit, seed):
        if seed == 846_302:
            raise RuntimeError(f"{circuit}: recorded race DNF'd on seed {seed}")
        return RecordedRace(circuit=circuit, seed=seed, trace=None, baseline=None)

    recorded, replaced = record_stage_b_traces(
        banks={CIRCUIT: (846_301, 846_302, 846_303)},
        overflow=(846_311, 846_312),
        recorder=recorder,
    )
    assert [race.seed for race in recorded] == [846_301, 846_311, 846_303]
    assert replaced == [(846_302, 846_311)]

    def always_dnf(circuit, seed):
        raise RuntimeError(f"{circuit}: recorded race DNF'd on seed {seed}")

    # the overflow bank is finite insurance, not an infinite retry loop
    with pytest.raises(RuntimeError):
        record_stage_b_traces(
            banks={CIRCUIT: (846_301,)}, overflow=(846_311,), recorder=always_dnf
        )
