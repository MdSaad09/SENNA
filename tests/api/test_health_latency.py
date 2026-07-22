"""/health under load: the F10 spec's "a running simulation never blocks /health beyond
a stated threshold", measured directly — once against a live WS consumer and once with a
SimpleWorker mid-race in this process — never by proxy. The threshold is serving.yaml's
health.max_response_ms.
"""

import asyncio
import os
import threading
import time

import pytest

from senna import config
from tests.api.conftest import CIRCUIT, SEED, create_and_drain, drain_queue

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
    ),
    pytest.mark.skipif(
        not os.environ.get("REDIS_URL"),
        reason="needs Redis; set REDIS_URL (CI provides a service container)",
    ),
]


def _health_p95_ms(client, samples: int = 40) -> float:
    timings_ms = []
    for _ in range(samples):
        start = time.perf_counter()
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        timings_ms.append((time.perf_counter() - start) * 1_000)
    timings_ms.sort()
    return timings_ms[round(0.95 * (samples - 1))]


def test_health_reports_the_served_model_version(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["model_version"]  # 5.9.2: {status, model_version}, filled once F10 bakes it


@pytest.mark.slow
def test_health_p95_under_threshold_while_a_stream_is_consumed(client, fresh_schema,
                                                               flush_redis, monkeypatch):
    run_id = create_and_drain(client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED})

    async def paced_sleep(delay_s: float) -> None:
        await asyncio.sleep(0.01)  # steady frame churn without waiting out real laps

    monkeypatch.setattr(client.app.state, "playback_sleep", paced_sleep, raising=False)

    stop = threading.Event()

    def consume():
        # each pass replays the stored race end to end, so the thread always exits
        while not stop.is_set():
            with client.websocket_connect(f"/ws/simulations/{run_id}") as ws:
                while ws.receive_json()["type"] != "sim:complete":
                    pass

    consumer = threading.Thread(target=consume, daemon=True)
    consumer.start()
    try:
        p95_ms = _health_p95_ms(client)
    finally:
        stop.set()
        consumer.join(timeout=30)

    assert p95_ms <= config.load("serving")["health"]["max_response_ms"]


@pytest.mark.slow
def test_health_p95_under_threshold_while_a_job_is_mid_flight(client, fresh_schema,
                                                              flush_redis):
    accepted = client.post(
        "/api/v1/simulations", json={"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED + 1}
    )
    assert accepted.status_code < 300, accepted.text

    worker = threading.Thread(target=drain_queue, daemon=True)
    worker.start()
    try:
        # a full race with TreeSHAP every lap far outlasts one probe: the job is running
        assert worker.is_alive()
        p95_ms = _health_p95_ms(client)
    finally:
        worker.join(timeout=300)

    assert p95_ms <= config.load("serving")["health"]["max_response_ms"]
