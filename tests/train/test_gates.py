"""Competence gates on hand-built histories (5.7, F-21). The deciders are pure
functions: every threshold arrives as a keyword from curriculum.yaml, and no gate ever
sees a step budget — a ceiling hit is a budget_stop in the log, never a pass.
"""

import pytest

from senna.train.gates import (
    GateDecision,
    StageCEval,
    pair_outcome,
    plateaued,
    select_checkpoint,
    stage_a_gate,
    stage_b_gate,
    stage_c_stop,
)
from tests.train.conftest import REFERENCE_TIME_S, a_history, pairs

GATE_A = dict(
    reference_time_s=REFERENCE_TIME_S,
    plateau_window=3,
    plateau_min_improvement=0.01,
    time_tolerance=0.015,
    denominator_floor=1.0,
)


def test_stage_a_gate_passes_on_a_flat_window_over_a_met_time_bar():
    history = a_history(2.0, 6.0, 8.0, 8.02, 7.99, 8.03)
    decision = stage_a_gate(history, **GATE_A)

    assert isinstance(decision, GateDecision)
    assert decision.passed
    assert decision.values["plateau_improvement"] < 0.01
    assert decision.values["time_delta_frac"] == pytest.approx(0.0)
    assert decision.values["anomaly"] is None


def test_stage_a_plateau_is_not_fooled_by_slow_creep():
    # +0.9% per eval forever: under the per-eval bar, but best-of-window vs best-before
    # compounds it to ~2.7% — the reading that makes a slow creep keep training
    creep = [10.0 * 1.009**i for i in range(12)]
    flat, improvement = plateaued(creep, window=3, min_improvement=0.01, denominator_floor=1.0)
    assert not flat
    assert improvement > 0.01
    assert not stage_a_gate(a_history(*creep), **GATE_A).passed


def test_stage_a_gate_needs_both_plateau_and_time():
    flat_but_slow = a_history(5.0, 5.01, 5.0, 5.01, times=[REFERENCE_TIME_S * 1.03] * 4)
    assert not stage_a_gate(flat_but_slow, **GATE_A).passed  # a plateau alone is not enough

    fast_but_learning = a_history(1.0, 2.0, 4.0, 8.0)  # times sit exactly on the bar
    assert not stage_a_gate(fast_but_learning, **GATE_A).passed  # F-21: time alone is not enough


def test_stage_a_time_gate_is_one_sided_and_flags_an_implausible_beat():
    flat = (5.0, 5.0, 5.0, 5.0)

    just_inside = stage_a_gate(a_history(*flat, times=[REFERENCE_TIME_S * 1.014] * 4), **GATE_A)
    assert just_inside.passed
    assert just_inside.values["anomaly"] is None

    small_beat = stage_a_gate(a_history(*flat, times=[REFERENCE_TIME_S * 0.995] * 4), **GATE_A)
    assert small_beat.passed
    assert small_beat.values["anomaly"] is None

    just_outside = stage_a_gate(a_history(*flat, times=[REFERENCE_TIME_S * 1.016] * 4), **GATE_A)
    assert not just_outside.passed

    big_beat = stage_a_gate(a_history(*flat, times=[REFERENCE_TIME_S * 0.98] * 4), **GATE_A)
    assert big_beat.passed  # one-sided: faster than the reference always passes ...
    assert big_beat.values["anomaly"] == "beats_reference_beyond_tolerance"  # ... but flagged


def test_stage_a_gate_holds_once_triggered():
    passing = a_history(2.0, 6.0, 8.0, 8.02, 7.99, 8.03)
    assert stage_a_gate(passing, **GATE_A).passed

    # training stops on a pass; if evals somehow kept coming, the decision must not flap
    regressed = a_history(
        2.0, 6.0, 8.0, 8.02, 7.99, 8.03, 12.0, 15.0,
        times=[REFERENCE_TIME_S] * 6 + [REFERENCE_TIME_S * 1.05] * 2,
    )
    assert stage_a_gate(regressed, **GATE_A).passed


def test_stage_a_gate_refuses_a_short_history():
    decision = stage_a_gate(a_history(5.0, 5.0, 5.0), **GATE_A)  # window + 1 needs 4
    assert not decision.passed
    assert "short" in decision.reason


