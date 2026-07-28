"""Engine construction — the one place the package touches asyncpg — and the guard that
keeps a destructive test off the ingested store.

The guard is here rather than in the test tree because the rule is about the database, not
about pytest: dropping every table is only ever safe on a database someone has declared
disposable. The ingest takes minutes from a warm FastF1 cache and hours without one, so the
cost of getting this wrong is real, and it has been paid three times.
"""

import os
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_DISPOSABLE_SUFFIX = "_test"
_OVERRIDE = "SENNA_ALLOW_DESTRUCTIVE_DB"


class ProductionDatabaseError(RuntimeError):
    """A drop-and-recreate was aimed at a database that is not marked disposable."""


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


def database_name(url: str) -> str:
    """The database this URL could name, resolved conservatively.

    The path alone is not enough: SQLAlchemy merges the query over the connect arguments,
    so `.../senna_test?database=senna` looks disposable and connects to the ingested store.
    But which key a driver honours is a driver's business — asyncpg takes `database` and
    rejects `dbname` outright, psycopg2 the other way about. Rather than model each one and
    inherit its accidents, every candidate is collected and the least disposable wins: if
    any reading of the URL points at something not named `*_test`, that is the answer.
    """
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    candidates = []
    for key in ("database", "dbname"):
        values = query.get(key, [])
        if len(values) > 1:
            # SQLAlchemy hands the driver a tuple here and no layer implements "last wins";
            # guessing one would be a rule nothing enforces
            raise ProductionDatabaseError(
                f"'{url}' names the database {len(values)} times ({values}) — no driver "
                "defines which wins, so this cannot be checked"
            )
        candidates.extend(values)
    candidates.append(parsed.path.lstrip("/"))
    return min(candidates, key=lambda name: name.endswith(_DISPOSABLE_SUFFIX))


def require_disposable(url: str | None = None) -> str:
    """Refuse a destructive operation unless the database is named as a disposable one.

    A name ending in `_test` is the signal. The escape hatch deliberately makes the
    operator name the database they are authorising rather than setting a bare flag: a
    blanket "yes" is the kind of thing that gets exported once and then forgotten in a
    shell that later runs the whole suite against the real store.
    """
    url = url or database_url()
    name = database_name(url)
    if not name:
        # a URL with no path leaves asyncpg to default the database to the role name,
        # which is the ingested store; an empty name would also match an empty override
        raise ProductionDatabaseError(
            f"'{url}' names no database, so the server would pick one — most likely the "
            "role's own. Put the database in the URL before dropping anything."
        )

    override = os.environ.get(_OVERRIDE)
    if name.endswith(_DISPOSABLE_SUFFIX) or (override and override == name):
        return url

    raise ProductionDatabaseError(
        f"refusing to drop every table on '{name}': destructive tests run against a "
        f"database whose name ends in '{_DISPOSABLE_SUFFIX}'. Create one and point the "
        f"tests at it:\n"
        f"    docker compose exec postgres createdb -U senna {name}{_DISPOSABLE_SUFFIX}\n"
        f"    DATABASE_URL=postgresql+asyncpg://senna:senna@localhost:5432/"
        f"{name}{_DISPOSABLE_SUFFIX} .venv/bin/python -m pytest tests/api\n"
        f"If '{name}' really is disposable, say so by name: {_OVERRIDE}={name}"
    )
