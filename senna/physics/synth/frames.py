"""Postgres to pandas for the synthetic generator, calibration rounds only.

Every loader filters to the frozen calibration split at the door (E-14), and
the pure guard refuse_validation_rounds is the check the fitters share. The
held-out rounds live behind heldout.py, which only validate.py may import —
the boundary that keeps T8's sim-to-real number honest.
"""

import pandas as pd
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncConnection

from senna.data.schema import Event, Lap, Session
from senna.physics.fits.joint_pace import FIRST_2026_SEASON


def refuse_validation_rounds(laps: pd.DataFrame, calibration_rounds: list[int]) -> None:
    """Raise if any 2026 lap sits outside the calibration rounds (E-14)."""
    held_out = laps["season"].ge(FIRST_2026_SEASON) & ~laps["round"].isin(calibration_rounds)
    if held_out.any():
        rounds = sorted(laps.loc[held_out, "round"].unique())
        raise ValueError(
            f"2026 round(s) {', '.join(map(str, rounds))} are held-out validation "
            f"data — the frozen split calibrates on rounds {calibration_rounds} (E-14)"
        )


async def position_laps(
    conn: AsyncConnection, era: str, calibration_rounds: list[int]
) -> pd.DataFrame:
    """Race and sprint laps with positions for T7 pass extraction, one era.

    Sprints enter deliberately: T7 is a per-opportunity model, so a shorter
    session simply contributes fewer opportunities without biasing the fit,
    and 2026 sprint laps are scarce real passing evidence (unlike the per-race
    hazard counts, which exclude sprints for uneven exposure).
    """
    stmt = _held_in(
        select(
            Event.season,
            Event.round,
            Lap.session_id,
            Lap.driver,
            Lap.lap_number,
            Lap.position,
            Lap.lap_time_s,
            Lap.track_status,
            Lap.is_accurate,
            Lap.is_green,
            Lap.pit_in_time_s,
            Lap.pit_out_time_s,
        )
        .join(Session, Lap.session_id == Session.id)
        .join(Event, Session.event_id == Event.id)
        .where(Lap.era == era, Lap.source.like("real_%"))
        .order_by(Lap.session_id, Lap.lap_number, Lap.position),
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
