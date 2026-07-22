"""GET /races/{year}/{round}: the ingested real race for replays, read from the
flagged-superset tables (5.3.4) — the replay wants every lap row, imputation flags
and all, and filters client-side by view.
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from api.schemas import RaceDetail
from senna.data.schema import Event, Lap, Session, SessionResult

router = APIRouter()


@router.get("/races/{year}/{round}", response_model=RaceDetail)
async def race_detail(request: Request, year: int, round: int):
    async with request.app.state.engine.connect() as conn:
        race = (await conn.execute(
            select(Event.event_name, Session.id)
            .join(Session, Session.event_id == Event.id)
            .where(Event.season == year, Event.round == round,
                   Session.session_name == "Race")
        )).first()
        if race is None:
            raise HTTPException(404, f"no ingested race for {year} round {round}")
        event_name, session_id = race

        results = (await conn.execute(
            select(SessionResult.driver_abbrev, SessionResult.team_name,
                   SessionResult.grid_position, SessionResult.position,
                   SessionResult.status, SessionResult.points)
            .where(SessionResult.session_id == session_id)
            .order_by(SessionResult.position)
        )).mappings().all()

        laps = (await conn.execute(
            select(Lap.driver, Lap.driver_number, Lap.lap_number, Lap.lap_time_s,
                   Lap.lap_time_imputed, Lap.position, Lap.compound, Lap.tyre_life,
                   Lap.stint, Lap.pit_in_time_s, Lap.pit_out_time_s)
            .where(Lap.session_id == session_id)
            .order_by(Lap.lap_number, Lap.driver_number)
        )).mappings().all()

    return RaceDetail(year=year, round=round, event_name=event_name,
                      results=[dict(row) for row in results],
                      laps=[dict(row) for row in laps])