def test_stage_b_thresholds_are_inclusive():
    at_the_rate_bar = stage_b_gate(
        pairs(200, 0.55), finish_ahead_min=0.55, median_delta_min=0.0, n_required=200
    )
    assert at_the_rate_bar.passed
    assert at_the_rate_bar.values["finish_ahead_rate"] == pytest.approx(0.55)

    # any ahead rate over 0.5 forces a positive median, so the median bar pins at rate 0.5
    at_the_median_bar = stage_b_gate(
        pairs(20, 0.5, ahead_delta=1), finish_ahead_min=0.5, median_delta_min=0.0, n_required=20
    )
    assert at_the_median_bar.passed
    assert at_the_median_bar.values["median_position_delta"] == pytest.approx(0.0)

    under_the_rate_bar = stage_b_gate(
        pairs(1000, 0.549), finish_ahead_min=0.55, median_delta_min=0.0, n_required=1000
    )
    assert not under_the_rate_bar.passed

    half_ties = pairs(10, 0.0, rest_delta=0) + pairs(10, 0.0, rest_delta=-1)
    under_the_median_bar = stage_b_gate(
        half_ties, finish_ahead_min=0.0, median_delta_min=0.0, n_required=20
    )
    assert not under_the_median_bar.passed
    assert under_the_median_bar.values["median_position_delta"] == pytest.approx(-0.5)


def test_stage_b_pair_outcome_orders_dnfs():
    assert pair_outcome(3, False, 7, False) == (True, 4)  # both finish, agent ahead
    assert pair_outcome(9, False, 6, False) == (False, -3)  # both finish, baseline ahead
    assert pair_outcome(5, False, 5, False) == (False, 0)  # a tie counts against the agent
    assert pair_outcome(5, False, 18, True) == (True, 13)  # a finisher beats any DNF
    assert pair_outcome(18, True, 5, False) == (False, -13)  # a DNF never beats a finisher
    assert pair_outcome(12, True, 14, True) == (False, 0)  # both out: no evidence either way


def test_stage_b_gate_demands_exactly_n_pairs():
    # a harness that silently dropped a seed would bias the rate — fail loudly instead
    with pytest.raises(ValueError):
        stage_b_gate(pairs(199, 0.6), finish_ahead_min=0.55, median_delta_min=0.0, n_required=200)


def test_stage_c_stagnation_clock_resets_on_improvement():
    stale = [
        StageCEval(step=100_000, mean_points=5.0),
        StageCEval(step=600_000, mean_points=5.0),  # equal is not an improvement
    ]
    stop = stage_c_stop(
        stale, current_step=1_200_000, stagnation_steps=1_000_000, min_improvement_points=0.0
    )
    assert stop.passed  # 1.1M steps since the best eval: stop and select
    assert stop.values["best_step"] == 100_000

    improved = [*stale, StageCEval(step=1_100_000, mean_points=5.5)]
    keep_going = stage_c_stop(
        improved, current_step=1_200_000, stagnation_steps=1_000_000, min_improvement_points=0.0
    )
    assert not keep_going.passed
    assert keep_going.values["best_step"] == 1_100_000
    assert keep_going.values["steps_since_best"] == 100_000


def test_stage_c_checkpoint_selection_breaks_ties_toward_the_earlier_step():
    history = [
        StageCEval(step=300_000, mean_points=6.2),
        StageCEval(step=400_000, mean_points=7.1),
        StageCEval(step=900_000, mean_points=7.1),
    ]
    assert select_checkpoint(history).step == 400_000


def test_no_stage_ever_advances_on_step_count_alone():
    # F-21: budget-exhausted histories with failing gates never pass, in any stage
    still_creeping = [10.0 * 1.009**i for i in range(30)]  # ~1.5M steps of evals, no plateau
    assert not stage_a_gate(a_history(*still_creeping), **GATE_A).passed

    flat_but_slow = a_history(*[5.0] * 30, times=[REFERENCE_TIME_S * 1.05] * 30)
    assert not stage_a_gate(flat_but_slow, **GATE_A).passed

    # the B gate takes no step input at all — only the paired outcomes can move it
    losing = stage_b_gate(
        pairs(200, 0.30), finish_ahead_min=0.55, median_delta_min=0.0, n_required=200
    )
    assert not losing.passed

    # and C selection follows points, never recency
    late_and_worse = [
        StageCEval(step=100_000, mean_points=9.0),
        StageCEval(step=4_000_000, mean_points=3.0),
    ]
    assert select_checkpoint(late_and_worse).step == 100_000
