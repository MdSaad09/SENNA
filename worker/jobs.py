"""run_simulation: the RQ job (5.9.3). The whole race runs immediately — frames and
TreeSHAP decision cards built lap by lap, persisted in one transaction — and the API
streams from that store on its own clock, so a dropped socket never loses a race
(E-16). The frozen triplet and surrogate load once per worker process (F-26), and
the same helpers that carded F09's evaluation races build the live cards here.
"""

import os

# arm64 landmine: torch and xgboost each bundle libomp, and two OpenMP runtimes in
# one process segfault — set before either loads. A bare statement, not an import
# whose position a lint autofix can shuffle below the torch imports (it did).
os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio
from datetime import UTC, datetime

import numpy as np
import redis
from sqlalchemy import delete, insert, select, update

from api.schemas import SimulationCreate
from senna import config
from senna.data.db import database_url, engine_for
from senna.data.schema import AgentDecision, LapFrameRow, SimulationRun
from senna.explain.attributions import top_drivers
from senna.explain.cards import build_card
from senna.explain.dataset import DecisionLogger
from senna.explain.features import FEATURE_NAMES
from senna.explain.run import flip_lines_for, pit_mask_fn, pit_policy_fn
from senna.serve.cache import events_channel, sim_cache_key, ttl_seconds
from senna.serve.frames import build_lap_frame
from senna.serve.loader import ServingModel, load_serving_model
from senna.serve.mapping import build_env
from senna.train.evals import Sb3Policy
from worker import settings

_explainer_cache: dict[str, dict] = {}


def run_simulation(run_id: int) -> None:
    try:
        key = asyncio.run(_run(run_id))
    except Exception as err:
        key = asyncio.run(_mark_failed(run_id, err))
        _finish_redis(run_id, key, ok=False)
        raise
    _finish_redis(run_id, key, ok=True)


async def _run(run_id: int) -> str:
    engine = engine_for(database_url())
    try:
        async with engine.begin() as conn:
            row = (await conn.execute(
                select(SimulationRun).where(SimulationRun.id == run_id)
            )).one()
            await conn.execute(
                update(SimulationRun).where(SimulationRun.id == run_id)
                .values(status="running", started_at=_now())
            )

        req = _request_from(row.config)
        serving = load_serving_model(version=row.model_version)
        frames, cards, summary = _simulate(req, serving)

        async with engine.begin() as conn:
            # rewrite, never append: a retried job lands on the same rows
            await conn.execute(delete(LapFrameRow).where(LapFrameRow.run_id == run_id))
            await conn.execute(delete(AgentDecision).where(AgentDecision.run_id == run_id))
            await conn.execute(
                insert(LapFrameRow),
                [{"run_id": run_id, "lap": frame["lap"], "frame": frame} for frame in frames],
            )
            if cards:
                await conn.execute(
                    insert(AgentDecision),
                    [{"run_id": run_id, "lap_number": card["lap"], "decision": card}
                     for card in cards],
                )
            await conn.execute(
                update(SimulationRun).where(SimulationRun.id == run_id)
                .values(status="complete", finished_at=_now(), summary=summary)
            )
        return sim_cache_key(serving.model_version, serving.env_config_hash, req)
    finally:
        await engine.dispose()


def _simulate(req: SimulationCreate, serving: ServingModel):
    env = build_env(req)
    policy = Sb3Policy(serving.model, serving.venv.normalize_obs)
    logger = DecisionLogger(policy, circuit=req.circuit_id, seed=req.seed)

    obs, info = env.reset(seed=req.seed, options={"grid_position": req.grid_position})
    logger.reset(obs, info, rng=None)
    frames: list[dict] = []
    snapshot = None
    terminated = False
    while not terminated:
        action = np.asarray(logger.act(obs, info, env.action_masks()))
        obs, _, terminated, _, info = env.step(action)
        frame, snapshot = build_lap_frame(env, info, snapshot)
        frames.append(frame)

    summary = {
        "final_position": int(info["final_position"]),
        "points": float(info["points"]),
        "race_time_s": float(info["race_time_s"]),
        "dnf": bool(info["dnf"]),
        "pit_laps": [int(lap) for lap in info["pit_laps"]],
        "compounds": [str(compound) for compound in info["compounds"]],
        "derate_count": int(info["derate_count"]),
        "energy_totals": {k: float(v) for k, v in info["energy_totals"].items()},
        # the playback clock's 1x period; fitted per circuit (physics_params t0_s)
        "nominal_lap_s": float(env.scenario.t0_s),
        "n_cars": env.n_cars,
        "total_laps": env.total_laps,
    }
    return frames, _cards_for(logger.records, env, policy, serving), summary


