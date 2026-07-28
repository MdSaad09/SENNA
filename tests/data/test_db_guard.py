"""The guard that keeps a destructive test off the ingested store.

Three test modules drop and recreate every table. Pointed at the production database
they erase an ingest that takes minutes to rebuild from a warm FastF1 cache and hours
without one — which has happened three times, twice in a single session. The rule is a
property of the database rather than of pytest, so it lives in senna.data.db and every
destructive site calls it.
"""

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


@pytest.mark.parametrize("module", [
    "tests.api.conftest", "tests.data.test_ingest_resume", "tests.explain.test_persist",
])
def test_every_destructive_module_calls_the_guard(module):
    """A new drop_all that forgets the guard is the whole failure mode, so the wiring is
    pinned per module rather than trusted."""
    from pathlib import Path

    path = Path(module.replace(".", "/") + ".py")
    source = path.read_text()
    assert "drop_all" in source, f"{path} no longer drops tables — drop this row"
    assert "require_disposable" in source, f"{path} drops tables without the guard"
