"""Per-session ingest checkpoints and the completeness gate (E-12, E-13).

A checkpoint flips to `loaded` inside the same transaction that writes the
session's rows, so a kill mid-write rolls both back and the rerun simply
retries — an absent row means "not attempted yet" and there is no
in_progress state to repair.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from senna.data.db import engine_for
from senna.data.schema import IngestCheckpoint

LOADED = "loaded"
FAILED = "failed"
EXCLUDED = "excluded"


class IncompleteIngestError(RuntimeError):
    """A past event is neither loaded nor excluded with a reason — no modelling yet (F-14)."""


def key_of(session: dict) -> tuple:
    return (session["season"], session["round"], session["source"], session["session_name"])


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def upsert_state(
    conn: AsyncConnection,
    session: dict,
    state: str,
    rows_loaded: int | None = None,
    error: str | None = None,
    excluded_reason: str | None = None,
) -> None:
    values = {
        "season": session["season"],
        "round": session["round"],
        "source": session["source"],
        "session_name": session["session_name"],
        "event_name": session.get("event_name"),
        "state": state,
        "rows_loaded": rows_loaded,
        "error": error,
        "excluded_reason": excluded_reason,
        "updated_at": _utcnow_naive(),
    }
    refresh = ("event_name", "state", "rows_loaded", "error", "excluded_reason", "updated_at")
    stmt = pg_insert(IngestCheckpoint).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["season", "round", "source", "session_name"],
        set_={name: stmt.excluded[name] for name in refresh},
    )
    await conn.execute(stmt)


async def states_by_key(engine: AsyncEngine) -> dict[tuple, str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            select(
                IngestCheckpoint.season,
                IngestCheckpoint.round,
                IngestCheckpoint.source,
                IngestCheckpoint.session_name,
                IngestCheckpoint.state,
            )
        )
    return {(r.season, r.round, r.source, r.session_name): r.state for r in rows}


async def mark_excluded(db_url: str, session: dict, reason: str) -> None:
    """Exclusion is a decision, not a gap — completeness demands the written reason."""
    engine = engine_for(db_url)
    try:
        async with engine.begin() as conn:
            await upsert_state(conn, session, EXCLUDED, excluded_reason=reason)
    finally:
        await engine.dispose()


async def assert_complete(db_url: str, expected: list[dict]) -> None:
    """E-12's gate: every expected past session is loaded or excluded-with-reason.

    Future events are not expected yet — that is how Madrid joins the calendar
    in September without failing every run before it (E-13).
    """
    engine = engine_for(db_url)
    try:
        states = await states_by_key(engine)
    finally:
        await engine.dispose()

    now = _utcnow_naive()
    missing = [
        session
        for session in expected
        # a NaT date is owed, not forgiven: only a known future date defers a
        # session (E-13); an unknown one must be loaded or excluded explicitly
        if not session["session_date_utc"] > now
        and states.get(key_of(session)) not in (LOADED, EXCLUDED)
    ]
    if missing:
        listing = "\n".join(
            f"  {s['season']} round {s['round']} {s['event_name']}"
            f" — {s['source']} {s['session_name']}"
            for s in missing
        )
        raise IncompleteIngestError(
            f"{len(missing)} expected session(s) neither loaded nor excluded:\n{listing}\n"
            "rerun the ingest to retry, or mark_excluded with a written reason"
        )
