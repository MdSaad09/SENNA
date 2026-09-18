

import os
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import insert, select

from api.deps import serving_config
from api.schemas import DecisionCard, JobAccepted, LapFrame, SimulationCreate, SimulationResult
from senna.data.schema import AgentDecision, LapFrameRow, SimulationRun
from senna.env.scenario import build_scenario
from senna.serve.loader import UnknownModelVersionError, read_manifest
from senna.serve.runner import run_simulation

router = APIRouter()



def validated_manifest(req: SimulationCreate) -> dict:
    try:
        # request > MODEL_VERSION env > the promoted headline (5.11.2)
        manifest = read_manifest(version=req.model_version or os.environ.get("MODEL_VERSION"))
    except UnknownModelVersionError as err:
        raise HTTPException(422, str(err)) from err
    try:
        scenario = build_scenario(req.circuit_id, req.era)
    except KeyError as err:
        raise HTTPException(
            404, f"no fitted circuit '{req.circuit_id}' — GET /api/v1/circuits lists the library"
        ) from err
    if req.grid_position > scenario.grid_size:
        raise HTTPException(
            422, f"grid_position {req.grid_position} exceeds the {req.era} grid "
                 f"of {scenario.grid_size} cars"
        )
    return manifest


def draw_seed(req: SimulationCreate) -> SimulationCreate:
    """A missing seed is drawn before the cache key is built, so the echoed seed is
    the one that runs. Shared with the counterfactual pair path — the seed must be
    drawn exactly once per pair or the E-15 key and the runs disagree."""
    if req.seed is not None:
        return req
    bound = serving_config()["seeds"]["draw_bound"]
    return req.model_copy(update={"seed": secrets.randbelow(bound)})




async def start_run(request: Request, req: SimulationCreate, *, purpose: str,
                    extra_config: dict | None = None) -> JobAccepted:
    # file+yaml IO off the event loop
    manifest = await run_in_threadpool(validated_manifest, req)
    req = draw_seed(req)

    async with request.app.state.engine.begin() as conn:
        run_id = (await conn.execute(
            insert(SimulationRun).values(
                created_at=datetime.now(UTC).replace(tzinfo=None),
                model_version=manifest["model_version"],
                env_config_hash=manifest["fingerprint"],
                status="queued", seed=req.seed, circuit=req.circuit_id, purpose=purpose,
                config={**req.model_dump(), **(extra_config or {})},
            ).returning(SimulationRun.id)
        )).scalar_one()

    # the race itself, on a thread so the event loop keeps serving reads
    await run_in_threadpool(run_simulation, run_id)
    return JobAccepted(run_id=run_id)


@router.post("/simulations", response_model=JobAccepted, status_code=202)
async def create_simulation(request: Request, req: SimulationCreate):
    """202 is kept from 5.9.2 even though the race is finished when this returns: the
    body is still a job handle and the client still reads the result back by id."""
    return await start_run(request, req, purpose="serve")


async def _serving_row(request: Request, run_id: int):
    async with request.app.state.engine.connect() as conn:
        row = (await conn.execute(
            select(SimulationRun).where(SimulationRun.id == run_id,
                                        SimulationRun.status.is_not(None))
        )).first()
    if row is None:
        raise HTTPException(404, f"no simulation run {run_id}")
    return row


@router.get("/simulations/{run_id}", response_model=SimulationResult)
async def simulation_result(request: Request, run_id: int):
    row = await _serving_row(request, run_id)
    return SimulationResult(
        run_id=row.id, status=row.status, model_version=row.model_version,
        env_config_hash=row.env_config_hash, circuit_id=row.circuit,
        era=(row.config or {}).get("era"), seed=row.seed, config=row.config,
        summary=row.summary, created_at=row.created_at, started_at=row.started_at,
        finished_at=row.finished_at,
    )


@router.get("/simulations/{run_id}/frames", response_model=list[LapFrame])
async def simulation_frames(request: Request, run_id: int,
                            from_lap: int = 1, to_lap: int | None = None):
    await _serving_row(request, run_id)
    page_size = serving_config()["frames"]["page_size"]
    if to_lap is None:
        to_lap = from_lap + page_size - 1
    to_lap = min(to_lap, from_lap + page_size - 1)
    async with request.app.state.engine.connect() as conn:
        frames = (await conn.execute(
            select(LapFrameRow.frame)
            .where(LapFrameRow.run_id == run_id,
                   LapFrameRow.lap >= from_lap, LapFrameRow.lap <= to_lap)
            .order_by(LapFrameRow.lap)
        )).scalars().all()
    return list(frames)


@router.get("/simulations/{run_id}/decisions", response_model=list[DecisionCard])
async def simulation_decisions(request: Request, run_id: int):
    await _serving_row(request, run_id)
    async with request.app.state.engine.connect() as conn:
        cards = (await conn.execute(
            select(AgentDecision.decision).where(AgentDecision.run_id == run_id)
            .order_by(AgentDecision.lap_number)
        )).scalars().all()
    return list(cards)
