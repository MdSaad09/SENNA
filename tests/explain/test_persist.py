"""Card persistence (5.3.5): one SimulationRun per eval race carrying model_version +
env_config_hash, one AgentDecision per card, and delete-and-rewrite per
(model_version, purpose) in a single transaction so `make explain` is idempotent.
Schema comes from senna.data.schema.Base.metadata, the tests/data pattern.
"""

import asyncio
import json
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from senna.data.schema import Base
from senna.explain.persist import write_eval_cards

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
)

MODEL_VERSION = "senna-ppo-6b6edb78d84e-C-00835584"  # the promoted headline triplet (F08)
ENV_CONFIG_HASH = "6b6edb78d84e" * 5 + "6b6e"  # any 64-hex stand-in; persist never parses it


def _db_url() -> str:
    raw = os.environ["DATABASE_URL"]
    if "+asyncpg" in raw:
        return raw
    return raw.replace("postgresql://", "postgresql+asyncpg://")


async def _fresh_schema(db_url: str) -> None:
    from senna.data.db import require_disposable

    require_disposable(db_url)
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _counts(db_url: str) -> tuple[int, int]:
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        runs = (await conn.execute(text("select count(*) from simulation_runs"))).scalar_one()
        cards = (await conn.execute(text("select count(*) from agent_decisions"))).scalar_one()
    await engine.dispose()
    return runs, cards


def _card(lap: int) -> dict:
    return {
        "circuit": "bahrain_grand_prix", "lap": lap,
        "action": {"pit": 0, "mode": 1},
        "honesty": {"fidelity": {"pit": 0.93, "mode": 0.96}, "model_version": MODEL_VERSION},
    }


def _races() -> list[dict]:
    return [
        {"circuit": "bahrain_grand_prix", "seed": 1_000_101, "cards": [_card(3), _card(23)]},
        {"circuit": "italian_grand_prix", "seed": 1_000_202, "cards": [_card(11)]},
    ]


def test_rewrite_is_idempotent():
    db_url = _db_url()
    asyncio.run(_fresh_schema(db_url))

    write_eval_cards(db_url, MODEL_VERSION, ENV_CONFIG_HASH, _races())
    first = asyncio.run(_counts(db_url))
    assert first == (2, 3)  # one run per race, one row per card

    # `make explain` run twice must land on the same rows, not double them
    write_eval_cards(db_url, MODEL_VERSION, ENV_CONFIG_HASH, _races())
    assert asyncio.run(_counts(db_url)) == first


def test_run_row_carries_version_and_hash():
    db_url = _db_url()
    asyncio.run(_fresh_schema(db_url))

    write_eval_cards(db_url, MODEL_VERSION, ENV_CONFIG_HASH, _races()[:1])

    async def run_row():
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("select model_version, env_config_hash, config from simulation_runs")
                )
            ).one()
        await engine.dispose()
        return row

    row = asyncio.run(run_row())
    assert row.model_version == MODEL_VERSION  # E-15: the cache key a retrain invalidates
    assert row.env_config_hash == ENV_CONFIG_HASH
    # asyncpg may hand JSONB back as its raw string depending on codec registration
    run_config = row.config if isinstance(row.config, dict) else json.loads(row.config)
    assert run_config["purpose"] == "F09-eval-cards"
    assert run_config["circuit"] == "bahrain_grand_prix"
    assert run_config["seed"] == 1_000_101
