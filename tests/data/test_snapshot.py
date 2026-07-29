"""The frozen data snapshot (F15, A-09): pg_dump to data/snapshot/ plus a committed
MANIFEST.md carrying the sha256, the size and per-table row counts, so an examiner can
verify the release asset without connecting to anything.

Two of these tests never touch a database. The manifest renderer is a pure seam, and
the restore guard must fire before pg_restore is ever spawned — restore is exactly the
destructive operation require_disposable exists for, and the guard is reused from
senna.data.db, never reimplemented. The round-trip runs only against a disposable
*_test database and carries the slow marker.
"""

import hashlib
import os
import shutil

import pytest

from senna.data.db import ProductionDatabaseError, require_disposable
from senna.data.snapshot import dump_snapshot, restore, row_counts, write_manifest

PRODUCTION = "postgresql+asyncpg://senna:senna@localhost:5432/senna"


def test_the_manifest_names_the_dump_its_hash_and_every_table():
    manifest = write_manifest(
        dump_name="senna-20261117.dump",
        sha256="ab" * 32,
        size_bytes=123456789,
        row_counts={"laps": 412345, "events": 120, "sessions": 480},
    )

    assert manifest.lstrip().startswith("#")  # it is the committed MANIFEST.md
    assert "senna-20261117.dump" in manifest
    assert ("ab" * 32) in manifest  # the full digest, verifiable against the asset
    assert "123456789" in manifest  # exact bytes; a humanized size may ride alongside
    for table, count in (("laps", "412345"), ("events", "120"), ("sessions", "480")):
        assert table in manifest
        assert count in manifest


def test_restore_refuses_non_disposable(tmp_path, monkeypatch):
    """Restoring over the ingested store is the db-wipe incident with a new spelling,
    so the guard must fire before any subprocess exists to do damage."""
    def never_spawn(*args, **kwargs):
        raise AssertionError(
            "pg_restore was spawned against a non-disposable database — the "
            "require_disposable guard did not fire first"
        )

    monkeypatch.setattr("subprocess.run", never_spawn)
    monkeypatch.setattr("subprocess.Popen", never_spawn)
    dump = tmp_path / "senna.dump"
    dump.write_bytes(b"PGDMP")  # a plausible dump, so only the guard can refuse

    with pytest.raises(ProductionDatabaseError):
        restore(dump, PRODUCTION)


@pytest.mark.slow
def test_snapshot_roundtrip(tmp_path):
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("needs Postgres; set DATABASE_URL at senna_test")
    if not (shutil.which("pg_dump") and shutil.which("pg_restore")):
        pytest.skip("needs pg_dump and pg_restore on PATH")
    try:
        require_disposable(url)
    except ProductionDatabaseError:
        pytest.skip("DATABASE_URL must name a *_test database for the restore leg")

    _seed_marker_event(url)
    counts_before = row_counts(url)
    assert counts_before.get("events", 0) >= 1

    dump_path = dump_snapshot(url, tmp_path)
    assert dump_path.exists()
    assert dump_path.stat().st_size > 0

    _delete_marker_event(url)
    assert row_counts(url)["events"] == counts_before["events"] - 1

    restore(dump_path, url)
    assert row_counts(url) == counts_before

    # the committed manifest is what the round-trip is verified against (A-09)
    manifest = write_manifest(
        dump_name=dump_path.name,
        sha256=hashlib.sha256(dump_path.read_bytes()).hexdigest(),
        size_bytes=dump_path.stat().st_size,
        row_counts=counts_before,
    )
    assert str(counts_before["events"]) in manifest


# the marker rides in events with a season no ingest will ever write, so deleting it
# cannot collide with rows other suites left in the shared senna_test database
_MARKER_SEASON = 2099


def _async_url(url: str) -> str:
    return url if "+asyncpg" in url else url.replace("postgresql://",
                                                     "postgresql+asyncpg://")


def _seed_marker_event(url: str) -> None:
    import asyncio
    from datetime import datetime

    from sqlalchemy import delete, insert
    from sqlalchemy.ext.asyncio import create_async_engine

    from senna.data.schema import Base, Event

    async def seed():
        engine = create_async_engine(_async_url(url))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(delete(Event).where(Event.season == _MARKER_SEASON))
            await conn.execute(insert(Event).values(
                season=_MARKER_SEASON, round=1, event_name="Snapshot Marker GP",
                event_format="conventional", event_date=datetime(2099, 1, 1),
            ))
        await engine.dispose()

    asyncio.run(seed())


def _delete_marker_event(url: str) -> None:
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import create_async_engine

    from senna.data.schema import Event

    async def wipe():
        engine = create_async_engine(_async_url(url))
        async with engine.begin() as conn:
            await conn.execute(delete(Event).where(Event.season == _MARKER_SEASON))
        await engine.dispose()

    asyncio.run(wipe())
