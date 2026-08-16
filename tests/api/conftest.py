"""Shared fixtures for the F10 serving-API suite. Suite seed 1105 keeps it apart from
fits (99), synth (271), env (512), strategy (704), train (846) and explain (933), so a
cross-suite coincidence cannot mask a bug (5.5.5). The app lifespan owns Postgres and
so `client` skips unless DATABASE_URL is set (CI provides
service containers). Jobs drain in-process through rq's SimpleWorker, which imports
torch and xgboost — hence the OpenMP guard before anything heavy loads.

Running these with the compose stack UP needs an isolated queue: the live worker
consumes the same rq queue name and would steal test jobs into the wrong database.
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

# HAM's seeded race carries stints so the F13 real-strategy extraction has something
# real to read: three stints over the full 57 laps — the same distance as the sim's
# bahrain scenario, so the extracted plan is an identity rescale of these out-laps
HAM_STINTS = ((17, "SOFT"), (20, "HARD"), (20, "HARD"))
HAM_REAL_STOPS = [[18, "HARD"], [38, "HARD"]]  # the out-lap and compound of stints 2 and 3

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
    pattern; the alembic migration itself is CI's `make migrate` concern.

    require_disposable is the reason this cannot silently eat the ingested store: it
    refuses any database not named as disposable, which is the mistake that cost the
    real one three times."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from senna.data.db import require_disposable
    from senna.data.schema import Base

    require_disposable(db_url())

    async def rebuild():
        engine = create_async_engine(db_url())
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(rebuild())



def drain_queue() -> None:
    """A no-op kept so the tests read the same as before. There is no queue on this
    branch: POST /simulations races the run inside the request, so by the time the
    response arrives the work the drain used to do is already done."""


def all_run_rows() -> list[dict]:
    """Every simulation row, oldest first. Used where a run fails before its id reaches
    the client — inline execution raises through the request, so the rows are the only
    handle on what happened. Both legs of a pair are wanted and they carry different
    purposes, so this filters on nothing."""
    import asyncio

    from sqlalchemy import select

    from senna.data.db import database_url, engine_for
    from senna.data.schema import SimulationRun

    async def read() -> list[dict]:
        engine = engine_for(database_url())
        try:
            async with engine.connect() as conn:
                rows = (await conn.execute(
                    select(SimulationRun).order_by(SimulationRun.id)
                )).all()
            return [{"id": r.id, "status": r.status, "summary": r.summary} for r in rows]
        finally:
            await engine.dispose()

    return asyncio.run(read())


def create_and_drain(client, body: dict) -> int:
    """POST a simulation and hand back the run id; the race is finished on return."""
    accepted = client.post("/api/v1/simulations", json=body)
    assert accepted.status_code < 300, accepted.text
    return accepted.json()["run_id"]


def seed_2024_bahrain() -> None:
    """Minimal ingested rows for one real 2024 race: enough for /races, the
    counterfactual year/round/driver lookup and the F13 real-strategy extraction.
    HAM's laps carry stints; VER's stay stint-less on purpose (the extraction 404)."""
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
            # VER's laps carry no stint column — the F13 stint-less 404 case reads them
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
            ham_laps, lap = [], 1
            for stint_number, (stint_laps, compound) in enumerate(HAM_STINTS, start=1):
                for age in range(1, stint_laps + 1):
                    # pit_in_time_s is non-null only on the lap HAM peeled in — how a
                    # stint that ended in a stop is told apart from the chequered flag
                    boxed = age == stint_laps and stint_number < len(HAM_STINTS)
                    ham_laps.append(
                        {"session_id": session_id, "driver": "HAM", "driver_number": "44",
                         "lap_number": lap, "stint": stint_number, "compound": compound,
                         "tyre_life": float(age), "lap_time_s": 96.0 + 0.05 * lap,
                         "lap_time_imputed": False, "position": 3, "era": "2024",
                         "source": "real_2024",
                         "pit_in_time_s": 4200.0 + lap if boxed else None},
                    )
                    lap += 1
            await conn.execute(insert(Lap), ham_laps)
            # ALO's laps carry stints but no compounds — the F13 compound-less 404
            # case reads them (FastF1 drops compound on some historic loads too)
            await conn.execute(
                insert(Lap),
                [
                    {"session_id": session_id, "driver": "ALO", "driver_number": "14",
                     "lap_number": lap, "stint": 1 if lap <= 20 else 2, "compound": None,
                     "tyre_life": float(lap if lap <= 20 else lap - 20),
                     "lap_time_s": 96.5 + 0.05 * lap, "lap_time_imputed": False,
                     "position": 8, "era": "2024", "source": "real_2024",
                     "pit_in_time_s": 4300.0 if lap == 20 else None}
                    for lap in range(1, 58)
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
def client():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("the app lifespan owns Postgres; set DATABASE_URL")
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as running:
        yield running


@pytest.fixture
def stub_pair_runner(monkeypatch):
    """Replace the inline counterfactual race with a completion marker.

    Route tests are about routing — validation, 404s, the pairing linkage, which model
    the era-matched leg selects. Racing two grands prix inside each of them would make
    the suite unusable and would test the runner, which tests/serve already does at its
    own seams."""
    import asyncio

    from sqlalchemy import update

    import api.routes.counterfactuals as route
    from senna.data.db import database_url, engine_for
    from senna.data.schema import SimulationRun

    def complete(agent_id: int, baseline_id: int) -> None:
        async def mark() -> None:
            engine = engine_for(database_url())
            try:
                async with engine.begin() as conn:
                    await conn.execute(
                        update(SimulationRun)
                        .where(SimulationRun.id.in_((agent_id, baseline_id)))
                        .values(status="complete", summary={"stubbed": True})
                    )
            finally:
                await engine.dispose()

        asyncio.run(mark())

    monkeypatch.setattr(route, "run_counterfactual", complete)
