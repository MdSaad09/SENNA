"""/health under load: the F10 spec's "a running simulation never blocks /health beyond
a stated threshold", measured directly rather than by proxy. The threshold is
serving.yaml's health.max_response_ms.

This matters more on this branch than it did on the queued one. There, a race ran in
another process and could not block the API whatever it did. Here it runs inside the
request that asked for it, so the only thing keeping /health responsive is that the
racing happens on a thread (run_in_threadpool) instead of on the event loop. That is a
one-line property and exactly the kind that gets refactored away, so it is measured.
"""

import os
import threading
import time

import pytest

from senna import config
from tests.api.conftest import CIRCUIT, SEED

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
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
def test_health_p95_under_threshold_while_a_race_is_running(client, fresh_schema):
    """POST a race from a thread and probe /health while it is still in the request."""
    done = threading.Event()

    def race():
        try:
            client.post("/api/v1/simulations",
                        json={"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED + 1})
        finally:
            done.set()

    runner = threading.Thread(target=race, daemon=True)
    runner.start()
    try:
        # a full race with TreeSHAP every lap far outlasts the probe window
        assert not done.is_set(), "the race finished before /health could be measured"
        p95_ms = _health_p95_ms(client)
    finally:
        runner.join(timeout=300)

    assert p95_ms <= config.load("serving")["health"]["max_response_ms"]
