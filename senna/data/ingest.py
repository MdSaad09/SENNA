"""Bulk ingest orchestrator — resumable, idempotent, cache-first (E-12).

Writes are delete-and-reload per (session, source) in one transaction: the
checkpoint flips to loaded in the same commit as the rows, so any rerun is
either a no-op or a clean reload, never a duplicate. One bad session is
recorded as failed and skipped — hours of bulk ingest must survive a single
broken weekend.

Run it: python -m senna.data.ingest --seasons 2024 --source fastf1
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import delete, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from senna import config
from senna.data import checkpoints
from senna.data.cleaning import flag_green_laps
from senna.data.db import database_url, engine_for
from senna.data.quality import DropCount, render_report, report_path
from senna.data.schema import (
    Event,
    Lap,
    OpenF1PitStop,
    OpenF1Stint,
    RaceControlMessage,
    Session,
    SessionResult,
    WeatherSample,
)

log = logging.getLogger(__name__)


class IngestError(RuntimeError):
    pass


def _seconds(value) -> float | None:
    return None if pd.isna(value) else float(value.total_seconds())


def _float(value) -> float | None:
    return None if pd.isna(value) else float(value)


def _int(value) -> int | None:
    return None if pd.isna(value) else int(value)


def _str(value) -> str | None:
    return None if pd.isna(value) else str(value)


def _bool(value) -> bool | None:
    return None if pd.isna(value) else bool(value)


def _era(season: int) -> str:
    # which physics yaml governs the row: pre-2026 rows calibrate against
    # configs/physics_2024.yaml, 2026 rows against physics_2026.yaml
    return "2026" if season >= 2026 else "2024"


def _lap_rows(frame: pd.DataFrame, session_id: int, session: dict) -> list[dict]:
    flagged, _ = flag_green_laps(frame)  # store the derived flag, keep every row (5.3.4)
    era = _era(session["season"])
    source = f"real_{session['season']}"
    return [
        {
            "session_id": session_id,
            "driver": _str(row.get("Driver")),
            "driver_number": str(row["DriverNumber"]),
            "team": _str(row.get("Team")),
            "lap_number": int(row["LapNumber"]),
            "stint": _int(row.get("Stint")),
            "compound": _str(row.get("Compound")),
            "tyre_life": _float(row.get("TyreLife")),
            "fresh_tyre": _bool(row.get("FreshTyre")),
            "lap_time_s": _seconds(row.get("LapTime")),
            "lap_time_imputed": False,
            "sector1_s": _seconds(row.get("Sector1Time")),
            "sector2_s": _seconds(row.get("Sector2Time")),
            "sector3_s": _seconds(row.get("Sector3Time")),
            "speed_st_kmh": _float(row.get("SpeedST")),
            "position": _int(row.get("Position")),
            "track_status": _str(row.get("TrackStatus")),
            "is_accurate": _bool(row.get("IsAccurate")),
            "is_green": bool(row["is_green"]),
            "pit_in_time_s": _seconds(row.get("PitInTime")),
            "pit_out_time_s": _seconds(row.get("PitOutTime")),
            "lap_start_time_s": _seconds(row.get("LapStartTime")),
            "era": era,
            "source": source,
        }
        for row in flagged.to_dict("records")
    ]


def _weather_rows(frame: pd.DataFrame, session_id: int, session: dict) -> list[dict]:
    return [
        {
            "session_id": session_id,
            "time_s": _seconds(row["Time"]),
            "air_temp_c": _float(row.get("AirTemp")),
            "track_temp_c": _float(row.get("TrackTemp")),
            "humidity_pct": _float(row.get("Humidity")),
            "rainfall": _bool(row.get("Rainfall")),
            "wind_speed_ms": _float(row.get("WindSpeed")),
        }
        for row in frame.to_dict("records")
    ]


def _race_control_rows(frame: pd.DataFrame, session_id: int, session: dict) -> list[dict]:
    return [
        {
            "session_id": session_id,
            "time_utc": None if pd.isna(row.get("Time")) else row["Time"].to_pydatetime(),
            "category": _str(row.get("Category")),
            "flag": _str(row.get("Flag")),
            "status": _str(row.get("Status")),
            "message": _str(row.get("Message")),
            "lap": _int(row.get("Lap")),
        }
        for row in frame.to_dict("records")
    ]


def _result_rows(frame: pd.DataFrame, session_id: int, session: dict) -> list[dict]:
    return [
        {
            "session_id": session_id,
            "driver_abbrev": str(row["Abbreviation"]),
            "team_name": _str(row.get("TeamName")),
            "grid_position": _int(row.get("GridPosition")),
            "position": _int(row.get("Position")),
            "status": _str(row.get("Status")),
            "points": _float(row.get("Points")),
        }
        for row in frame.to_dict("records")
        if pd.notna(row.get("Abbreviation"))
    ]


def _pit_stop_rows(frame: pd.DataFrame, session_id: int, session: dict) -> list[dict]:
    return [
        {
            "session_id": session_id,
            "driver_number": int(row["driver_number"]),
            "lap_number": int(row["lap_number"]),
            "pit_duration_s": _float(row.get("pit_duration")),
        }
        for row in frame.to_dict("records")
        if pd.notna(row.get("lap_number"))
    ]


def _stint_rows(frame: pd.DataFrame, session_id: int, session: dict) -> list[dict]:
    return [
        {
            "session_id": session_id,
            "driver_number": int(row["driver_number"]),
            "stint_number": int(row["stint_number"]),
            "compound": _str(row.get("compound")),
            "lap_start": _int(row.get("lap_start")),
            "lap_end": _int(row.get("lap_end")),
            "tyre_age_at_start": _int(row.get("tyre_age_at_start")),
        }
        for row in frame.to_dict("records")
    ]


TABLES = {
    "laps": Lap,
    "weather": WeatherSample,
    "race_control": RaceControlMessage,
    "results": SessionResult,
    "openf1_pit_stops": OpenF1PitStop,
    "openf1_stints": OpenF1Stint,
}

CONVERTERS = {
    "laps": _lap_rows,
    "weather": _weather_rows,
    "race_control": _race_control_rows,
    "results": _result_rows,
    "openf1_pit_stops": _pit_stop_rows,
    "openf1_stints": _stint_rows,
}


async def run_ingest(sessions: list[dict], loader, db_url: str) -> None:
    """loader(session) -> dict of table name to frame; it may stash
    missing_channels / openf1 keys on the session dict for the sessions row."""
    engine = engine_for(db_url)
    try:
        states = await checkpoints.states_by_key(engine)
        for session in sessions:
            if states.get(checkpoints.key_of(session)) == checkpoints.LOADED:
                continue
            try:
                frames = loader(session)
            except Exception as err:
                # recorded, skipped, retried on the next run — never fatal to the batch
                log.warning("%s %s failed: %r", session["event_name"], session["session_name"], err)
                async with engine.begin() as conn:
                    await checkpoints.upsert_state(
                        conn, session, checkpoints.FAILED, error=repr(err)
                    )
                continue
            await _write_session(engine, session, frames)
    finally:
        await engine.dispose()


async def _write_session(engine: AsyncEngine, session: dict, frames: dict) -> None:
    async with engine.begin() as conn:
        event_id = await _upsert_event(conn, session)
        session_id = await _upsert_session(conn, event_id, session)
        rows_loaded = 0
        for table_name, frame in frames.items():
            if table_name not in TABLES:
                raise IngestError(f"loader returned unknown table '{table_name}'")
            rows = CONVERTERS[table_name](frame, session_id, session)
            await conn.execute(_delete_stale(table_name, session_id, session))
            if rows:
                await conn.execute(insert(TABLES[table_name]), rows)
                rows_loaded += len(rows)
        await checkpoints.upsert_state(
            conn, session, checkpoints.LOADED, rows_loaded=rows_loaded
        )


def _delete_stale(table_name: str, session_id: int, session: dict):
    model = TABLES[table_name]
    stmt = delete(model).where(model.session_id == session_id)
    if table_name == "laps":
        # synthetic_2026 rows will share the table later; only this source reloads
        stmt = stmt.where(model.source == f"real_{session['season']}")
    return stmt


async def _upsert_event(conn: AsyncConnection, session: dict) -> int:
    await conn.execute(
        pg_insert(Event)
        .values(
            season=session["season"],
            round=session["round"],
            event_name=session["event_name"],
            event_format=session.get("event_format"),
            event_date=_naive(session.get("event_date")),
        )
        .on_conflict_do_nothing(index_elements=["season", "round"])
    )
    return (
        await conn.execute(
            select(Event.id).where(
                Event.season == session["season"], Event.round == session["round"]
            )
        )
    ).scalar_one()


async def _upsert_session(conn: AsyncConnection, event_id: int, session: dict) -> int:
    stmt = pg_insert(Session).values(
        event_id=event_id,
        session_name=session["session_name"],
        session_date_utc=_naive(session.get("session_date_utc")),
    )
    # only overwrite what this pass actually knows: the fastf1 pass brings the
    # channel probe, the openf1 pass brings its keys — neither may null the other's
    refresh = {"session_date_utc": stmt.excluded.session_date_utc}
    if "missing_channels" in session:
        stmt = stmt.values(missing_channels=session["missing_channels"])
        refresh["missing_channels"] = stmt.excluded.missing_channels
    if "openf1_session_key" in session:
        stmt = stmt.values(
            openf1_session_key=session["openf1_session_key"],
            openf1_meeting_key=session.get("openf1_meeting_key"),
        )
        refresh["openf1_session_key"] = stmt.excluded.openf1_session_key
        refresh["openf1_meeting_key"] = stmt.excluded.openf1_meeting_key
    stmt = stmt.on_conflict_do_update(
        index_elements=["event_id", "session_name"], set_=refresh
    )
    await conn.execute(stmt)
    return (
        await conn.execute(
            select(Session.id).where(
                Session.event_id == event_id,
                Session.session_name == session["session_name"],
            )
        )
    ).scalar_one()


def _naive(value):
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_pydatetime()


async def write_season_report(engine: AsyncEngine, season: int, report_dir: str) -> None:
    completeness = await _completeness_rows(engine, season)
    drop_counts = await _season_drop_counts(engine, season)
    channel_gaps = await _channel_gaps(engine, season)
    text = render_report(
        season=season,
        completeness=completeness,
        drop_counts=drop_counts,
        missing_channels=channel_gaps,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    path = report_path(season, report_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    log.info("wrote %s", path)


async def _completeness_rows(engine: AsyncEngine, season: int) -> list[dict]:
    from senna.data.schema import IngestCheckpoint as CP

    async with engine.connect() as conn:
        rows = await conn.execute(
            select(CP)
            .where(CP.season == season)
            .order_by(CP.round, CP.source, CP.session_name)
        )
    return [
        {
            "event": r.event_name or f"round {r.round}",
            "session": r.session_name,
            "source": r.source,
            "state": r.state,
            "reason": r.excluded_reason or r.error or "",
        }
        for r in rows.scalars()
    ]


async def _season_drop_counts(engine: AsyncEngine, season: int) -> list[DropCount]:
    """Counts per rule over the stored season — what a fit would exclude (5.3.4).

    Each rule is counted against all stored laps, not chained after the
    previous rule, so a report line answers "how much does this rule cost".
    """
    from sqlalchemy import func

    stmt = (
        select(
            func.count().label("rows_in"),
            func.count().filter(Lap.is_accurate.is_(False)).label("not_accurate"),
            func.count()
            .filter(or_(Lap.pit_in_time_s.is_not(None), Lap.pit_out_time_s.is_not(None)))
            .label("in_out"),
            func.count().filter(Lap.is_green.is_(False)).label("not_green"),
            func.count().filter(Lap.lap_time_s.is_(None)).label("no_lap_time"),
        )
        .select_from(Lap)
        .join(Session, Lap.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(Event.season == season)
    )
    async with engine.connect() as conn:
        totals = (await conn.execute(stmt)).one()
    n = totals.rows_in
    return [
        DropCount("is_accurate", n, totals.not_accurate, 0),
        DropCount("in_out_laps", n, totals.in_out, 0),
        DropCount("is_green", n, 0, totals.not_green),
        DropCount("lap_time_nat", n, 0, totals.no_lap_time),
    ]


async def _channel_gaps(engine: AsyncEngine, season: int) -> dict[str, list[str]]:
    stmt = (
        select(Event.event_name, Session.session_name, Session.missing_channels)
        .join(Session, Session.event_id == Event.id)
        .where(Event.season == season, Session.missing_channels.is_not(None))
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(stmt)).all()
    return {
        f"{event} — {session_name}": channels
        for event, session_name, channels in rows
        if channels
    }


def _cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SENNA bulk data ingest (F01)")
    parser.add_argument("--seasons", type=int, nargs="+", default=None)
    parser.add_argument("--source", choices=["fastf1", "openf1", "all"], default="all")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="regenerate quality reports and completeness from the database, no fetching",
    )
    return parser


async def _amain(args: argparse.Namespace) -> None:
    from senna.data import fastf1_loader
    from senna.data.openf1 import OpenF1Client

    cfg = config.load("ingest")
    db_url = database_url()
    seasons = args.seasons or config.get(cfg, "seasons")
    first_openf1 = config.get(cfg, "openf1.first_season")

    fastf1_loader.enable_cache(config.get(cfg, "fastf1.cache_dir"))
    session_types = config.get(cfg, "fastf1.sessions_to_ingest")

    expected: list[dict] = []
    for season in seasons:
        schedule = fastf1_loader.fetch_schedule(season)
        events = {
            row["RoundNumber"]: row
            for _, row in schedule.iterrows()
        }
        planned = [
            {
                "season": season,
                "round": p["round"],
                "event_name": p["event_name"],
                "session_name": p["session_name"],
                "session_date_utc": p["session_date_utc"],
                "event_format": events[p["round"]]["EventFormat"],
                "event_date": events[p["round"]]["EventDate"],
            }
            for p in fastf1_loader.plan_sessions(schedule, session_types)
        ]
        fastf1_sessions = [dict(p, source="fastf1") for p in planned]
        openf1_sessions = (
            [dict(p, source="openf1") for p in planned] if season >= first_openf1 else []
        )
        expected += fastf1_sessions + openf1_sessions

        if args.report_only:
            continue
        if args.source in ("fastf1", "all"):
            await run_ingest(fastf1_sessions, _fastf1_session_loader, db_url)
        if args.source in ("openf1", "all") and openf1_sessions:
            client = OpenF1Client(config.get(cfg, "openf1"))
            loader = _openf1_session_loader(client, season)
            await run_ingest(openf1_sessions, loader, db_url)

    engine = engine_for(db_url)
    try:
        for season in seasons:
            await write_season_report(engine, season, config.get(cfg, "quality.report_dir"))
    finally:
        await engine.dispose()

    await checkpoints.assert_complete(db_url, _due(expected))


def _due(expected: list[dict]) -> list[dict]:
    # E-13: only sessions whose date has passed are expected — Madrid appears
    # in the plan today but is not owed data until its September weekend
    now = datetime.now(UTC).replace(tzinfo=None)
    return [s for s in expected if pd.notna(s["session_date_utc"]) and s["session_date_utc"] < now]


def _fastf1_session_loader(session: dict) -> dict[str, pd.DataFrame]:
    from senna.data import fastf1_loader

    frames, missing = fastf1_loader.load_session_frames(
        session["season"], session["round"], session["session_name"]
    )
    session["missing_channels"] = missing
    return frames


def _openf1_session_loader(client, season: int):
    key_by_date_and_name: dict[tuple, dict] = {}

    def load(session: dict) -> dict[str, pd.DataFrame]:
        if not key_by_date_and_name:
            for row in client.get("sessions", year=season):
                day = str(row.get("date_start", ""))[:10]
                key_by_date_and_name[(day, row.get("session_name"))] = row
        day = str(session["session_date_utc"])[:10]
        match = key_by_date_and_name.get((day, session["session_name"]))
        if match is None:
            raise IngestError(
                f"openf1 /sessions has no {session['session_name']} on {day} — "
                "if it is genuinely absent upstream, mark_excluded with a reason"
            )
        session["openf1_session_key"] = match["session_key"]
        session["openf1_meeting_key"] = match.get("meeting_key")
        return {
            "openf1_pit_stops": pd.DataFrame(client.pit(session_key=match["session_key"])),
            "openf1_stints": pd.DataFrame(client.stints(session_key=match["session_key"])),
        }

    return load


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_amain(_cli().parse_args(argv)))


if __name__ == "__main__":
    main()
