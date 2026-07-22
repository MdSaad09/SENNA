"""E-15 versioned caching as observed through the live API and Redis: a completed run's
entry is keyed by model_version + env_config_hash + scenario + seed, an identical
request returns the stored run, and the 7-day TTL backstops it all. The key builder's
pure behaviour lives in tests/serve/test_cache_key.py; this module checks what actually
lands in Redis.
"""

import json
import os

import pytest
import redis

from senna import config
from tests.api.conftest import CIRCUIT, SEED, create_and_drain

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

HEADLINE_MANIFEST = config.REPO_ROOT / "models" / "headline" / "manifest.json"


def _sim_keys() -> list[str]:
    conn = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    keys = sorted(conn.scan_iter(match="sim:*"))
    conn.close()
    return keys


@pytest.mark.slow
def test_an_identical_request_returns_the_cached_run(client, fresh_schema, flush_redis):
    body = {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED}
    first = create_and_drain(client, body)

    again = client.post("/api/v1/simulations", json=body)
    assert again.json()["run_id"] == first  # same scenario, same seed, same model: a hit


@pytest.mark.slow
def test_a_different_circuit_with_the_same_seed_is_a_fresh_run(client, fresh_schema, flush_redis):
    # the 5.9.3 key as written would collide here; the scenario digest keeps them apart
    first = create_and_drain(client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED})
    second = client.post(
        "/api/v1/simulations",
        json={"circuit_id": "italian_grand_prix", "grid_position": 5, "seed": SEED},
    )
    assert second.status_code < 300, second.text
    assert second.json()["run_id"] != first


@pytest.mark.slow
@pytest.mark.skipif(not HEADLINE_MANIFEST.is_file(), reason="needs the baked headline triplet")
def test_the_cache_key_names_the_served_model_and_env_hash(client, fresh_schema, flush_redis):
    create_and_drain(client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED})

    keys = _sim_keys()
    assert len(keys) == 1
    prefix, model_version, env_hash, _digest, seed = keys[0].split(":")
    manifest = json.loads(HEADLINE_MANIFEST.read_text())
    assert prefix == config.load("serving")["cache"]["key_prefix"]
    assert model_version == manifest["model_version"]  # E-15: a retrain can never hit this
    assert env_hash == manifest["fingerprint"]  # from the manifest, never recomputed at serve
    assert seed == str(SEED)


@pytest.mark.slow
def test_the_cache_entry_carries_the_seven_day_ttl(client, fresh_schema, flush_redis):
    create_and_drain(client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED})

    keys = _sim_keys()
    assert keys
    conn = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    ttl_s = conn.ttl(keys[0])
    conn.close()
    ttl_cap_s = config.load("serving")["cache"]["ttl_days"] * 86_400
    assert 1 <= ttl_s <= ttl_cap_s  # E-15's backstop, actually set on the key
