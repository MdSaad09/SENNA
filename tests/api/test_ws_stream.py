"""Playback-clock streaming over /ws/simulations/{run_id} (5.9.3). The worker persisted
every frame before these tests connect, so the socket is a read-only replay: pause, seek
and reconnect are all reads against the same store (E-16). The stream's sleep comes from
app.state.playback_sleep, so no test waits out a real lap.
"""

import asyncio
import os
import time

import pytest

from senna import config
from tests.api.conftest import (
    CIRCUIT,
    RACE_ROUND,
    RACE_SEASON,
    SEED,
    create_and_drain,
    drain_queue,
    flush_serving_keys,
    reset_schema,
    seed_2024_bahrain,
)

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
    ),
    pytest.mark.skipif(
        not os.environ.get("REDIS_URL"),
        reason="needs Redis; set REDIS_URL (CI provides a service container)",
    ),
    pytest.mark.slow,
]

RACE_LAPS = config.load("circuits")[CIRCUIT]["race_laps"]

_EVENT_KINDS = {"sc", "vsc", "red", "weather", "pit"}
_MAX_MESSAGES = 10_000


class SleepRecorder:
    """Counts every inter-frame delay the server requests; sleeps for real only when
    a test needs the stream to stay interruptible."""

    def __init__(self, actual_s: float = 0.0):
        self.actual_s = actual_s
        self.delays = []

    async def __call__(self, delay_s: float) -> None:
        self.delays.append(delay_s)
        if self.actual_s:
            await asyncio.sleep(self.actual_s)


@pytest.fixture(scope="module")
def stream():
    """One completed run whose stored frames contain at least one race event, plus the
    client that owns it. Rival pit stops alone should satisfy the event requirement on
    the first seed; the loop is insurance against a freak eventless race."""
    if not (os.environ.get("DATABASE_URL") and os.environ.get("REDIS_URL")):
        pytest.skip("the app lifespan owns Postgres and Redis; set DATABASE_URL and REDIS_URL")
    from fastapi.testclient import TestClient

    from api.main import app

    reset_schema()
    flush_serving_keys()
    with TestClient(app) as client:
        for attempt in range(4):
            run_id = create_and_drain(
                client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED + attempt}
            )
            frames = client.get(f"/api/v1/simulations/{run_id}/frames").json()
            if any(frame["events"] for frame in frames):
                yield client, run_id
                return
        pytest.fail("four seeds without a single race event — rival pits alone should appear")


def _collect(ws):
    laps, events = [], []
    for _ in range(_MAX_MESSAGES):
        message = ws.receive_json()
        if message["type"] == "sim:complete":
            return laps, events, message
        if message["type"] == "sim:lap":
            laps.append(message)
        elif message["type"] == "sim:event":
            events.append(message)
    raise AssertionError("stream never sent sim:complete")


def test_the_full_stream_arrives_in_lap_order_and_ends_complete(stream, monkeypatch):
    client, run_id = stream
    monkeypatch.setattr(client.app.state, "playback_sleep", SleepRecorder(), raising=False)

    with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
        ws.send_json({"type": "client:speed", "speed": 30})
        laps, _, complete = _collect(ws)

    assert [m["frame"]["lap"] for m in laps] == list(range(1, RACE_LAPS + 1))
    assert all("card" in m for m in laps)  # sim:lap carries LapFrame + DecisionCard (5.9.3)
    assert any(m["card"] for m in laps)
    assert "summary" in complete


def test_race_events_are_pushed_as_sim_event_messages(stream, monkeypatch):
    client, run_id = stream
    monkeypatch.setattr(client.app.state, "playback_sleep", SleepRecorder(), raising=False)

    with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
        _, events, _ = _collect(ws)

    assert events  # the fixture picked a run whose stored frames contain an event
    assert all(message["kind"] in _EVENT_KINDS for message in events)


