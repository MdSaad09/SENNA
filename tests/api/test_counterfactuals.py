"""POST /counterfactuals: real era-matched replay plumbing (F-24) running the frozen
2026 model on 2024 physics, with the pending-F14 caveat recorded so loudly no consumer
can miss it (plan Q3).
"""

import os

import pytest

from tests.api.conftest import RACE_ROUND, RACE_SEASON, drain_queue, seed_2024_bahrain

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


def test_body_validation_requires_year_round_and_driver(client, fresh_schema, flush_redis):
    response = client.post("/api/v1/counterfactuals", json={"year": RACE_SEASON, "round": 1})
    assert response.status_code == 422


def test_an_unraced_event_is_a_404(client, fresh_schema, flush_redis):
    body = {"year": 2031, "round": 9, "driver": "VER"}
    assert client.post("/api/v1/counterfactuals", json=body).status_code == 404


def test_a_driver_not_in_the_results_is_a_404(client, fresh_schema, flush_redis):
    seed_2024_bahrain()
    body = {"year": RACE_SEASON, "round": RACE_ROUND, "driver": "ZZZ"}
    assert client.post("/api/v1/counterfactuals", json=body).status_code == 404


@pytest.mark.slow
def test_the_replay_runs_on_2024_physics_with_the_pending_caveat(client, fresh_schema,
                                                                 flush_redis):
    seed_2024_bahrain()
    accepted = client.post(
        "/api/v1/counterfactuals",
        json={"year": RACE_SEASON, "round": RACE_ROUND, "driver": "HAM"},
    )
    assert accepted.status_code < 300, accepted.text
    run_id = accepted.json()["run_id"]
    drain_queue()

    run = client.get(f"/api/v1/simulations/{run_id}").json()
    assert run["status"] == "complete"
    assert run["era"] == "2024"
    # Q3: the frozen 2026 model on 2024 physics until F14 delivers the era-matched model
    assert run["config"]["era_matched_model"] == "pending-F14"

    frames = client.get(f"/api/v1/simulations/{run_id}/frames").json()
    assert frames
    assert all(len(frame["cars"]) == 20 for frame in frames)  # physics_2024 grid_size
