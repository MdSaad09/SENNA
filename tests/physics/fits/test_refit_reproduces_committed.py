"""A-09 enforced rather than promised: the frozen pack must reproduce the shipped physics.

The pack's whole claim is that an examiner can restore `data/snapshot/`, follow
`docs/freeze.md`, run `make fit`, and arrive at the constants the repo ships. That claim
was false. `configs/physics_params.yaml` was written from a store holding all five
declared seasons — its own watermark said so — while only 2024 and 2025 reached the
joint pace fits. Bahrain's era-2024 base pace came from 1958 laps of an available 3705,
about 0.9 s/lap, and nothing in the build noticed because nothing compared the file
against what its own data produces.

This is the guard that actually failed on `main`. `assert_season_coverage` would have
passed that run without a word, because the store was complete; `assert_pace_season_
coverage` did not exist yet and is the gate that matches the defect's shape. Rendering
the fit and diffing it against the committed bytes is the broadest of the three: it
catches any disagreement between the committed constants and what the data produces,
including causes nobody has thought of yet.

It is `slow` and needs the ingested store, so CI's `-m "not slow"` run never executes
it. `docs/freeze.md` step 1 runs it explicitly before a tag — that, not CI, is what
makes the A-09 promise checkable.

These two are the guard. They need the ingested store rather than the disposable test
database, and the battery is minutes of real work, so they are `slow` and skip cleanly
when the store is not there. Read-only throughout: nothing here drops a table, and the
refit renders to a tmp path rather than over the committed file.
"""

import asyncio
import difflib
import os

import pytest
from sqlalchemy import text

from senna import config
from senna.data.db import database_url, engine_for
from senna.physics.fits import frames, run

pytestmark = pytest.mark.slow

COMMITTED_PARAMS = config.REPO_ROOT / "configs" / "physics_params.yaml"

# raced dry in all four era-2024 seasons, and the circuit the F18 spec reproduced the
# defect on — 1958 laps under the old scope against 3705 under the full era
SAMPLE_EVENT = "Bahrain Grand Prix"
ERA_2024_SEASONS = {2022, 2023, 2024, 2025}


async def _read(query):
    engine = engine_for(database_url())
    try:
        async with engine.connect() as conn:
            return await query(conn)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def ingested_store():
    """The circuit index, or a skip if this is not the full ingested store."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("needs the ingested store; export DATABASE_URL (see .env.example)")

    # the energy module swallows FastF1 failures by design, so a cold cache does not
    # error — it quietly drops the energy blocks and the byte comparison then fails
    # blaming the fitters. Skip rather than accuse.
    cache = config.REPO_ROOT / config.get(config.load("ingest"), "fastf1.cache_dir")
    if not cache.is_dir() or not any(cache.iterdir()):
        pytest.skip(f"needs a warm FastF1 cache at {cache}; the energy fits read telemetry")

    # the disposable test database is the usual value of DATABASE_URL and holds no laps;
    # circuit_index raises KeyError on the empty frame rather than returning one, so ask
    # first. A test that needs the ingested store must skip on the test store, not error.
    laps = asyncio.run(_read(lambda conn: conn.scalar(text("select count(*) from laps"))))
    if not laps:
        pytest.skip("DATABASE_URL names a store with no laps; this needs the ingested one")

    rounds = config.get(config.load("data_split"), "calibration_rounds")
    index = asyncio.run(_read(lambda conn: frames.circuit_index(conn, rounds)))
    declared = config.get(config.load("ingest"), "seasons")
    missing = sorted(set(declared) - set(index["season"]))
    if missing:
        # a partial store is the defect this feature fixed, not a reason to fail here:
        # the gate in run.py is what refuses it, and test_coverage_gate.py covers that
        pytest.skip(f"store is missing season(s) {missing}; run `make ingest` for them")
    return index


def test_refit_reproduces_the_committed_params(ingested_store, tmp_path):
    refitted = tmp_path / "physics_params.yaml"
    run.main(["--params-out", str(refitted)])

    produced = refitted.read_text()
    committed = COMMITTED_PARAMS.read_text()
    if produced == committed:
        return

    # a whole-file assert dumps 2000 lines and teaches nothing; the first divergence
    # names the circuit and the constant, which is where the investigation starts
    diff = difflib.unified_diff(
        committed.splitlines(), produced.splitlines(), "committed", "refitted", n=1, lineterm=""
    )
    pytest.fail(
        "`make fit` no longer renders configs/physics_params.yaml — either the fitters "
        "changed and the file needs regenerating, or the store is not the frozen "
        "snapshot (A-09):\n" + "\n".join(list(diff)[:40])
    )


def test_every_era_2024_season_reaches_the_fit(ingested_store):
    rounds = config.get(config.load("data_split"), "calibration_rounds")
    laps = asyncio.run(
        _read(lambda conn: frames.pace_laps(conn, SAMPLE_EVENT, "2024", rounds))
    )

    # by season, not by count: a lap total looks healthy while a whole season is
    # absent, which is exactly how the original defect stayed invisible
    assert set(laps["season"]) == ERA_2024_SEASONS
