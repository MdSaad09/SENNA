"""Resumability and completeness against real Postgres transactions (E-12, E-13).

Schema comes from senna.data.schema.Base.metadata, not alembic — a fresh
drop/create per test is cheap and the migration itself is exercised in CI's
`make migrate` step, not here. asyncio.run inside sync tests keeps
pytest-asyncio out of the dependency set.
"""

import asyncio
import os

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from senna.data.checkpoints import IncompleteIngestError, assert_complete, mark_excluded
from senna.data.ingest import IngestError, run_ingest
from senna.data.schema import Base

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
)

COUNTED_TABLES = ("events", "sessions", "laps", "ingest_checkpoints")


class LoaderCrash(RuntimeError):
    """Stands in for a kill mid-ingest."""


def _db_url() -> str:
    raw = os.environ["DATABASE_URL"]
    if "+asyncpg" in raw:
        return raw
    return raw.replace("postgresql://", "postgresql+asyncpg://")


async def _fresh_schema(db_url: str) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _row_counts(db_url: str) -> dict[str, int]:
    engine = create_async_engine(db_url)
    counts = {}
    async with engine.connect() as conn:
        for table in COUNTED_TABLES:
            counts[table] = (
                await conn.execute(text(f"select count(*) from {table}"))
            ).scalar_one()
    await engine.dispose()
    return counts


def _race_sessions(rounds: list[int]) -> list[dict]:
    return [
        {
            "season": 2024,
            "round": r,
            "event_name": f"Event {r} Grand Prix",
            "session_name": "Race",
            "session_date_utc": pd.Timestamp("2024-03-03") + pd.Timedelta(days=14 * (r - 1)),
            "source": "fastf1",
            "era": "2024",  # era.first_2026_season (configs/ingest.yaml)
        }
        for r in rounds
    ]


def _steady_loader(make_laps):
    def load(session: dict) -> dict[str, pd.DataFrame]:
        return {"laps": make_laps([{}, {}, {}])}

    return load


def _crash_after(n_sessions: int, make_laps):
    calls = {"count": 0}

    def load(session: dict) -> dict[str, pd.DataFrame]:
        calls["count"] += 1
        if calls["count"] > n_sessions:
            raise LoaderCrash(f"killed after {n_sessions} sessions")
        return {"laps": make_laps([{}, {}, {}])}

    return load


def test_kill_mid_ingest_then_rerun_equals_a_clean_single_run(make_laps):
    db_url = _db_url()
    sessions = _race_sessions([1, 2, 3, 4])

    asyncio.run(_fresh_schema(db_url))
    asyncio.run(run_ingest(sessions, _steady_loader(make_laps), db_url))
    clean_counts = asyncio.run(_row_counts(db_url))
    asyncio.run(assert_complete(db_url, sessions))

    asyncio.run(_fresh_schema(db_url))
    try:
        asyncio.run(run_ingest(sessions, _crash_after(2, make_laps), db_url))
    except LoaderCrash:
        pass  # the simulated kill; run_ingest may instead record the failure and return
    asyncio.run(run_ingest(sessions, _steady_loader(make_laps), db_url))  # resume (E-12)

    assert asyncio.run(_row_counts(db_url)) == clean_counts
    asyncio.run(assert_complete(db_url, sessions))


def test_reingesting_the_same_sessions_is_idempotent(make_laps):
    db_url = _db_url()
    sessions = _race_sessions([1, 2])

    asyncio.run(_fresh_schema(db_url))
    asyncio.run(run_ingest(sessions, _steady_loader(make_laps), db_url))
    first_counts = asyncio.run(_row_counts(db_url))
    asyncio.run(run_ingest(sessions, _steady_loader(make_laps), db_url))

    assert asyncio.run(_row_counts(db_url)) == first_counts


def test_completeness_ignores_future_events_but_not_past_gaps(make_laps):
    db_url = _db_url()
    loaded = _race_sessions([1])
    asyncio.run(_fresh_schema(db_url))
    asyncio.run(run_ingest(loaded, _steady_loader(make_laps), db_url))

    # E-13: Madrid has no data until its weekend happens — never a missing session
    madrid = {
        "season": 2026,
        "round": 17,
        "event_name": "Madrid Grand Prix",
        "session_name": "Race",
        "session_date_utc": pd.Timestamp.now(tz="UTC").tz_convert(None) + pd.Timedelta(days=60),
        "source": "fastf1",
    }
    asyncio.run(assert_complete(db_url, loaded + [madrid]))

    past_gap = _race_sessions([2])
    with pytest.raises(IncompleteIngestError) as err:
        asyncio.run(assert_complete(db_url, loaded + past_gap))
    # the error names the missing (event, source, session) triple
    assert "Event 2 Grand Prix" in str(err.value)
    assert "fastf1" in str(err.value)
    assert "Race" in str(err.value)


