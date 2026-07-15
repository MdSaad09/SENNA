"""Engine construction — the one place the package touches asyncpg."""

import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def engine_for(db_url: str) -> AsyncEngine:
    return create_async_engine(db_url)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set — copy .env.example to .env, start "
            "`docker compose up postgres`, and export it (or source .env)"
        )
    return url
