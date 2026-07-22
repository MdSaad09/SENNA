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


def test_a_new_model_version_is_a_cache_miss(client, fresh_schema, flush_redis, monkeypatch):
    # E-15's whole point: deploying a retrained model must cold-start its own
    # namespace. No drain needed — the POST-time key already dedupes.
    body = {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED}
    first = client.post("/api/v1/simulations", json=body).json()["run_id"]
    assert client.post("/api/v1/simulations", json=body).json()["run_id"] == first

    import api.routes.simulations as simulations

    real_read = simulations.read_manifest

    def retrained(models_dir=None, version=None):
        manifest = dict(real_read(models_dir, version))
        manifest["model_version"] = manifest["model_version"] + "-retrain"
        manifest["fingerprint"] = "f" * 64
        return manifest

    monkeypatch.setattr(simulations, "read_manifest", retrained)
    assert client.post("/api/v1/simulations", json=body).json()["run_id"] != first


def test_a_stranded_key_for_a_dead_run_is_a_miss(client, fresh_schema, flush_redis):
    # a work horse killed hard never reaches _finish_redis: the row sticks at
    # "running" and the key would answer with the corpse for 7 days (review finding)
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import create_async_engine

    from senna.data.schema import SimulationRun
    from tests.api.conftest import db_url

    body = {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED}
    stuck = client.post("/api/v1/simulations", json=body).json()["run_id"]

    queue_cfg = config.load("serving")["queue"]
    beyond = timedelta(seconds=queue_cfg["stale_after_timeouts"] * queue_cfg["job_timeout_s"] + 60)
    # rows carry naive UTC (the persist convention) — local now() would be off by
    # the timezone and could land the backdate in the future
    long_ago = datetime.now(UTC).replace(tzinfo=None) - beyond

    async def strand():
        engine = create_async_engine(db_url())
        async with engine.begin() as conn:
            await conn.execute(
                update(SimulationRun).where(SimulationRun.id == stuck)
                .values(status="running", started_at=long_ago)
            )
        await engine.dispose()

    asyncio.run(strand())
    assert client.post("/api/v1/simulations", json=body).json()["run_id"] != stuck


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
