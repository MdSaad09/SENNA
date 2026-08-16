"""POST /counterfactuals (F-24): one POST answers with a linked, event-paired run
pair — the frozen agent and the driver's actual strategy replayed in the same
simulator. The agent leg runs the era-matched model where one is baked, so the
comparison separates better strategy from a different car; where none is baked
the route falls back to the frozen 2026 model on 2024 physics and the run config
says so loudly — era_matched_model: pending-F14 — so no consumer can mistake the
preview for the thesis result. The real stops are extracted from the driver's
ingested laps here at POST time and frozen into the run config, so the worker
never reads laps and a retry replays the identical plan.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, insert, select, update

from api.routes.simulations import draw_seed, validated_manifest
from api.schemas import JobAccepted, SimulationCreate
from senna.data.schema import Event, Lap, Session, SessionResult, SimulationRun
from senna.env.scenario import build_scenario
from senna.serve.loader import (
    UnknownModelVersionError,
    era_model_version,
    read_manifest,
)
from senna.serve.mapping import circuit_slug
from senna.serve.runner import run_counterfactual
from senna.strategy.extract import plan_from_rows

router = APIRouter()


class CounterfactualCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    round: int
    driver: str
    # optional so a demo deep link can pin the pair; drawn server-side when absent
    # (additive 5.9.2 divergence, F13 plan)
    seed: int | None = None


async def _real_plan(conn, session_id: int, driver: str, sim_total_laps: int):
    rows = (await conn.execute(
        select(Lap.lap_number, Lap.stint, Lap.compound, Lap.pit_in_time_s)
        .where(Lap.session_id == session_id, Lap.driver == driver,
               Lap.source.like("real%"))
        .order_by(Lap.lap_number)
    )).all()
    if not any(stint is not None for _, stint, _, _ in rows):
        raise HTTPException(
            404, f"{driver}'s ingested laps carry no stint data — there is no real "
                 "strategy to replay; re-ingest the event with stints populated"
        )
    real_total_laps = (await conn.execute(
        select(func.max(Lap.lap_number))
        .where(Lap.session_id == session_id, Lap.source.like("real%"))
    )).scalar_one()
    plan = plan_from_rows(rows, sim_total_laps=sim_total_laps,
                          real_total_laps=int(real_total_laps))
    if any(name is None for _, name in plan.stops):
        raise HTTPException(
            404, f"{driver}'s ingested laps carry a stint without compound data — "
                 "the replay cannot pick a tyre; re-ingest the event with compounds populated"
        )
    return [[lap, name] for lap, name in plan.stops]


@router.post("/counterfactuals", response_model=JobAccepted, status_code=202)
async def create_counterfactual(request: Request, req: CounterfactualCreate):
    async with request.app.state.engine.connect() as conn:
        raced = (await conn.execute(
            select(Event.event_name, SessionResult.grid_position, Session.id)
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
        event_name, grid_position, session_id = raced

        slug = circuit_slug(event_name)
        try:
            scenario = build_scenario(slug, "2024")
        except KeyError as err:
            raise HTTPException(404, f"'{slug}' has no fitted 2024 scenario — "
                                     "the counterfactual needs the era's physics") from err
        real_stops = await _real_plan(conn, session_id, req.driver, scenario.total_laps)

    sim = SimulationCreate(
        circuit_id=slug,
        era="2024",
        # a pit-lane start ingests as grid 0; the back of the era's field is the
        # honest slot, and the era says how big that field is (never a literal 20)
        grid_position=grid_position or scenario.grid_size,
        rival_band="test",
        seed=req.seed,
    )
    manifest = await run_in_threadpool(validated_manifest, sim)
    # F-24: the agent leg should be the era-matched model, not the 2026 headline driving a
    # 2024 car. Until make finetune has baked one, fall back to the headline and say so in
    # the run config — the dashboard reads that string and prints the caveat itself
    try:
        era_matched = await run_in_threadpool(era_model_version, sim.era)
        served = await run_in_threadpool(read_manifest, None, era_matched)
    except UnknownModelVersionError:
        era_matched, served = "pending-F14", manifest
    sim = draw_seed(sim)

    identity = {"year": req.year, "round": req.round, "driver": req.driver}
    now = datetime.now(UTC).replace(tzinfo=None)
    async with request.app.state.engine.begin() as conn:
        # baseline first so the agent row can carry its id; no model_version — no
        # policy network runs the replay, and the null is what E-15 reads as
        # "nothing to explain"
        baseline_id = (await conn.execute(
            insert(SimulationRun).values(
                created_at=now, model_version=None,
                env_config_hash=served["fingerprint"],
                status="queued", seed=sim.seed, circuit=slug,
                purpose="counterfactual_baseline",
                config={**sim.model_dump(), **identity, "policy": "real_replay"},
            ).returning(SimulationRun.id)
        )).scalar_one()
        agent_id = (await conn.execute(
            insert(SimulationRun).values(
                created_at=now,
                model_version=served["model_version"],
                env_config_hash=served["fingerprint"],
                status="queued", seed=sim.seed, circuit=slug, purpose="counterfactual",
                config={**sim.model_dump(), **identity,
                        "era_matched_model": era_matched,
                        "baseline_run_id": baseline_id, "real_stops": real_stops,
                        "pairing": "event_trace"},
            ).returning(SimulationRun.id)
        )).scalar_one()
        await conn.execute(
            update(SimulationRun).where(SimulationRun.id == baseline_id)
            .values(config={**sim.model_dump(), **identity,
                            "policy": "real_replay", "agent_run_id": agent_id})
        )

    # both legs, inline: a one-legged comparison must never look complete, so the
    # pair runs or fails together (F-24)
    await run_in_threadpool(run_counterfactual, agent_id, baseline_id)
    return JobAccepted(run_id=agent_id, baseline_run_id=baseline_id)
