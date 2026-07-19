"""Card persistence (5.3.5): one SimulationRun per eval race, one AgentDecision row
per card, all inside a single transaction that first deletes whatever a previous
run of `make explain` wrote for this (model_version, purpose) — rewrite, never
append, so re-running lands on the same rows. The sync wrapper is the ingest
pattern: the package's engine is async because the API will be (5.9), and a batch
writer has no reason to duplicate that machinery.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from senna.data.schema import AgentDecision, SimulationRun

PURPOSE = "F09-eval-cards"  # the discriminator: F10's served runs share these tables


def write_eval_cards(db_url: str, model_version: str, env_config_hash: str, races) -> None:
    """races: [{"circuit", "seed", "cards": [card, ...]}, ...] — cards from build_card."""
    asyncio.run(_rewrite(db_url, model_version, env_config_hash, races))


async def _rewrite(db_url, model_version, env_config_hash, races):
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            stale = select(SimulationRun.id).where(
                SimulationRun.model_version == model_version,
                SimulationRun.config["purpose"].astext == PURPOSE,
            )
            await conn.execute(delete(AgentDecision).where(AgentDecision.run_id.in_(stale)))
            await conn.execute(delete(SimulationRun).where(SimulationRun.id.in_(stale)))

            for race in races:
                run_id = (await conn.execute(
                    insert(SimulationRun).values(
                        created_at=datetime.now(UTC).replace(tzinfo=None),
                        model_version=model_version,
                        env_config_hash=env_config_hash,
                        config={"purpose": PURPOSE, "circuit": race["circuit"],
                                "seed": race["seed"]},
                    ).returning(SimulationRun.id)
                )).scalar_one()
                await conn.execute(
                    insert(AgentDecision),
                    [{"run_id": run_id, "lap_number": card["lap"], "decision": card}
                     for card in race["cards"]],
                )
    finally:
        await engine.dispose()
