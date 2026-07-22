"""POST /simulations and the reads over its stored results (5.9.2). The POST draws a
missing seed before the cache key exists, checks the E-15 key, writes the queued row
and hands the race to the RQ worker — a request handler never simulates (F-26).
Serving reads filter on status IS NOT NULL so F09's eval-card rows, which share these
tables under their own purpose, 404 here instead of 500ing.
"""

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import insert, select

from api.deps import serving_config
from api.schemas import DecisionCard, JobAccepted, LapFrame, SimulationCreate, SimulationResult
from senna.data.schema import AgentDecision, LapFrameRow, SimulationRun
from senna.serve.cache import sim_cache_key, ttl_seconds
from senna.serve.loader import UnknownModelVersionError, read_manifest
from senna.serve.mapping import GridBoundError, UnknownCircuitError
from senna.env.scenario import build_scenario

router = APIRouter()

_SEED_BOUND = 2**31  # the repo-wide int32 seed domain (configs/seeds.yaml, derived_seeds)


def _validated_manifest(req: SimulationCreate) -> dict:
    try:
        manifest = read_manifest(version=req.model_version)
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


async def enqueue_run(request: Request, req: SimulationCreate, *, purpose: str,
                      extra_config: dict | None = None) -> JobAccepted:
    manifest = _validated_manifest(req)
    if req.seed is None:
        # drawn before the key is built, so the echoed seed is the one that runs
        req = req.model_copy(update={"seed": secrets.randbelow(_SEED_BOUND)})

    key = sim_cache_key(manifest["model_version"], manifest["fingerprint"], req)
    redis = request.app.state.redis
    cached = await redis.get(key)
    if cached is not None:
        return JobAccepted(run_id=int(cached))

    engine = request.app.state.engine
    async with engine.begin() as conn:
        run_id = (await conn.execute(
            insert(SimulationRun).values(
                created_at=datetime.now(UTC).replace(tzinfo=None),
                model_version=manifest["model_version"],
                env_config_hash=manifest["fingerprint"],
                status="queued", seed=req.seed, circuit=req.circuit_id, purpose=purpose,
                config={**req.model_dump(), **(extra_config or {})},
            ).returning(SimulationRun.id)
        )).scalar_one()

    # NX: a racing identical request keeps the first run; the worker refreshes on
    # success and deletes on failure so a retry can re-run (E-15)
    await redis.set(key, run_id, nx=True, ex=ttl_seconds())

    queue_cfg = serving_config()["queue"]
    await run_in_threadpool(
        request.app.state.queue.enqueue, "worker.jobs.run_simulation", run_id,
        job_timeout=queue_cfg["job_timeout_s"],
        result_ttl=queue_cfg["result_ttl_s"], failure_ttl=queue_cfg["result_ttl_s"],
    )
    return JobAccepted(run_id=run_id)


@router.post("/simulations", response_model=JobAccepted, status_code=202)
async def create_simulation(request: Request, req: SimulationCreate):
    return await enqueue_run(request, req, purpose="serve")


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
