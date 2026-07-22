"""POST /counterfactuals (F-24): era-matched replay plumbing, real end to end. Until
F14 delivers the Stage-C 2024 fine-tune, the job runs the frozen 2026 model on 2024
physics and the run config says so loudly — era_matched_model: pending-F14 — so no
consumer can mistake the preview for the thesis result (decision Q3).
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from api.routes.simulations import enqueue_run
from api.schemas import JobAccepted, SimulationCreate
from senna.data.schema import Event, Session, SessionResult
from senna.env.scenario import build_scenario
from senna.serve.mapping import circuit_slug

router = APIRouter()


class CounterfactualCreate(BaseModel):
    year: int
    round: int
    driver: str


@router.post("/counterfactuals", response_model=JobAccepted, status_code=202)
async def create_counterfactual(request: Request, req: CounterfactualCreate):
    async with request.app.state.engine.connect() as conn:
        raced = (await conn.execute(
            select(Event.event_name, SessionResult.grid_position)
            .join(Session, Session.event_id == Event.id)
            .join(SessionResult, SessionResult.session_id == Session.id)
            .where(Event.season == req.year, Event.round == req.round,
                   Session.session_name == "Race",
                   SessionResult.driver_abbrev == req.driver)
        )).first()
    if raced is None:
        raise HTTPException(
            404, f"no ingested race result for {req.driver} at {req.year} round {req.round}"
        )

    event_name, grid_position = raced
    slug = circuit_slug(event_name)
    try:
        scenario = build_scenario(slug, "2024")
    except KeyError as err:
        raise HTTPException(404, f"'{slug}' has no fitted 2024 scenario — "
                                 "the counterfactual needs the era's physics") from err
    sim = SimulationCreate(
        circuit_id=slug,
        era="2024",
        # a pit-lane start ingests as grid 0; the back of the era's field is the
        # honest slot, and the era says how big that field is (never a literal 20)
        grid_position=grid_position or scenario.grid_size,
        rival_band="test",
    )
    return await enqueue_run(
        request, sim, purpose="counterfactual",
        extra_config={"year": req.year, "round": req.round, "driver": req.driver,
                      "era_matched_model": "pending-F14"},
    )
