"""Held-out loaders — the ONLY module that reads 2026 rounds 7+.

The frozen split calibrates on rounds 1-6 and validates on everything later
(E-14). Every calibration module refuses those rounds; validate.py imports this
one to read them, and nothing else may (the import boundary is tested). Keeping
the held-out reads in a single named place is what makes T8's sim-to-real
number a real out-of-sample measurement rather than a restated fit.
"""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from senna.data.schema import Event, Lap, OpenF1PitStop, Session
from senna.physics.fits.frames import circuit_slug
from senna.physics.synth.frames import FIRST_2026_SEASON


async def held_out_race_laps(conn: AsyncConnection, validation_rounds_from: int) -> pd.DataFrame:
    """Green race laps of 2026 rounds >= validation_rounds_from, per circuit."""
    stmt = (
        select(
            Event.event_name,
            Event.round,
            Lap.lap_number,
            Lap.compound,
            Lap.stint,
            Lap.lap_time_s,
            Lap.is_green,
            Lap.is_accurate,
        )
        .join(Session, Lap.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(
            Event.season == FIRST_2026_SEASON,
            Event.round >= validation_rounds_from,
            Session.session_name == "Race",
            Lap.source.like("real_%"),
        )
        .order_by(Event.round, Lap.session_id, Lap.lap_number)
    )
    frame = await _frame(conn, stmt)
    if not frame.empty:
        frame["slug"] = frame["event_name"].map(circuit_slug)
    return frame


async def held_out_pit_stops(conn: AsyncConnection, validation_rounds_from: int) -> pd.DataFrame:
    """OpenF1 pit durations for the held-out races — the pit-loss check (5.4.1)."""
    stmt = (
        select(Event.event_name, OpenF1PitStop.pit_duration_s)
        .join(Session, OpenF1PitStop.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(
            Event.season == FIRST_2026_SEASON,
            Event.round >= validation_rounds_from,
            Session.session_name == "Race",
        )
    )
    frame = await _frame(conn, stmt)
    if not frame.empty:
        frame["slug"] = frame["event_name"].map(circuit_slug)
    return frame


async def _frame(conn: AsyncConnection, stmt) -> pd.DataFrame:
    rows = (await conn.execute(stmt)).mappings().all()
    return pd.DataFrame(rows)
