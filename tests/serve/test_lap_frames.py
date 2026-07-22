"""build_lap_frame: the honest per-lap derivation from a lap-quantised RaceState to the
5.9.2 LapFrame. Everything here must hold for any legal playthrough, because the worker
calls it once per lap on whatever race the policy happens to produce.
"""

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from api.schemas import LapFrame
from senna.env.scenario import COMPOUNDS
from senna.serve.frames import build_lap_frame
from tests.serve.conftest import SEED, sample_legal_action

_EVENT_KINDS = {"sc", "vsc", "red", "weather", "pit"}


def _assert_frame_invariants(frame: dict, env, info) -> None:
    LapFrame.model_validate(frame)

    cars = frame["cars"]
    assert len(cars) == env.n_cars
    assert {car["id"] for car in cars} == set(range(env.n_cars))  # ego stable at id 0
    assert sorted(car["position"] for car in cars) == list(range(1, env.n_cars + 1))
    for car in cars:
        assert 0.0 <= car["s_track"] < 1.0
        assert car["compound"] in COMPOUNDS
        assert car["tyre_age"] >= 0

    agent = frame["agent"]
    assert 0.0 <= agent["soc_mj"] <= 4.0  # the 4 MJ usable store (E-01)
    assert agent["soc_mj"] == pytest.approx(info["energy"]["soc_mj"])

    ego = next(car for car in cars if car["id"] == 0)
    if ego["position"] > 1:
        # the display gap must be the env's own, not a second derivation free to drift
        assert ego["gap_ahead_s"] == pytest.approx(info["gap_ahead_s"], abs=1e-6)

    assert all(event["kind"] in _EVENT_KINDS for event in frame["events"])


def _assert_pit_flags(prev_frame: dict, frame: dict) -> bool:
    """A tyre-age reset between consecutive green frames is a stop; the frame must say
    so, and a rival stop must surface as a pit RaceEvent."""
    prev_age = {car["id"]: car["tyre_age"] for car in prev_frame["cars"]}
    pit_event_ids = {event["car_id"] for event in frame["events"] if event["kind"] == "pit"}
    stopped = False
    for car in frame["cars"]:
        if prev_age[car["id"]] > 0 and car["tyre_age"] == 0:
            assert car["in_pit"] is True
            if car["id"] != 0:
                assert car["id"] in pit_event_ids
            stopped = True
    return stopped


def _play_and_check(env, seed: int, max_laps: int | None = None) -> bool:
    rng = np.random.default_rng(seed)
    _, info = env.reset(seed=seed)
    snapshot = None
    prev_frame = None
    saw_stop = False
    terminated = False
    lap = 0
    while not terminated and (max_laps is None or lap < max_laps):
        action = sample_legal_action(env.action_masks(), rng)
        _, _, terminated, _, info = env.step(action)
        frame, snapshot = build_lap_frame(env, info, snapshot)
        _assert_frame_invariants(frame, env, info)
        # a red flag resets every car's tyres without a stop, so skip the diff there
        if prev_frame is not None and not info["events"]["red_flag"]:
            saw_stop |= _assert_pit_flags(prev_frame, frame)
        prev_frame = frame
        lap += 1
    return saw_stop


def test_a_random_legal_race_yields_valid_frames_every_lap(env):
    saw_stop = _play_and_check(env, SEED)
    # rivals always stop at least once, so the in_pit branch genuinely executed
    assert saw_stop


@pytest.mark.property
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=25, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_frame_invariants_hold_for_any_legal_playthrough(make_env, seed):
    # bounded laps keep the property run inside the fast suite's budget
    _play_and_check(make_env(), seed, max_laps=12)
