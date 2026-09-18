"""The F10 integration test: POST /simulations runs the race inline, stores frames and
cards -> read back over the 5.9.2 endpoints. The round trip runs the real frozen triplet
with TreeSHAP every lap, so it carries the slow marker; the request-validation tests stay
fast because they are refused at POST before any race starts.
"""

import json
import os

import pytest

from senna import config
from tests.api.conftest import CIRCUIT, SEED, create_and_drain

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
    ),
]

HEADLINE_MANIFEST = config.REPO_ROOT / "models" / "headline" / "manifest.json"


@pytest.mark.slow
@pytest.mark.skipif(not HEADLINE_MANIFEST.is_file(), reason="needs the baked headline triplet")
def test_post_drain_and_read_back_the_whole_round_trip(client, fresh_schema):
    run_id = create_and_drain(client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED})

    run = client.get(f"/api/v1/simulations/{run_id}").json()
    assert run["status"] == "complete"
    assert run["seed"] == SEED  # echoed back for reproducibility (5.9.2)
    assert run["circuit_id"] == CIRCUIT
    assert run["era"] == "2026"
    # model_version None resolved to the served version, never left blank
    baked = json.loads(HEADLINE_MANIFEST.read_text())["model_version"]
    assert run["model_version"] == baked

    race_laps = config.load("circuits")[CIRCUIT]["race_laps"]
    frames = client.get(f"/api/v1/simulations/{run_id}/frames").json()
    assert [frame["lap"] for frame in frames] == list(range(1, race_laps + 1))

    page = client.get(
        f"/api/v1/simulations/{run_id}/frames", params={"from_lap": 10, "to_lap": 19}
    ).json()
    assert [frame["lap"] for frame in page] == list(range(10, 20))

    decisions = client.get(f"/api/v1/simulations/{run_id}/decisions").json()
    assert decisions  # one card per lap, TreeSHAP top-k included (5.8.2)
    assert all(card["honesty"]["model_version"] == baked for card in decisions)


def test_a_missing_seed_is_drawn_server_side_and_echoed(client, fresh_schema):
    accepted = client.post("/api/v1/simulations", json={"circuit_id": CIRCUIT, "grid_position": 5})
    assert accepted.status_code < 300, accepted.text
    run = client.get(f"/api/v1/simulations/{accepted.json()['run_id']}").json()
    # drawn before the cache key is built, so the echoed seed is the one that will run
    assert isinstance(run["seed"], int)


def test_an_unknown_circuit_is_a_404(client, fresh_schema):
    response = client.post(
        "/api/v1/simulations", json={"circuit_id": "nowhere_grand_prix", "grid_position": 5}
    )
    assert response.status_code == 404


def test_a_2024_grid_slot_beyond_the_20_car_field_is_a_422(client, fresh_schema):
    # physics_2024 fields 20 cars; grid_position must respect the era, not the 2026 bound
    body = {"circuit_id": CIRCUIT, "era": "2024", "grid_position": 21}
    assert client.post("/api/v1/simulations", json=body).status_code == 422


def test_an_unknown_model_version_is_refused_at_post(client, fresh_schema):
    body = {"circuit_id": CIRCUIT, "grid_position": 5,
            "model_version": "senna-ppo-000000000000-A-00000000"}
    response = client.post("/api/v1/simulations", json=body)
    # E-15: a version with no baked manifest fails loudly, never falls back silently
    assert 400 <= response.status_code < 500


@pytest.mark.skipif(not HEADLINE_MANIFEST.is_file(), reason="needs the baked headline triplet")
def test_the_baked_model_version_is_accepted_explicitly(client, fresh_schema):
    baked = json.loads(HEADLINE_MANIFEST.read_text())["model_version"]
    body = {"circuit_id": CIRCUIT, "grid_position": 5, "model_version": baked, "seed": SEED}
    assert client.post("/api/v1/simulations", json=body).status_code < 300


def test_the_requested_weather_profile_is_echoed_verbatim(client, fresh_schema):
    # mixed and wet_risk both map onto the markov weather engine (plan Q2); the recorded
    # profile must stay distinct or the mapping limitation becomes invisible
    for offset, profile in enumerate(("mixed", "wet_risk")):
        body = {"circuit_id": CIRCUIT, "grid_position": 5, "weather_profile": profile,
                "seed": SEED + offset}
        accepted = client.post("/api/v1/simulations", json=body)
        assert accepted.status_code < 300, accepted.text
        run = client.get(f"/api/v1/simulations/{accepted.json()['run_id']}").json()
        assert run["config"]["weather_profile"] == profile