def test_excluded_with_a_written_reason_satisfies_completeness(make_laps):
    db_url = _db_url()
    sessions = _race_sessions([1, 2])

    asyncio.run(_fresh_schema(db_url))
    asyncio.run(run_ingest(sessions[:1], _steady_loader(make_laps), db_url))
    asyncio.run(
        mark_excluded(db_url, sessions[1], reason="wet race, analysed separately (5.3.4)")
    )

    asyncio.run(assert_complete(db_url, sessions))


def test_a_crash_inside_the_write_transaction_leaves_no_partial_state(make_laps):
    # the headline checkpoint claim: loaded commits with the rows or not at all
    db_url = _db_url()
    sessions = _race_sessions([1, 2])

    def poisoned(session: dict) -> dict[str, pd.DataFrame]:
        frames = {"laps": make_laps([{}, {}, {}])}
        if session["round"] == 2:
            frames["bogus_table"] = make_laps([{}])  # blows up inside _write_session
        return frames

    asyncio.run(_fresh_schema(db_url))
    with pytest.raises(IngestError):
        asyncio.run(run_ingest(sessions, poisoned, db_url))

    counts = asyncio.run(_row_counts(db_url))
    assert counts["laps"] == 3  # round 1 only; round 2 rolled back wholesale
    assert counts["ingest_checkpoints"] == 1

    asyncio.run(run_ingest(sessions, _steady_loader(make_laps), db_url))  # resume
    assert asyncio.run(_row_counts(db_url))["laps"] == 6
    asyncio.run(assert_complete(db_url, sessions))


def test_fastf1_and_openf1_passes_share_a_session_row_without_clobbering(
    make_laps, make_weather, make_race_control
):
    db_url = _db_url()
    fastf1_pass = _race_sessions([1])

    def fastf1_like(session: dict) -> dict[str, pd.DataFrame]:
        session["missing_channels"] = ["DRS"]
        return {
            "laps": make_laps([{}, {}]),
            "weather": make_weather(rainfall=[False, False]),
            "race_control": make_race_control(flags=["GREEN", "CHEQUERED"]),
            "results": pd.DataFrame(
                [
                    {
                        "Abbreviation": "VER",
                        "TeamName": "Red Bull Racing",
                        "GridPosition": 1.0,
                        "Position": 1.0,
                        "Status": "Finished",
                        "Points": 25.0,
                    }
                ]
            ),
        }

    def openf1_like(session: dict) -> dict[str, pd.DataFrame]:
        session["openf1_session_key"] = 9999
        return {
            "openf1_pit_stops": pd.DataFrame(
                [{"driver_number": 1, "lap_number": None, "pit_duration": 21.5}]
            ),
            "openf1_stints": pd.DataFrame(
                [
                    {
                        "driver_number": 1,
                        "stint_number": 1,
                        "compound": "MEDIUM",
                        "lap_start": 1,
                        "lap_end": 2,
                        "tyre_age_at_start": 0,
                    }
                ]
            ),
        }

    asyncio.run(_fresh_schema(db_url))
    asyncio.run(run_ingest(fastf1_pass, fastf1_like, db_url))
    openf1_pass = [dict(s, source="openf1") for s in fastf1_pass]
    asyncio.run(run_ingest(openf1_pass, openf1_like, db_url))

    async def session_row():
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "select missing_channels, openf1_session_key, is_dry,"
                        " (select count(*) from sessions) as session_count,"
                        " (select count(*) from weather) as weather_count,"
                        " (select count(*) from race_control) as rc_count,"
                        " (select count(*) from results) as result_count,"
                        " (select count(*) from openf1_pit_stops) as pit_count,"
                        " (select count(*) from openf1_stints) as stint_count"
                        " from sessions"
                    )
                )
            ).one()
        await engine.dispose()
        return row

    row = asyncio.run(session_row())
    assert row.session_count == 1  # both passes upserted into one row
    assert row.openf1_session_key == 9999
    # the openf1 pass must not null out what the fastf1 pass learned
    assert row.missing_channels == ["DRS"]
    assert row.is_dry is True  # no rain, no red flag (5.3.4)
    assert (row.weather_count, row.rc_count, row.result_count) == (2, 2, 1)
    # the lap-less pit stop is kept, not silently dropped (F-14)
    assert (row.pit_count, row.stint_count) == (1, 1)


def test_an_exclusion_is_terminal_for_reruns(make_laps):
    # a rerun must not retry an excluded session — the retry would fail again
    # and overwrite the recorded decision with a plain failure
    db_url = _db_url()
    sessions = _race_sessions([1])

    asyncio.run(_fresh_schema(db_url))
    asyncio.run(mark_excluded(db_url, sessions[0], reason="no upstream data for this event"))

    def untouchable(session: dict) -> dict[str, pd.DataFrame]:
        raise AssertionError("run_ingest retried an excluded session")

    asyncio.run(run_ingest(sessions, untouchable, db_url))
    asyncio.run(assert_complete(db_url, sessions))
