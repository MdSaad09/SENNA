"""M5 — SC/VSC decision quality against the ex-post afterstate optimum (5.12, E-03).

Two layers, tested apart. The labelling layer asks a physics question: on this trace, from
this car's state, was boxing in the window worth more than the materiality margin? A car
that reaches the window on a worn tyre with nothing else planned should be told to pit; the
same window one lap after a fresh set went on should be told to stay, because a second stop
buys nothing and still pays the neutralised pit loss.

The scoring layer is pure arithmetic and is pinned without a single rollout: precision AND
recall, SC and VSC in separate blocks (E-03), immaterial windows out of both numerator and
denominator and counted by reason. Recall alone is the gameable half — an always-pit call
sheet cannot miss an opportunity — which is why 5.12 M5 demands both numbers together.

A stop on the window's onset lap does not count as a call: that action was chosen against
the mask built at the end of the previous lap, before the neutralisation existed.
"""

import numpy as np
import pytest

from senna.env import events
from senna.eval.afterstate import Window
from senna.eval.sc_quality import sc_decision_quality, window_verdict
from senna.strategy.plans import PitPlan, PlanPolicy
from senna.strategy.rollout import run_episode
from tests.eval.conftest import SEED

# mirrors the m5 block of configs/eval.yaml; kept literal here so the metric arithmetic
# stays pinned to known answers when the config's targets are retuned
_M5_CFG = {"label_margin_s": 1.0, "precision_target": 0.75, "recall_target": 0.75}


def _sc_onset(trace) -> int:
    return int(np.flatnonzero(trace.status == events.SC)[0]) + 1


def _plan_race(env, scenario, stops):
    policy = PlanPolicy(PitPlan(stops=stops), mode="greedy", scenario=scenario)
    return run_episode(env, policy, seed=SEED)


def _verdict(status, first_lap, *, label, called, excluded=None):
    """A hand-built verdict in the shape window_verdict returns, with the two time fields
    kept consistent with the label so nothing has to be re-derived downstream."""
    margin_s = {"pit": 5.0, "stay": -5.0, "immaterial": 0.2}[label]
    stay_time_s = 5000.0
    return {
        "status": status,
        "first_lap": first_lap,
        "last_lap": first_lap + 2,
        "label": label,
        "agent_called_pit": called,
        "best_pit_time_s": stay_time_s - margin_s,
        "stay_time_s": stay_time_s,
        "margin_s": margin_s,
        "excluded": excluded,
    }


@pytest.mark.slow
def test_m5_labels_on_a_constructed_sc_window(make_env, scenario, trace_with_sc):
    trace = trace_with_sc
    onset = _sc_onset(trace)
    window = Window(status="sc", first_lap=onset, last_lap=onset + 2)
    env = make_env(twin=trace)

    worn = _plan_race(env, scenario, ((14, "HARD"),))
    verdict = window_verdict(window, race=worn, scenario=scenario, env=env, cfg=_M5_CFG)

    assert verdict["excluded"] is None
    assert verdict["label"] == "pit"
    assert verdict["best_pit_time_s"] < verdict["stay_time_s"]
    assert verdict["margin_s"] == pytest.approx(
        verdict["stay_time_s"] - verdict["best_pit_time_s"]
    )
    assert verdict["margin_s"] > _M5_CFG["label_margin_s"]

    # the same window, one lap after a fresh SOFT went on: another stop throws the tyre away
    # and still pays the neutralised pit loss
    fresh = _plan_race(env, scenario, ((14, "HARD"), (onset - 1, "SOFT")))
    verdict = window_verdict(window, race=fresh, scenario=scenario, env=env, cfg=_M5_CFG)

    assert verdict["excluded"] is None
    assert verdict["label"] == "stay"
    assert verdict["best_pit_time_s"] > verdict["stay_time_s"]
    assert verdict["margin_s"] < -_M5_CFG["label_margin_s"]


def test_m5_precision_recall_per_window_vsc_and_sc_separated():
    verdicts = [
        _verdict("sc", 10, label="pit", called=True),
        _verdict("sc", 20, label="pit", called=False),
        _verdict("sc", 30, label="stay", called=False),
        _verdict("sc", 40, label="stay", called=False),
        _verdict("vsc", 12, label="pit", called=True),
        _verdict("vsc", 22, label="pit", called=True),
        _verdict("vsc", 32, label="stay", called=False),
        _verdict("sc", 50, label="immaterial", called=True, excluded="immaterial"),
        _verdict("vsc", 52, label="immaterial", called=False, excluded="immaterial"),
    ]

    quality = sc_decision_quality(verdicts, cfg=_M5_CFG)

    assert quality["sc"]["tp"] == 1
    assert quality["sc"]["fp"] == 0
    assert quality["sc"]["fn"] == 1
    assert quality["sc"]["tn"] == 2
    assert quality["sc"]["precision"] == pytest.approx(1.0)
    assert quality["sc"]["recall"] == pytest.approx(0.5)
    assert quality["sc"]["n_windows"] == 4

    # E-03: pooling the two states would report precision 1.0 / recall 0.75 and hide that
    # the agent answers a VSC well and a safety car badly
    assert quality["vsc"]["tp"] == 2
    assert quality["vsc"]["fp"] == 0
    assert quality["vsc"]["fn"] == 0
    assert quality["vsc"]["tn"] == 1
    assert quality["vsc"]["precision"] == pytest.approx(1.0)
    assert quality["vsc"]["recall"] == pytest.approx(1.0)
    assert quality["vsc"]["n_windows"] == 3

    assert quality["excluded"] == {"immaterial": 2}
    assert quality["targets"] == {"precision": 0.75, "recall": 0.75}
    assert not quality["met"]  # the SC recall of 0.5 misses

    always_pit = [dict(verdict, agent_called_pit=True) for verdict in verdicts]
    inflated = sc_decision_quality(always_pit, cfg=_M5_CFG)

    assert inflated["sc"]["recall"] == pytest.approx(1.0)
    assert inflated["vsc"]["recall"] == pytest.approx(1.0)
    assert inflated["sc"]["precision"] == pytest.approx(0.5)
    assert inflated["excluded"] == {"immaterial": 2}


def test_m5_onset_lap_pit_is_not_counted_as_a_call(make_env, scenario, trace_with_sc):
    trace = trace_with_sc
    onset = _sc_onset(trace)
    window = Window(status="sc", first_lap=onset, last_lap=onset + 2)
    env = make_env(twin=trace)

    blind = _plan_race(env, scenario, ((onset, "HARD"),))
    assert blind.pit_laps == [onset]
    verdict = window_verdict(window, race=blind, scenario=scenario, env=env, cfg=_M5_CFG)
    assert not verdict["agent_called_pit"]

    informed = _plan_race(env, scenario, ((onset + 1, "HARD"),))
    assert informed.pit_laps == [onset + 1]
    verdict = window_verdict(window, race=informed, scenario=scenario, env=env, cfg=_M5_CFG)
    assert verdict["agent_called_pit"]
