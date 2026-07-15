"""Postgres to pandas for the fitting battery — the only fits module that
touches the database. Every query already excludes 2026 held-out rounds
(E-14): the frozen split is enforced at the door, and again inside the
fitters that take calibration_rounds.
"""

import pandas as pd
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncConnection

from senna.data.schema import Event, Lap, OpenF1PitStop, Session

FIRST_2026_SEASON = 2026

LAP_COLUMNS = (
    Event.season,
    Event.round,
    Lap.session_id,
    Lap.driver,
    Lap.lap_number,
    Lap.stint,
    Lap.compound,
    Lap.tyre_life,
    Lap.lap_time_s,
    Lap.track_status,
    Lap.is_accurate,
    Lap.is_green,
    Lap.pit_in_time_s,
    Lap.pit_out_time_s,
)


def circuit_slug(event_name: str) -> str:
    return event_name.lower().replace(" ", "_")


async def circuit_index(conn: AsyncConnection, calibration_rounds: list[int]) -> pd.DataFrame:
    """One row per race/sprint session: the work list every fit iterates."""
    stmt = _held_in(
        select(
            Event.season,
            Event.round,
            Event.event_name,
            Session.id.label("session_id"),
            Session.session_name,
            Session.is_dry,
            Lap.era,
        )
        .join(Session, Session.event_id == Event.id)
        .join(Lap, Lap.session_id == Session.id)
        .distinct()
        .order_by(Event.season, Event.round, Session.id),
        calibration_rounds,
    )
    frame = await _frame(conn, stmt)
    frame["slug"] = frame["event_name"].map(circuit_slug)
    return frame


async def pace_laps(
    conn: AsyncConnection, event_name: str, era: str, calibration_rounds: list[int]
) -> pd.DataFrame:
    """Dry race and sprint laps for one circuit-era — the E-10 fit input.

    The dry gate is is_dry IS TRUE: sessions whose weather never landed
    (is_dry null) stay out of dry fits rather than sneaking in (5.3.4).
    """
    stmt = _held_in(
        select(*LAP_COLUMNS)
        .join(Session, Lap.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(
            Event.event_name == event_name,
            Lap.era == era,
            Lap.source.like("real_%"),
            Session.is_dry.is_(True),
        )
        # a stable order keeps float summation identical run to run, which is
        # what lets a make fit rerun render byte-identically
        .order_by(Lap.session_id, Lap.driver, Lap.lap_number),
        calibration_rounds,
    )
    return await _frame(conn, stmt)


async def hazard_laps(
    conn: AsyncConnection, event_name: str, calibration_rounds: list[int]
) -> pd.DataFrame:
    """Race laps of every season for one circuit, wet included — event rates
    are a circuit property and interventions cluster in bad weather."""
    stmt = _held_in(
        select(Lap.session_id, Lap.lap_number, Lap.track_status, Lap.lap_time_s, Lap.is_green)
        .join(Session, Lap.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(
            Event.event_name == event_name,
            Session.session_name == "Race",
            Lap.source.like("real_%"),
        )
        .order_by(Lap.session_id, Lap.driver, Lap.lap_number),
        calibration_rounds,
    )
    return await _frame(conn, stmt)


async def status_laps(
    conn: AsyncConnection, era: str, calibration_rounds: list[int]
) -> pd.DataFrame:
    """All race laps of one era, for the pooled SC/VSC pace multipliers."""
    stmt = _held_in(
        select(Lap.lap_time_s, Lap.track_status, Lap.is_green)
        .join(Session, Lap.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(
            Session.session_name == "Race",
            Lap.era == era,
            Lap.source.like("real_%"),
        )
        .order_by(Lap.session_id, Lap.driver, Lap.lap_number),
        calibration_rounds,
    )
    return await _frame(conn, stmt)


async def pit_stops(
    conn: AsyncConnection, event_name: str, calibration_rounds: list[int]
) -> pd.DataFrame:
    stmt = _held_in(
        select(Event.season, OpenF1PitStop.lap_number, OpenF1PitStop.pit_duration_s)
        .join(Session, OpenF1PitStop.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(Event.event_name == event_name, Session.session_name == "Race")
        .order_by(OpenF1PitStop.session_id, OpenF1PitStop.driver_number, OpenF1PitStop.id),
        calibration_rounds,
    )
    return await _frame(conn, stmt)


async def race_control_messages(
    conn: AsyncConnection, event_name: str, calibration_rounds: list[int]
) -> pd.DataFrame:
    """Race-control text per race — the notebook's cross-check on track_status."""
    from senna.data.schema import RaceControlMessage

    stmt = _held_in(
        select(
            Event.season,
            RaceControlMessage.session_id,
            RaceControlMessage.category,
            RaceControlMessage.flag,
            RaceControlMessage.message,
        )
        .join(Session, RaceControlMessage.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(Event.event_name == event_name, Session.session_name == "Race")
        .order_by(RaceControlMessage.session_id, RaceControlMessage.id),
        calibration_rounds,
    )
    return await _frame(conn, stmt)


def _held_in(stmt: Select, calibration_rounds: list[int]) -> Select:
    # E-14: 2026 rounds outside the frozen calibration list never reach a fitter
    return stmt.where(
        (Event.season < FIRST_2026_SEASON) | Event.round.in_(calibration_rounds)
    )


async def _frame(conn: AsyncConnection, stmt: Select) -> pd.DataFrame:
    rows = (await conn.execute(stmt)).mappings().all()
    return pd.DataFrame(rows)
