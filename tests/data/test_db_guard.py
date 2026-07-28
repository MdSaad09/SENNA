"""The guard that keeps a destructive test off the ingested store.

Three test modules drop and recreate every table. Pointed at the production database
they erase an ingest that takes minutes to rebuild from a warm FastF1 cache and hours
without one — which has happened three times, twice in a single session. The rule is a
property of the database rather than of pytest, so it lives in senna.data.db and every
destructive site calls it.
"""

from pathlib import Path

import pytest

from senna.data.db import ProductionDatabaseError, database_name, require_disposable

PRODUCTION = "postgresql+asyncpg://senna:senna@localhost:5432/senna"
DISPOSABLE = "postgresql+asyncpg://senna:senna@localhost:5432/senna_test"


def test_a_disposable_database_is_allowed():
    assert require_disposable(DISPOSABLE) == DISPOSABLE


def test_the_production_database_is_refused():
    with pytest.raises(ProductionDatabaseError, match="senna"):
        require_disposable(PRODUCTION)


def test_the_refusal_says_what_to_do():
    # a guard that only says "no" gets bypassed; this one has to hand over the command
    with pytest.raises(ProductionDatabaseError) as raised:
        require_disposable(PRODUCTION)

    message = str(raised.value)
    assert "senna_test" in message
    assert "SENNA_ALLOW_DESTRUCTIVE_DB" in message


def test_the_override_must_name_the_database(monkeypatch):
    # a bare truthy flag is the kind of thing that gets exported once and forgotten, so
    # the escape hatch only opens for the database the operator actually typed out
    monkeypatch.setenv("SENNA_ALLOW_DESTRUCTIVE_DB", "1")
    with pytest.raises(ProductionDatabaseError):
        require_disposable(PRODUCTION)

    monkeypatch.setenv("SENNA_ALLOW_DESTRUCTIVE_DB", "somewhere_else")
    with pytest.raises(ProductionDatabaseError):
        require_disposable(PRODUCTION)

    monkeypatch.setenv("SENNA_ALLOW_DESTRUCTIVE_DB", "senna")
    assert require_disposable(PRODUCTION) == PRODUCTION


def test_database_name_reads_the_url_path():
    assert database_name(PRODUCTION) == "senna"
    assert database_name(DISPOSABLE) == "senna_test"
    assert database_name("postgresql://u:p@host:5432/other_test") == "other_test"


def _destructive_modules():
    """Every test module that drops tables, discovered rather than listed: a hard-coded
    list cannot notice the new module that forgets the guard, which is the whole failure
    mode this file exists for."""
    from senna import config

    here = Path(__file__).resolve()
    return sorted(
        path for path in (config.REPO_ROOT / "tests").rglob("*.py")
        if path.resolve() != here and "drop_all" in path.read_text()
    )


def test_at_least_one_module_still_drops_tables():
    # if this ever empties, the discovery below is silently vacuous
    assert _destructive_modules()


@pytest.mark.parametrize("path", _destructive_modules(), ids=lambda p: p.stem)
def test_every_destructive_module_calls_the_guard(path):
    assert "require_disposable" in path.read_text(), (
        f"{path} drops every table without calling require_disposable — point it at the "
        "guard before it finds the ingested store"
    )


def _explode(*args, **kwargs):
    raise AssertionError(
        "a destructive fixture reached the database layer with DATABASE_URL pointing at "
        "the production store — the guard did not fire"
    )


@pytest.mark.parametrize("call", [
    ("tests.api.conftest", "reset_schema", ()),
    ("tests.data.test_ingest_resume", "_fresh_schema", (PRODUCTION,)),
    ("tests.explain.test_persist", "_fresh_schema", (PRODUCTION,)),
], ids=lambda c: c[0].rsplit(".", 1)[-1] if isinstance(c, tuple) else str(c))
def test_every_destructive_entry_point_refuses_production(call, monkeypatch):
    """The discovery grep proves the call exists; this proves it fires.

    The engine constructor is replaced with something that raises, so a regressed guard
    fails this test instead of demonstrating the bug on the real database. A test that
    only goes red *after* dropping the tables would be a worse version of the incident it
    models — and one that needs no DATABASE_URL from the operator, so a plain
    `pytest tests/data` would be the thing that erases the store.
    """
    import asyncio
    import importlib

    module_name, function_name, args = call
    module = importlib.import_module(module_name)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", _explode)
    monkeypatch.setattr(module, "create_async_engine", _explode, raising=False)
    monkeypatch.setenv("DATABASE_URL", PRODUCTION)
    monkeypatch.delenv("SENNA_ALLOW_DESTRUCTIVE_DB", raising=False)

    target = getattr(module, function_name)
    with pytest.raises(ProductionDatabaseError):
        result = target(*args)
        if asyncio.iscoroutine(result):
            asyncio.run(result)


def test_a_url_without_a_database_is_refused(monkeypatch):
    # sqlalchemy leaves the database unset and asyncpg then defaults it to the role name,
    # which is the ingested store; an empty name also used to match an empty override
    monkeypatch.setenv("SENNA_ALLOW_DESTRUCTIVE_DB", "")
    with pytest.raises(ProductionDatabaseError):
        require_disposable("postgresql+asyncpg://senna:senna@localhost:5432")
