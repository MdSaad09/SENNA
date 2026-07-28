"""Neutralisation windows and the spliced replay the M5/M6 afterstate searches branch from.

A window is a maximal run of one neutralised status in the trace; RED is never one and it
breaks the runs on either side of it (E-04). The timing rule is the point of the module:
the action for lap L is chosen against the mask built at the end of lap L-1, so a safety
car that starts on lap w1 is first visible to the decision for lap w1+1. A stop taken on
the onset lap was called blind and cannot be graded, which is why the published M5
denominator counts a window only when it offers at least one informed decision lap.

SplicedPolicy exists because ScriptedActions holds station once its script runs out, and
an afterstate variant has to keep racing to the flag under the agent's own policy — a
frozen tail would grade every counterfactual against a car that stopped strategising.
"""

import numpy as np
import pytest

from senna import config
from senna.env import events
from senna.env.twin import EventTrace
from senna.eval.afterstate import SplicedPolicy, Window, neutralisation_windows
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.rollout import run_episode
from tests.eval.conftest import CIRCUIT, SEED


def test_window_extraction_on_handbuilt_status_arrays():
    statuses = np.full(24, events.GREEN, dtype=int)
    statuses[4:7] = events.VSC  # laps 5-7
    statuses[7:9] = events.SC  # laps 8-9, adjacent but a different status
    statuses[12:14] = events.SC  # laps 13-14
    statuses[14] = events.RED  # lap 15 splits the safety car in two
    statuses[15:17] = events.SC  # laps 16-17
    statuses[21] = events.SC  # lap 22, the last completed lap
    statuses[22:24] = events.VSC  # laps 23-24, after the ego saw the flag

    trace = EventTrace.green(CIRCUIT, "2026", 24, 1, grid=np.array([1]))
    trace.status[:] = statuses

    windows = neutralisation_windows(trace, last_lap=22)

    assert [(w.status, w.first_lap, w.last_lap) for w in windows] == [
        ("vsc", 5, 7),
        ("sc", 8, 9),
        ("sc", 13, 14),
        ("sc", 16, 17),
    ]
    assert not any(w.first_lap <= 15 <= w.last_lap for w in windows)  # E-04: RED is never one
    assert not any(w.first_lap >= 22 for w in windows)  # nothing informed is left to decide


def test_decision_laps_start_after_the_onset():
    window = Window(status="sc", first_lap=30, last_lap=32)

    assert window.decision_laps(57) == [31, 32]
    assert window.decision_laps(31) == [31]
    assert window.decision_laps(30) == []  # lap 30's action was chosen before the car saw it


@pytest.mark.slow
def test_spliced_policy_prefix_reproduces_the_base_roll(make_env, scenario, trace_with_sc):
    heuristic_cfg = config.load("baselines")["heuristic"]
    env = make_env(twin=trace_with_sc)

    base = run_episode(env, EngineerHeuristic(scenario, heuristic_cfg), seed=SEED)
    spliced = run_episode(
        env,
        SplicedPolicy(
            prefix_actions=base.actions,
            tail_policy=EngineerHeuristic(scenario, heuristic_cfg),
        ),
        seed=SEED,
    )

    assert spliced.race_time_s == pytest.approx(base.race_time_s, abs=1e-9)
    assert [action.tolist() for action in spliced.actions] == [
        action.tolist() for action in base.actions
    ]
    assert spliced.pit_laps == base.pit_laps
    assert spliced.compounds == base.compounds