def _cards_for(records, env, policy, serving: ServingModel) -> list[dict]:
    if not records:
        return []
    explainers = _explainers(serving)
    states = np.stack([record.obs for record in records])
    pit_shap = explainers["pit"].shap_values(states)
    mode_shap = explainers["mode"].shap_values(states)

    explain_cfg = config.load("explain")
    top_k = explain_cfg["cards"]["top_k_drivers"]
    flip_cfg = explain_cfg["flip"]
    pit_only = config.load("serving")["live_cards"]["flip_on_pit_only"]
    fidelity = {head: fit["top1"] for head, fit in serving.fidelity["heads"].items()}
    mask_fn = pit_mask_fn(env.scenario)
    policy_fn = pit_policy_fn(policy)

    cards = []
    for i, record in enumerate(records):
        pit_row = pit_shap[i, :, record.pit_action]
        if record.pit_action != 0 or not pit_only:
            # 5.8.2: flip probes for headline decisions — a pit call is the headline
            flips = flip_lines_for(record, pit_row, env.scenario, policy_fn, mask_fn,
                                   per_card=flip_cfg["features_per_card"],
                                   sweep_points=flip_cfg["sweep_points"],
                                   max_sweeps=flip_cfg["max_sweeps"])
        else:
            flips = []
        cards.append(build_card(
            record,
            pit_drivers=top_drivers(pit_row, FEATURE_NAMES, top_k),
            mode_drivers=top_drivers(mode_shap[i, :, record.mode_action],
                                     FEATURE_NAMES, top_k),
            flip_lines=flips,
            fidelity=fidelity,
            model_version=serving.model_version,
            # the loader already refused any surrogate not fitted to this checkpoint
            surrogate_version=serving.model_version,
        ))
    return cards


def _explainers(serving: ServingModel) -> dict:
    if serving.model_version not in _explainer_cache:
        from senna.explain.attributions import head_explainer

        _explainer_cache[serving.model_version] = {
            head: head_explainer(booster, serving.background)
            for head, booster in serving.boosters.items()
        }
    return _explainer_cache[serving.model_version]


async def _mark_failed(run_id: int, err: Exception) -> str | None:
    engine = engine_for(database_url())
    try:
        async with engine.begin() as conn:
            row = (await conn.execute(
                select(SimulationRun).where(SimulationRun.id == run_id)
            )).one_or_none()
            await conn.execute(
                update(SimulationRun).where(SimulationRun.id == run_id)
                .values(status="failed", finished_at=_now(),
                        summary={"error": f"{type(err).__name__}: {err}"})
            )
        if row is None or not (row.model_version and row.env_config_hash and row.config):
            return None
        return sim_cache_key(row.model_version, row.env_config_hash,
                             _request_from(row.config))
    finally:
        await engine.dispose()


def _finish_redis(run_id: int, key: str | None, *, ok: bool) -> None:
    conn = redis.Redis.from_url(settings.redis_url())
    try:
        if key:
            if ok:
                conn.set(key, run_id, ex=ttl_seconds())
            else:
                conn.delete(key)  # E-15: a failed run must not answer a retry
        conn.publish(events_channel(run_id), "complete" if ok else "failed")
    finally:
        conn.close()


def _request_from(run_config: dict) -> SimulationCreate:
    known = {name: run_config[name]
             for name in SimulationCreate.model_fields if name in run_config}
    return SimulationCreate(**known)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