def test_seek_replays_from_the_requested_lap(stream, monkeypatch):
    client, run_id = stream
    # a real (tiny) delay keeps the server from outrunning the client's seek
    monkeypatch.setattr(client.app.state, "playback_sleep", SleepRecorder(0.02), raising=False)

    with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
        seen = 0
        for _ in range(_MAX_MESSAGES):
            if ws.receive_json()["type"] == "sim:lap":
                seen += 1
                if seen == 3:
                    break
        ws.send_json({"type": "client:seek", "lap": 2})
        laps, _, _ = _collect(ws)

    lap_numbers = [m["frame"]["lap"] for m in laps]
    # playback never revisits lap 2 on its own, so its reappearance is the seek working
    assert 2 in lap_numbers
    assert lap_numbers[lap_numbers.index(2):] == list(range(2, RACE_LAPS + 1))


def test_a_mid_stream_speed_change_takes_effect_immediately(stream, monkeypatch):
    client, run_id = stream
    recorder = SleepRecorder(0.02)  # real (tiny) delays so the switch lands mid-stream
    monkeypatch.setattr(client.app.state, "playback_sleep", recorder, raising=False)
    nominal = client.get(f"/api/v1/simulations/{run_id}").json()["summary"]["nominal_lap_s"]

    with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
        seen = 0
        for _ in range(_MAX_MESSAGES):
            if ws.receive_json()["type"] == "sim:lap":
                seen += 1
                if seen == 3:
                    break
        ws.send_json({"type": "client:speed", "speed": 30})
        _collect(ws)

    # started at the 1x default, ended at 30x — and the switch may not wait out an
    # in-flight 1x tick (at real speed that tick is a whole lap of wall clock)
    assert recorder.delays[0] == pytest.approx(nominal / 1)
    assert recorder.delays[-1] == pytest.approx(nominal / 30)


def test_pause_halts_the_playback_clock(stream, monkeypatch):
    client, run_id = stream
    recorder = SleepRecorder(0.02)
    monkeypatch.setattr(client.app.state, "playback_sleep", recorder, raising=False)

    with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
        assert ws.receive_json()["type"] in {"sim:lap", "sim:event"}
        ws.send_json({"type": "client:pause"})
        time.sleep(0.3)  # let frames already in flight settle
        ticks_at_pause = len(recorder.delays)
        time.sleep(0.3)  # ~15 frame periods at the patched delay
        assert len(recorder.delays) == ticks_at_pause  # no new frames while paused


def test_reconnect_after_a_drop_replays_with_zero_frames_lost(stream, monkeypatch):
    client, run_id = stream
    monkeypatch.setattr(client.app.state, "playback_sleep", SleepRecorder(), raising=False)

    with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
        for _ in range(5):
            ws.receive_json()
        # leaving the context is the dropped connection

    # E-16: frames live in Postgres, so a fresh socket replays the whole race
    with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
        laps, _, complete = _collect(ws)
    assert [m["frame"]["lap"] for m in laps] == list(range(1, RACE_LAPS + 1))
    assert complete["type"] == "sim:complete"


def test_a_baseline_run_streams_card_null_laps_and_a_normal_complete(stream, monkeypatch):
    # the F13 replay baseline stores frames but no cards — its socket must still be a
    # first-class stream: sim:lap every lap with card null (E-15 honesty, the same
    # empty state the card panel renders), then an ordinary sim:complete
    client, _ = stream
    seed_2024_bahrain()
    accepted = client.post(
        "/api/v1/counterfactuals",
        json={"year": RACE_SEASON, "round": RACE_ROUND, "driver": "HAM", "seed": SEED},
    )
    assert accepted.status_code == 202, accepted.text
    baseline_id = accepted.json()["baseline_run_id"]
    drain_queue()

    monkeypatch.setattr(client.app.state, "playback_sleep", SleepRecorder(), raising=False)
    with client.websocket_connect(f"/ws/simulations/{baseline_id}") as ws:
        ws.send_json({"type": "client:speed", "speed": 30})
        laps, _, complete = _collect(ws)

    assert laps
    assert [m["frame"]["lap"] for m in laps] == list(range(1, len(laps) + 1))
    assert all(m["card"] is None for m in laps)
    assert complete["type"] == "sim:complete"
    assert "summary" in complete
