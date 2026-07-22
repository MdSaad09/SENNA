"""Shared fixtures for the F10 serving-API suite. Suite seed 1105 keeps it apart from
fits (99), synth (271), env (512), strategy (704), train (846) and explain (933), so a
cross-suite coincidence cannot mask a bug (5.5.5). The app lifespan owns Postgres and
Redis, so `client` skips unless DATABASE_URL and REDIS_URL are both set (CI provides
service containers). Jobs drain in-process through rq's SimpleWorker, which imports
torch and xgboost — hence the OpenMP guard before anything heavy loads.
"""

import asyncio
import os

# arm64 landmine (F09 plan): torch and xgboost each bundle libomp, and two OpenMP
# runtimes in one process segfault — single-threaded OpenMP, set before either loads
os.environ.setdefault("OMP_NUM_THREADS", "1")

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

SEED = 1105
CIRCUIT = "bahrain_grand_prix"  # a raced 2026 event with real fitted params in configs

RACE_SEASON = 2024
RACE_ROUND = 1
RACE_NAME = "Bahrain Grand Prix"

# the serving namespaces (configs/serving.yaml prefixes) plus rq's bookkeeping —
# never a blanket FLUSHDB on what may be a shared redis
_SERVING_KEY_PATTERNS = ("sim:*", "events:*", "rq:*")


def db_url() -> str:
    raw = os.environ["DATABASE_URL"]
    if "+asyncpg" in raw:
        return raw
    return raw.replace("postgresql://", "postgresql+asyncpg://")


def reset_schema() -> None:
    """Drop and recreate every table senna.data.schema declares — the tests/data
    pattern; the alembic migration itself is CI's `make migrate` concern."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from senna.data.schema import Base

    async def rebuild():
        engine = create_async_engine(db_url())
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(rebuild())


def flush_serving_keys() -> None:
    import redis

    conn = redis.Redis.from_url(os.environ["REDIS_URL"])
    for pattern in _SERVING_KEY_PATTERNS:
        keys = list(conn.scan_iter(match=pattern))
        if keys:
            conn.delete(*keys)
    conn.close()


def drain_queue() -> None:
    """Run every queued job to completion in this process (rq SimpleWorker, burst)."""
    import redis
    from rq import Queue, SimpleWorker

    from senna import config

    queue_name = config.load("serving")["queue"]["name"]
    conn = redis.Redis.from_url(os.environ["REDIS_URL"])
    SimpleWorker([Queue(queue_name, connection=conn)], connection=conn).work(burst=True)
    conn.close()


def create_and_drain(client, body: dict) -> int:
    """POST a simulation, run its job to completion, hand back the run id."""
    accepted = client.post("/api/v1/simulations", json=body)
    assert accepted.status_code < 300, accepted.text
    drain_queue()
    return accepted.json()["run_id"]


def seed_2024_bahrain() -> None:
    """Minimal ingested rows for one real 2024 race: enough for /races and the
    counterfactual year/round/driver lookup, nothing more."""
    from sqlalchemy import insert
    from sqlalchemy.ext.asyncio import create_async_engine

    from senna.data.schema import Event, Lap, Session, SessionResult

    async def seed():
        engine = create_async_engine(db_url())
        async with engine.begin() as conn:
            event_id = (
                await conn.execute(
                    insert(Event)
                    .values(
                        season=RACE_SEASON, round=RACE_ROUND, event_name=RACE_NAME,
                        event_format="conventional", event_date=datetime(2024, 3, 2),
                    )
                    .returning(Event.id)
                )
            ).scalar_one()
            session_id = (
                await conn.execute(
                    insert(Session)
                    .values(event_id=event_id, session_name="Race", is_dry=True)
                    .returning(Session.id)
                )
            ).scalar_one()
            await conn.execute(
                insert(SessionResult),
                [
                    {"session_id": session_id, "driver_abbrev": "VER",
                     "team_name": "Red Bull Racing", "grid_position": 1,
                     "position": 1, "status": "Finished", "points": 25.0},
                    {"session_id": session_id, "driver_abbrev": "HAM",
                     "team_name": "Mercedes", "grid_position": 5,
                     "position": 3, "status": "Finished", "points": 15.0},
                    {"session_id": session_id, "driver_abbrev": "ALO",
                     "team_name": "Aston Martin", "grid_position": 9,
                     "position": 8, "status": "Finished", "points": 4.0},
                ],
            )
            await conn.execute(
                insert(Lap),
                [
                    {"session_id": session_id, "driver": "VER", "driver_number": "1",
                     "lap_number": lap, "lap_time_s": 95.0 + 0.1 * lap,
                     "lap_time_imputed": False, "compound": "MEDIUM",
                     "tyre_life": float(lap), "position": 1, "era": "2024",
                     "source": "real_2024"}
                    for lap in (1, 2, 3)
                ],
            )
        await engine.dispose()

    asyncio.run(seed())


@pytest.fixture
def fresh_schema():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("needs Postgres; set DATABASE_URL (CI provides a service container)")
    reset_schema()


@pytest.fixture
def flush_redis():
    if not os.environ.get("REDIS_URL"):
        pytest.skip("needs Redis; set REDIS_URL (CI provides a service container)")
    flush_serving_keys()
    yield
    flush_serving_keys()


@pytest.fixture
def client():
    if not (os.environ.get("DATABASE_URL") and os.environ.get("REDIS_URL")):
        pytest.skip("the app lifespan owns Postgres and Redis; set DATABASE_URL and REDIS_URL")
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as running:
        yield running
