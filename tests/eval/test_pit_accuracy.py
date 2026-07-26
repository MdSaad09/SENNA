"""M6 — pit window accuracy: the share of stops within 3 laps of the post-hoc optimum.

The sweep is a corridor, not a free search. A stop can only move between its neighbours,
neither adjacent stint may run past its compound's cliff cap, and the compound the car
actually took has to be legal at the pit entry of every candidate lap — the mask is built
at the end of lap L-1, so the wetness that decides is trace.wetness[L-2] (E-08). The
realised lap is always in its own corridor: without that identity the sweep would not be a
coordinate-wise search around what the agent did.

The scoring half is pure arithmetic and needs no rollout. A stop counts as a hit when it
sits within the tolerance of the nearest optimal lap — nearest, because a tie in the sweep
means two laps were equally good and grading against the further one would penalise an
agent that found the other. Forced and red-flag stops (E-04) never enter the denominator;
they were not decisions, and the counts surface so the published share says what it covers.
"""

import numpy as np
import pytest

from senna import config
from senna.env import events
from senna.env.scenario import SLICKS
from senna.env.twin import EventTrace
from senna.eval.pit_accuracy import pit_window_accuracy, stop_corridor
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.plans import PitPlan, PlanPolicy
from senna.strategy.rollout import run_episode
from tests.eval.conftest import CIRCUIT, SEED

# mirrors the m6 block of configs/eval.yaml plus the shared bootstrap knobs; kept literal
# so the constructed hit/miss answers stay fixed when the config's target is retuned
_M6_CFG = {
    "tolerance_laps": 3,
    "target_share": 0.72,
    "bootstrap": {"seed": SEED, "resamples": 200},
}


def _cliff_cap_laps(scenario, name):
    return scenario.deg_max_age[name] + scenario.env["tyre_failure"]["cliff_age_margin_laps"]


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
    """The same rule senna/env/masks.py applies, restated so the test says what it checks."""
    if name in SLICKS:
        return wetness <= validity["slick_max_wetness"]
    if name == "INTERMEDIATE":
        low, high = validity["inter_band"]
        return low <= wetness <= high
    return wetness >= validity["wet_min_wetness"]


def _row(stop_lap, optimal_laps, *, excluded=None):
    return {
        "circuit": CIRCUIT,
        "seed": SEED,
        "stop_lap": stop_lap,
        "optimal_laps": optimal_laps,
        "excluded": excluded,
    }


@pytest.mark.slow
def test_m6_sweep_identity_and_legality(make_env, scenario, green_trace):
    n_laps = green_trace.n_laps
    env = make_env(twin=green_trace)
    race = run_episode(
        env,
        PlanPolicy(PitPlan(stops=((25, "HARD"),)), mode="greedy", scenario=scenario),
        seed=SEED,
    )
    assert race.pit_laps == [25]

    corridor = stop_corridor(race, 0, scenario=scenario, trace=green_trace)

    assert 25 in corridor  # L' = L_i, the identity the sweep is built around
    for candidate in corridor:
        # the grid MEDIUM runs laps 1..L-1 and the HARD runs L..n; neither may reach the
        # cliff, or the "optimum" would be a stint the sim force-pits out of
        assert candidate - 2 <= _cliff_cap_laps(scenario, "MEDIUM")
        assert n_laps - candidate <= _cliff_cap_laps(scenario, "HARD")
    assert 13 not in corridor  # a HARD fitted here finishes the race 44 laps old
    assert 46 not in corridor  # and the grid MEDIUM would reach the stop 44 laps old

    wet_trace = _wet_ramp(
        EventTrace.green(env.circuit, env.era, n_laps, green_trace.n_cars, grid=green_trace.grid)
    )
    wet_race = run_episode(
        make_env(twin=wet_trace),
        EngineerHeuristic(scenario, config.load("baselines")["heuristic"]),
        seed=SEED,
    )
    assert wet_race.pit_laps

    validity = scenario.env["compound_validity"]
    for index, (lap, name) in enumerate(
        zip(wet_race.pit_laps, wet_race.compounds, strict=True)
    ):
        corridor = stop_corridor(wet_race, index, scenario=scenario, trace=wet_trace)
        assert lap in corridor
        for candidate in corridor:
            entry_wetness = float(wet_trace.wetness[candidate - 2])
            assert _compound_allowed(name, entry_wetness, validity), (
                f"stop {index} ({name}) was offered lap {candidate}, whose pit entry sits "
                f"at wetness {entry_wetness}"
            )

    last = len(wet_race.pit_laps) - 1
    assert wet_race.compounds[last] in SLICKS  # the heuristic comes back to slicks as it dries
    assert 30 not in stop_corridor(wet_race, last, scenario=scenario, trace=wet_trace)


def test_m6_constructed_hit_and_miss():
    rows = [
        _row(20, [20]),  # on the optimum
        _row(23, [20]),  # exactly the tolerance away — "within 3 laps" includes the boundary
        _row(25, [20]),  # five laps off
        _row(34, [22, 31]),  # tied optima, three laps from the nearer one
        _row(26, [22, 31]),  # tied optima, four laps from the nearer one
    ]

    accuracy = pit_window_accuracy(rows, cfg=_M6_CFG)

    assert accuracy["n_stops"] == 5
    assert accuracy["share"] == pytest.approx(0.6)
    assert accuracy["target"] == _M6_CFG["target_share"]
    assert not accuracy["met"]
    assert accuracy["ci_low"] <= accuracy["share"] <= accuracy["ci_high"]
    assert 0.0 <= accuracy["ci_low"]
    assert accuracy["ci_high"] <= 1.0


def test_m6_excludes_forced_and_red_flag_stops():
    rows = [
        _row(20, [20]),
        _row(25, [20]),
        _row(12, [12], excluded="forced_pit"),  # a cliff failure, not a call
        _row(44, [44], excluded="red_flag"),  # the E-04 free tyre change
    ]

    accuracy = pit_window_accuracy(rows, cfg=_M6_CFG)

    # both excluded rows would have scored as hits; counting them would lift 0.5 to 0.75
    assert accuracy["n_stops"] == 2
    assert accuracy["share"] == pytest.approx(0.5)
    assert accuracy["excluded"] == {"forced_pit": 1, "red_flag": 1}
