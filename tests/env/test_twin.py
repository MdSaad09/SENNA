"""The deterministic twin (F06, A-05/M3, M5 groundwork). record=True captures the
events an episode actually applied; twin=trace replays them with pace noise zeroed and
pit service collapsed to the mean, so a rolled trace is byte-identical run to run. The
paired-seed guarantee lives here: change the ego's strategy and the per-lap track
status, weather and wetness do not move, because they come from the trace, not a policy-
coupled RNG stream (F06 plan finding 2). Terminal info also gains race_time_s, the
race-time bar Stage A gates on.

Suite seed 704, matching the F06 rival tests and clear of the env suite's 512.
"""

import numpy as np
import pytest

from senna.env import F1RaceEnv
from senna.env.twin import EventTrace

SEED = 704
CIRCUIT = "bahrain_grand_prix"
ERA = "2026"

# a fixed policy: run balanced, take one mid-race stop to HARD, then run to the flag
ACTIONS = [[0, 1]] * 15 + [[3, 1]] + [[0, 1]] * 80
# two ego strategies that share nothing but the trace they roll on
STALL = [[0, 1]] * 200
STOP_EARLY = [[0, 1]] * 8 + [[3, 1]] + [[0, 1]] * 200


def _play(env, actions):
    obs, info = env.reset(seed=SEED)
    frames = [obs.copy()]
    infos = [info]
    for action in actions:
        obs, reward, terminated, truncated, info = env.step(np.array(action))
        frames.append(obs.copy())
        infos.append(info)
        if terminated:
            break
    return np.array(frames), infos


def _record_trace(actions):
    recorder = F1RaceEnv(CIRCUIT, ERA, record=True)
    _play(recorder, actions)
    return recorder.recorded_trace()


def test_a_captured_trace_replays_to_a_byte_identical_deterministic_episode():
    trace = _record_trace(ACTIONS)

    frames_a, infos_a = _play(F1RaceEnv(CIRCUIT, ERA, twin=trace), ACTIONS)
    frames_b, infos_b = _play(F1RaceEnv(CIRCUIT, ERA, twin=trace), ACTIONS)

    assert np.array_equal(frames_a, frames_b)
    assert infos_a[-1]["race_time_s"] == infos_b[-1]["race_time_s"]


def test_events_on_the_twin_do_not_shift_when_the_ego_strategy_changes():
    trace = _record_trace(STALL)

    _, infos_stall = _play(F1RaceEnv(CIRCUIT, ERA, twin=trace), STALL)
    _, infos_stop = _play(F1RaceEnv(CIRCUIT, ERA, twin=trace), STOP_EARLY)

    # both ego strategies run the full distance, so the two info streams align lap for lap
    for stall_lap, stop_lap in zip(infos_stall, infos_stop, strict=True):
        assert stall_lap["track_status"] == stop_lap["track_status"]
        assert stall_lap["events"]["weather"] == stop_lap["events"]["weather"]
        assert stall_lap["events"]["wetness"] == stop_lap["events"]["wetness"]


def test_the_twin_zeroes_noise_and_collapses_service_to_the_mean():
    recorder = F1RaceEnv(CIRCUIT, ERA, record=True)
    frames_origin, _ = _play(recorder, ACTIONS)
    trace = recorder.recorded_trace()

    frames_twin_a, _ = _play(F1RaceEnv(CIRCUIT, ERA, twin=trace), ACTIONS)
    frames_twin_b, _ = _play(F1RaceEnv(CIRCUIT, ERA, twin=trace), ACTIONS)

    # zeroed noise and mean service make the twin roll reproducible ...
    assert np.array_equal(frames_twin_a, frames_twin_b)
    # ... and that removal moves it off the noisy episode it was captured from
    assert not np.array_equal(frames_origin, frames_twin_a)


def test_a_synthetic_green_trace_runs_an_all_green_dry_race():
    reference = F1RaceEnv(CIRCUIT, ERA)
    n_cars = reference.n_cars
    trace = EventTrace.green(
        CIRCUIT, ERA, reference.total_laps, n_cars, grid=np.arange(1, n_cars + 1)
    )

    _, infos = _play(F1RaceEnv(CIRCUIT, ERA, twin=trace), [[0, 1]] * (reference.total_laps + 5))

    for info in infos:
        assert info["track_status"] == "green"
        assert info["events"]["wetness"] == 0.0


def test_a_trace_survives_the_npz_round_trip(tmp_path):
    trace = _record_trace(ACTIONS)
    path = tmp_path / "trace.npz"
    trace.save_npz(path)
    reloaded = EventTrace.from_npz(path)

    assert reloaded.circuit == trace.circuit
    assert reloaded.era == trace.era
    assert reloaded.seed == trace.seed
    assert reloaded.n_laps == trace.n_laps
    assert reloaded.n_cars == trace.n_cars
    for field in (
        "grid", "driver_s", "status", "red_flag", "weather",
        "wetness", "failed", "rival_pit", "rival_mode",
    ):
        assert np.array_equal(getattr(reloaded, field), getattr(trace, field))


def test_recorded_trace_refuses_an_incomplete_record():
    # a race that stopped short of the flag would leave a green-tailed twin; refuse it
    # rather than hand back a trace that silently misrepresents the events (M3)
    env = F1RaceEnv(CIRCUIT, ERA, record=True)
    env.reset(seed=SEED)
    for _ in range(5):
        env.step(np.array([0, 1]))

    with pytest.raises(RuntimeError):
        env.recorded_trace()


def test_terminal_info_reports_the_ego_race_time():
    env = F1RaceEnv(CIRCUIT, ERA)
    env.reset(seed=SEED)
    terminated = False
    info = {}
    while not terminated:
        _, _, terminated, _, info = env.step(np.array([0, 1]))

    assert "race_time_s" in info
    race_time_s = info["race_time_s"]
    assert isinstance(race_time_s, float)
    assert np.isfinite(race_time_s)
    # the ego clock only advances, so a whole race must outrun any single reference lap
    assert race_time_s > env.scenario.t_ref_s > 0.0
